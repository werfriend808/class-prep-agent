"""검색 -> 본문 조회 -> 요약 전체 파이프라인.

흐름: 질의 유형 판단(query_router) -> MCP 검색/필터(mcp_client)
      -> 각 결과 본문 조회(mcp_client) -> LLM 요약(summarizer)

Tool 이름은 실제 `list_tools()` 실행 결과로 확인 완료 (mcp_client.py 참고,
"API-post-search" / "API-query-data-source" / "API-retrieve-page-markdown"
등 OpenAPI operationId 기반 이름). 다만 각 tool의 정확한 응답 JSON 모양은
아직 실제 호출로 검증하지 못했다 — `_extract_pages`, `_extract_markdown`
안의 파싱 로직은 Notion REST API 응답 스키마를 근거로 작성했으며, 실제
실행 결과를 보고 조정해야 할 수 있다 (태스크 #10에서 골든셋으로 검증).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .config import NOTION_DATA_SOURCE_ID
from .mcp_client import NotionMCPClient
from .query_router import ParsedQuery, QueryType, classify_query, clean_search_query
from .summarizer import summarize_page

MAX_RESULTS = 5


@dataclass
class SearchResult:
    title: str
    summary: str
    notion_url: str
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MCP 응답 파싱 헬퍼
# ---------------------------------------------------------------------------

def _tool_result_to_obj(result: Any) -> Any:
    """MCP CallToolResult -> 파이썬 dict/list/str.

    notion-mcp-server는 OpenAPI 스펙 기반으로 자동 생성된 서버라, 대부분의
    tool 결과가 `content[0].text`에 JSON 문자열로 담겨 온다. 최신 MCP
    스펙에서는 `structuredContent`로 구조화된 값이 바로 오는 경우도 있어
    두 경로를 모두 시도한다.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if not content:
        return None

    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 순수 텍스트(마크다운 등)로 오는 tool은 그대로 문자열 반환
        return text


def _get_title(properties: dict[str, Any]) -> str:
    """Notion 페이지 properties에서 title 속성을 찾아 문자열로 합친다."""
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            rich_text = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in rich_text) or "(제목 없음)"
    return "(제목 없음)"


def _normalize_title(s: str) -> str:
    """제목 비교용 정규화: 앞뒤 공백과 끝의 구두점(?!.…~) 차이는 무시한다.

    골든셋 케이스: "...불가피했는가 페이지 요약해줘" 질의가 물음표 없이
    들어와도 실제 제목 "...불가피했는가?"와 같은 페이지로 매칭되어야 한다.
    """
    return re.sub(r"[\s?!.…~]+$", "", s.strip())


def _get_tags(properties: dict[str, Any]) -> list[str]:
    """select/multi_select/학기(rich_text) 속성값들을 배지용 태그로 뽑는다.

    "학기"는 select처럼 보이지만 실제 스키마는 rich_text다 (2026-07-27,
    실제 API-post-search 응답으로 검증). 값이 비어있지 않을 때만 태그에 포함한다.
    """
    tags: list[str] = []
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        ptype = prop.get("type")
        if ptype == "select" and prop.get("select"):
            tags.append(prop["select"]["name"])
        elif ptype == "multi_select":
            tags.extend(item["name"] for item in prop.get("multi_select", []))
        elif ptype == "rich_text" and name == "학기":
            text = "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
            if text:
                tags.append(text)
    return tags


def _extract_pages(raw: Any) -> list[dict[str, Any]]:
    """search / query-data-source 응답에서 {id, title, url, tags} 리스트를 뽑는다."""
    obj = _tool_result_to_obj(raw)
    if not isinstance(obj, dict):
        return []

    results = obj.get("results", [])
    pages = []
    for item in results:
        if not isinstance(item, dict) or item.get("object") not in ("page", None):
            continue
        properties = item.get("properties", {})
        pages.append(
            {
                "id": item.get("id"),
                "title": _get_title(properties) if properties else item.get("title", "(제목 없음)"),
                "url": item.get("url", ""),
                "tags": _get_tags(properties) if properties else [],
            }
        )
    return pages


def _extract_markdown(raw: Any) -> str:
    obj = _tool_result_to_obj(raw)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # 문서화된 형태: {"markdown": "..."} 혹은 {"content": "..."}
        return obj.get("markdown") or obj.get("content") or ""
    return ""


# ---------------------------------------------------------------------------
# FILTER 유형: 자연어 필터 후보 -> Notion API filter 객체
# ---------------------------------------------------------------------------

def _resolve_relative_date(hint: str) -> dict[str, str] | None:
    """"지난달" 같은 상대 날짜 힌트를 Notion date filter 조건으로 변환.

    Notion은 past_week/past_month/past_year 같은 내장 상대 필터를 지원하므로
    가능하면 그걸 쓰고, "YYYY년 M월"처럼 명시적인 연월은 직접 범위를 계산한다.
    """
    if hint in ("지난달",):
        return {"past_month": {}}
    if hint in ("지난주", "이번주"):
        return {"past_week": {}}
    if hint in ("올해", "작년"):
        return {"past_year": {}}

    m = re.match(r"(\d{2,4})\s*년\s*(\d{1,2})\s*월", hint)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if year < 100:
            year += 2000
        start = date(year, month, 1)
        end = date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)
        return {"on_or_after": start.isoformat(), "on_or_before": end.isoformat()}
    return None


