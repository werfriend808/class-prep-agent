"""pipeline.py의 순수 로직(응답 파싱, 필터 변환)에 대한 단위 테스트.

search_and_summarize()는 실제로 notion-mcp-server(Node.js/npx)와 LLM(Claude
또는 클로바)을 호출하므로 여기서는 다루지 않는다 — 그건 실제 서버가 붙은 로컬 환경에서
수동으로 확인한다(파일 상단 "실제 연동 확인 방법" 참고). 여기서는 네트워크
없이도 항상 결정적으로 통과해야 하는 부분만 검증한다.
"""
import asyncio
from types import SimpleNamespace

import src.pipeline as pipeline
from src.pipeline import (
    _extract_markdown,
    _extract_pages,
    _fetch_candidate_pages,
    _get_tags,
    _get_title,
    _normalize_title,
    _summarize_or_fallback,
    build_notion_filter,
)
from src.query_router import ParsedQuery, QueryType


def _fake_tool_result(json_text: str):
    """MCP CallToolResult 흉내 (content[0].text에 JSON 문자열)."""
    return SimpleNamespace(content=[SimpleNamespace(text=json_text)])


def test_get_title_from_title_property():
    properties = {
        "이름": {
            "type": "title",
            "title": [{"plain_text": "학교생활 "}, {"plain_text": "챗봇 만들기"}],
        }
    }
    assert _get_title(properties) == "학교생활 챗봇 만들기"


def test_get_tags_from_select_and_multi_select():
    properties = {
        "학년": {"type": "select", "select": {"name": "고1"}},
        "다중 선택": {
            "type": "multi_select",
            "multi_select": [{"name": "통합 사회1"}],
        },
    }
    tags = _get_tags(properties)
    assert "고1" in tags
    assert "통합 사회1" in tags


def test_get_tags_includes_semester_rich_text():
    # 실제 응답 검증 결과 "학기"는 select가 아니라 rich_text였다.
    properties = {
        "학기": {
            "type": "rich_text",
            "rich_text": [{"plain_text": "26-1"}],
        }
    }
    assert _get_tags(properties) == ["26-1"]


def test_get_tags_skips_empty_semester():
    properties = {"학기": {"type": "rich_text", "rich_text": []}}
    assert _get_tags(properties) == []


def test_extract_pages_from_search_response():
    raw = _fake_tool_result(
        '{"results": [{"object": "page", "id": "abc123", "url": "https://notion.so/abc123", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "토론수업 계획안"}]}, '
        '"학년": {"type": "select", "select": {"name": "고1"}}}}]}'
    )
    pages = _extract_pages(raw)
    assert len(pages) == 1
    assert pages[0]["id"] == "abc123"
    assert pages[0]["title"] == "토론수업 계획안"
    assert pages[0]["tags"] == ["고1"]


def test_extract_pages_empty_results():
    raw = _fake_tool_result('{"results": []}')
    assert _extract_pages(raw) == []


def test_extract_markdown_from_dict_shape():
    raw = _fake_tool_result('{"markdown": "# 제목\\n본문 내용"}')
    assert _extract_markdown(raw) == "# 제목\n본문 내용"


def test_extract_markdown_from_plain_text_shape():
    raw = SimpleNamespace(content=[SimpleNamespace(text="# 제목\n본문 내용")])
    assert _extract_markdown(raw) == "# 제목\n본문 내용"


def test_build_notion_filter_single_condition():
    filter_obj = build_notion_filter({"학년": "고1"})
    assert filter_obj == {"property": "학년", "select": {"equals": "고1"}}


def test_build_notion_filter_combines_with_and():
    filter_obj = build_notion_filter({"학년": "고1", "과목": "수학"})
    assert filter_obj == {
        "and": [
            {"property": "학년", "select": {"equals": "고1"}},
            {"property": "다중 선택", "multi_select": {"contains": "수학"}},
        ]
    }


def test_build_notion_filter_relative_date():
    filter_obj = build_notion_filter({"과목": "수학", "날짜": "지난달"})
    assert filter_obj == {
        "and": [
            {"property": "다중 선택", "multi_select": {"contains": "수학"}},
            {"property": "날짜", "date": {"past_month": {}}},
        ]
    }


def test_build_notion_filter_empty_when_no_filters():
    assert build_notion_filter({}) is None


def test_build_notion_filter_semester_uses_rich_text():
    filter_obj = build_notion_filter({"학기": "26-1"})
    assert filter_obj == {"property": "학기", "rich_text": {"equals": "26-1"}}


