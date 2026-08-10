"""Notion 페이지 생성 MCP 연동 (실전 프로젝트 2: "Notion 페이지 생성 및 링크 반환").

실전 1은 읽기 tool(API-post-search, API-query-data-source,
API-retrieve-page-markdown)만 썼지만, 여기서는 쓰기 tool 두 개를 쓴다 — 둘 다
실전 1에서 `list_tools()`로 이미 확인해둔 실제 tool 이름이다 (mcp_client.py
docstring 참고):
  - "API-post-page": 새 페이지 생성 (parent + properties)
  - "API-update-page-markdown": 생성한 페이지의 본문을 마크다운으로 채워넣기
    (Notion 블록 JSON을 직접 조립할 필요 없이 마크다운 문자열을 그대로 보낼 수
    있어서 훨씬 간단하다)

사전 조건: `.env`의 NOTION_LESSON_PLAN_PARENT_ID가 가리키는 Notion 페이지에
Integration이 연결(Connections)되어 있어야 하고, 그 페이지 하위에 페이지를
만들 수 있는 권한이 있어야 한다.

`API-update-page-markdown` 실제 스키마 (scripts/debug_notion_tools.py로 확인,
2026-08-10): 필수 파라미터가 {page_id, type} 두 개고, `type`은
"replace_content"(페이지 전체 덮어쓰기, 권장) / "update_content"(부분
find-and-replace, 권장) / "insert_content" / "replace_content_range"
(뒤의 둘은 deprecated) 중 하나다. 새로 만든 빈 페이지에 계획안 전체를 한 번에
쓰는 용도이므로 "replace_content"를 쓴다.

**주의 (실제로 겪은 두 가지 버그, scripts/debug_notion_tools.py로 재현/확인):**
1. `insert_content`를 문자열로 보내면(`"insert_content": "마크다운..."`)
   스키마상으로는 허용되는 것처럼 보이지만 실제로는 "body.insert_content
   should be an object" 검증 에러가 난다 — 객체 형태
   (`{"content": ..., "position": {"type": "end"}}`)로 보내야 한다.
2. **notion-mcp-server는 Notion API 검증 에러가 나도 MCP `isError` 플래그를
   True로 세팅하지 않는다** — 에러가 `content[0].text` 안에
   `{"object":"error","status":400,...}` 형태의 JSON으로만 담겨 온다. 그래서
   `isError`만 확인하면 실패를 놓친다 (처음에 이걸 놓쳐서 페이지는 생성되는데
   본문은 계속 비어있는 채로 "성공"이라고 나왔었다). `_raise_if_tool_error`가
   `isError`와 응답 JSON의 `object == "error"` 둘 다 확인하는 이유.
"""
from __future__ import annotations

from typing import Any

from .config import NOTION_LESSON_PLAN_PARENT_ID
from .lesson_plan import PLAN_SECTIONS
from .mcp_client import NotionMCPClient
from .pipeline import _tool_result_to_obj

_SECTION_TITLES = {
    "자료_개요": "자료 개요",
    "수업_목표": "수업 목표",
    "배경_읽기_자료": "배경 읽기 자료",
    "핵심_개념": "핵심 개념",
    "토론_쟁점": "토론 쟁점",
    "수업_흐름": "수업 흐름",
    "학생_활동지_예시": "학생 활동지 예시",
    "평가_루브릭": "평가 루브릭",
}


class NotionWriteError(RuntimeError):
    """페이지 생성/본문 작성 실패를 UI에 알리기 위한 예외."""


def plan_to_markdown(plan: dict) -> str:
    """lesson_plan.generate_lesson_plan()의 결과 dict를 Notion용 마크다운으로 변환."""
    lines = [f"# {plan.get('topic', '')} 토의·토론 수업계획안", ""]
    lines.append(f"**과목**: {plan.get('subject', '')}  |  **대상**: {plan.get('grade', '')}")
    lines.append("")
    for key in PLAN_SECTIONS:
        lines.append(f"## {_SECTION_TITLES.get(key, key)}")
        lines.append(str(plan.get(key, "")))
        lines.append("")

    references = plan.get("ncic_references") or []
    if references:
        lines.append("## NCIC 교육과정 근거")
        for ref in references:
            lines.append(f"- {ref}")
        lines.append("")

    return "\n".join(lines)