def build_notion_filter(filters: dict[str, str]) -> dict[str, Any] | None:
    """query_router가 뽑은 필터 후보를 query-data-source용 filter 객체로 변환.

    속성 이름("학년", "다중 선택", "날짜", "학기")은 golden_set/queries.md에
    정리된 샘플 데이터셋 스키마 기준. 팀 데이터셋의 실제 속성 이름이 다르면
    이 매핑만 바꾸면 된다.
    """
    conditions: list[dict[str, Any]] = []

    if grade := filters.get("학년"):
        conditions.append({"property": "학년", "select": {"equals": grade}})
    if subject := filters.get("과목"):
        conditions.append({"property": "다중 선택", "multi_select": {"contains": subject}})
    if semester := filters.get("학기"):
        # 실제 스키마 확인 결과 "학기"는 select가 아니라 rich_text 속성이었다
        # (2026-07-27, 실제 API-post-search 응답으로 검증).
        conditions.append({"property": "학기", "rich_text": {"equals": semester}})
    if date_hint := filters.get("날짜"):
        if date_cond := _resolve_relative_date(date_hint):
            conditions.append({"property": "날짜", "date": date_cond})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"and": conditions}


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------

_FALLBACK_SUMMARY_LEN = 150


def _summarize_or_fallback(title: str, markdown: str) -> str:
    """Claude API로 요약하되, 실패하면(크레딧 부족/키 없음/네트워크 오류 등)
    본문 앞부분을 잘라 보여주는 것으로 대체한다.

    검색·MCP 연동 자체는 Claude API 없이도 확인할 수 있어야 하므로, 결제
    문제로 요약 호출이 막혀 있어도 파이프라인 전체가 죽지 않게 한다.
    """
    if not markdown:
        return "본문을 불러오지 못했어요."
    try:
        return summarize_page(title, markdown)
    except Exception as e:  # noqa: BLE001 — 크레딧 부족(BadRequestError) 등 모든 실패를 폴백 처리
        excerpt = markdown.strip().replace("\n", " ")[:_FALLBACK_SUMMARY_LEN]
        return f"[AI 요약 실패 - 원문 일부만 표시: {e}]\n{excerpt}..."


async def _fetch_candidate_pages(session, parsed: ParsedQuery) -> list[dict[str, Any]]:
    if parsed.query_type == QueryType.FILTER:
        if not NOTION_DATA_SOURCE_ID:
            raise RuntimeError(
                "FILTER 유형 검색을 쓰려면 .env에 NOTION_DATA_SOURCE_ID를 설정해야 합니다. "
                "NotionMCPClient().search(...) 또는 retrieve_database(...)로 "
                "'수업 자료' 데이터소스 ID를 한 번 조회해서 채워 넣으세요."
            )
        notion_filter = build_notion_filter(parsed.filters)
        args: dict[str, Any] = {"data_source_id": NOTION_DATA_SOURCE_ID}
        if notion_filter:
            args["filter"] = notion_filter
        raw = await session.call_tool("API-query-data-source", args)
    else:
        # TOPIC / TITLE 둘 다 전체 워크스페이스 검색(API-post-search)을 사용한다.
        # Notion search는 의미 기반이 아니라 단순 텍스트 매칭에 가까워서,
        # 자연어 문장을 그대로 넘기면 제목과 거의 안 겹쳐 엉뚱한 결과가 나온다
        # (실사용 테스트로 확인함 — golden_set/queries.md 참고). 그래서
        # "찾아줘"/"관련"/"자료" 같은 요청 표현을 제거한 핵심 키워드로 검색한다.
        search_query = clean_search_query(parsed.raw_query)
        raw = await session.call_tool("API-post-search", {"query": search_query})

    pages = _extract_pages(raw)

    if parsed.query_type != QueryType.FILTER:
        # Notion search는 단어 단위로도 느슨하게 매칭한다 (예: "학교생활 챗봇
        # 만들기"로 검색해도 "생활"이나 "만들기"만 겹치는 무관한 페이지가
        # 같이 나옴 — 실사용 테스트로 확인). 검색 결과 중 제목이 검색어와
        # (구두점 차이만 무시하고) 정확히 일치하는 페이지가 있으면, 그건
        # 사용자가 찾는 그 페이지일 가능성이 매우 높으므로 그 결과만 남긴다.
        #
        # query_router의 TOPIC/TITLE 분류에 기대지 않고 항상 이 검사를 하는
        # 이유: LLM 분류가 안 될 때(크레딧 부족 등) 쓰는 _heuristic_classify는
        # "학교생활 챗봇 만들기"처럼 계획안/교안/퀴즈 같은 문서유형 접미사가
        # 없는 실제 제목을 TITLE이 아니라 TOPIC으로 잘못 분류하는 경우가 있다
        # (실사용 테스트로 확인). 분류 결과와 무관하게 정확히 일치하는 제목이
        # 있으면 그걸 우선하는 편이 더 견고하다.
        target = _normalize_title(clean_search_query(parsed.raw_query))
        exact_matches = [p for p in pages if _normalize_title(p["title"]) == target]
        if exact_matches:
            return exact_matches

    return pages


async def search_and_summarize(query: str) -> list[SearchResult]:
    """자연어 질의를 받아 검색+요약된 결과 리스트를 반환한다."""
    parsed = classify_query(query)
    client = NotionMCPClient()

    async with client.session() as session:
        pages = await _fetch_candidate_pages(session, parsed)
        pages = pages[:MAX_RESULTS]
        if not pages:
            return []

        results: list[SearchResult] = []
        for page in pages:
            md_raw = await session.call_tool("API-retrieve-page-markdown", {"page_id": page["id"]})
            markdown = _extract_markdown(md_raw)
            summary = _summarize_or_fallback(page["title"], markdown)
            results.append(
                SearchResult(
                    title=page["title"],
                    summary=summary,
                    notion_url=page["url"],
                    tags=page["tags"],
                )
            )
        return results