def test_summarize_or_fallback_returns_excerpt_on_api_failure():
    def _boom(title, markdown, max_tokens=300):
        raise RuntimeError("credit balance too low")

    original = pipeline.summarize_page
    pipeline.summarize_page = _boom
    try:
        result = _summarize_or_fallback("제목", "본문 내용입니다.")
    finally:
        pipeline.summarize_page = original
    assert "본문 내용입니다" in result
    assert "요약 실패" in result


def test_summarize_or_fallback_handles_empty_markdown():
    assert _summarize_or_fallback("제목", "") == "본문을 불러오지 못했어요."


def test_normalize_title_ignores_trailing_question_mark():
    # 골든셋 케이스: 질의에 물음표가 없어도 실제 제목(물음표 있음)과 매칭되어야 함
    assert _normalize_title("근대화 과정에서 외세의 수용은 불가피했는가") == _normalize_title(
        "근대화 과정에서 외세의 수용은 불가피했는가?"
    )


class _FakeSession:
    """call_tool()이 미리 정해둔 raw 응답을 반환하는 가짜 세션."""

    def __init__(self, raw_response):
        self._raw = raw_response

    async def call_tool(self, name, arguments):
        return self._raw


def test_fetch_candidate_pages_title_filters_to_exact_match():
    # 실사용 테스트로 확인한 문제: Notion search가 "학교생활 챗봇 만들기"로
    # 검색해도 "생활"/"만들기"만 겹치는 무관한 페이지를 같이 반환한다.
    # TITLE 유형은 제목이 정확히 일치하는 페이지만 남겨야 한다.
    raw = _fake_tool_result(
        '{"results": ['
        '{"object": "page", "id": "p1", "url": "u1", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "생활 속 비용 조건을 부등식으로 비교하기"}]}}},'
        '{"object": "page", "id": "p2", "url": "u2", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "학교생활 챗봇 만들기"}]}}}'
        "]}"
    )
    parsed = ParsedQuery(
        query_type=QueryType.TITLE,
        raw_query="학교생활 챗봇 만들기 페이지 요약해줘",
        filters={},
    )
    session = _FakeSession(raw)
    pages = asyncio.run(_fetch_candidate_pages(session, parsed))
    assert len(pages) == 1
    assert pages[0]["title"] == "학교생활 챗봇 만들기"


def test_fetch_candidate_pages_title_falls_back_when_no_exact_match():
    raw = _fake_tool_result(
        '{"results": [{"object": "page", "id": "p1", "url": "u1", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "전혀 다른 제목"}]}}}]}'
    )
    parsed = ParsedQuery(query_type=QueryType.TITLE, raw_query="없는 제목 페이지 요약해줘", filters={})
    session = _FakeSession(raw)
    pages = asyncio.run(_fetch_candidate_pages(session, parsed))
    assert len(pages) == 1  # 정확히 일치하는 게 없어도 결과 자체는 버리지 않음


def test_fetch_candidate_pages_narrows_exact_match_even_when_misclassified_as_topic():
    # 실사용 테스트로 확인한 실제 버그: ANTHROPIC_API_KEY 크레딧이 없어
    # LLM 분류가 실패하면 _heuristic_classify가 "학교생활 챗봇 만들기"처럼
    # 문서유형 접미사가 없는 실제 제목을 TITLE이 아니라 TOPIC으로 잘못
    # 분류한다. 이 좁히기 로직은 TOPIC으로 분류돼도 정확히 일치하는 제목이
    # 있으면 그 결과로 좁혀야 한다 (분류 결과에 의존하지 않아야 함).
    raw = _fake_tool_result(
        '{"results": ['
        '{"object": "page", "id": "p1", "url": "u1", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "생활 속 비용 조건을 부등식으로 비교하기"}]}}},'
        '{"object": "page", "id": "p2", "url": "u2", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "통합사회 토론 자료 만들기"}]}}},'
        '{"object": "page", "id": "p3", "url": "u3", '
        '"properties": {"이름": {"type": "title", "title": [{"plain_text": "학교생활 챗봇 만들기"}]}}}'
        "]}"
    )
    parsed = ParsedQuery(
        query_type=QueryType.TOPIC,  # 잘못 분류된 상황을 그대로 재현
        raw_query="학교생활 챗봇 만들기 페이지 요약해줘",
        filters={},
    )
    session = _FakeSession(raw)
    pages = asyncio.run(_fetch_candidate_pages(session, parsed))
    assert len(pages) == 1
    assert pages[0]["title"] == "학교생활 챗봇 만들기"