def _raise_if_tool_error(result: Any, action: str) -> None:
    """MCP CallToolResult가 에러면 NotionWriteError로 바꿔서 올린다.

    두 겹으로 확인해야 한다:
    1) MCP 레벨 `isError` 플래그
    2) notion-mcp-server가 Notion API 검증 에러를 `isError=False`인 채로
       content JSON 안에 `{"object": "error", ...}` 형태로만 실어 보내는 경우
       (실제로 겪은 버그 — module docstring 참고). 응답을 파싱해서 이 모양인지도
       확인해야 진짜 실패를 놓치지 않는다.
    """
    if getattr(result, "isError", False):
        content = getattr(result, "content", None)
        message = getattr(content[0], "text", None) if content else None
        raise NotionWriteError(f"{action} 실패: {message or result}")

    obj = _tool_result_to_obj(result)
    if isinstance(obj, dict) and obj.get("object") == "error":
        raise NotionWriteError(f"{action} 실패: {obj.get('message', obj)}")


def _extract_page_id(page_obj: Any) -> str | None:
    if isinstance(page_obj, dict):
        return page_obj.get("id")
    return None


def _page_url(page_obj: Any, page_id: str) -> str:
    if isinstance(page_obj, dict) and page_obj.get("url"):
        return page_obj["url"]
    # url이 응답에 없으면 page_id로 Notion 웹 URL을 직접 구성(하이픈 제거)
    compact_id = page_id.replace("-", "")
    return f"https://www.notion.so/{compact_id}"


async def update_lesson_plan_in_notion(page_id: str, plan: dict) -> dict:
    """이미 만들어진 수업계획안 Notion 페이지의 본문을 새 내용으로 덮어쓴다.

    종합 프로젝트의 수정-전파 요구사항: 사용자가 대화로 계획안 수정을
    요청하면 매번 새 페이지를 만드는 게 아니라 같은 page_id의 본문을
    replace_content로 교체해서 "하나의 계획안"이라는 일관성을 유지한다.
    (save_lesson_plan_to_notion은 API-post-page로 새 페이지를 만드는 반면,
    이 함수는 API-update-page-markdown만 호출한다.)
    """
    markdown = plan_to_markdown(plan)

    client = NotionMCPClient()
    async with client.session() as session:
        update_result = await session.call_tool(
            "API-update-page-markdown",
            {"page_id": page_id, "type": "replace_content", "replace_content": {"new_str": markdown}},
        )
        _raise_if_tool_error(update_result, "Notion 페이지 본문 수정")

    return {"page_id": page_id, "url": _page_url({}, page_id)}


async def save_lesson_plan_to_notion(plan: dict, parent_page_id: str | None = None) -> dict:
    """수업계획안을 Notion 페이지로 생성하고 {"page_id", "url"}을 반환한다."""
    parent_id = parent_page_id or NOTION_LESSON_PLAN_PARENT_ID
    if not parent_id:
        raise NotionWriteError(
            ".env에 NOTION_LESSON_PLAN_PARENT_ID가 설정되어 있지 않습니다. "
            "수업계획안을 저장할 Notion 페이지의 ID를 .env에 추가해주세요."
        )

    title = f"{plan.get('topic', '수업계획안')} ({plan.get('subject', '')})"
    markdown = plan_to_markdown(plan)

    client = NotionMCPClient()
    async with client.session() as session:
        create_result = await session.call_tool(
            "API-post-page",
            {
                "parent": {"page_id": parent_id},
                "properties": {"title": {"title": [{"text": {"content": title}}]}},
            },
        )
        _raise_if_tool_error(create_result, "Notion 페이지 생성")
        page_obj = _tool_result_to_obj(create_result)
        page_id = _extract_page_id(page_obj)
        if not page_id:
            raise NotionWriteError("Notion 페이지 생성에 실패했어요 (응답에서 page_id를 찾지 못했어요).")

        update_result = await session.call_tool(
            "API-update-page-markdown",
            {"page_id": page_id, "type": "replace_content", "replace_content": {"new_str": markdown}},
        )
        _raise_if_tool_error(update_result, "Notion 페이지 본문 작성")

    return {"page_id": page_id, "url": _page_url(page_obj, page_id)}
