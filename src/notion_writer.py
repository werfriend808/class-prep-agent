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
만들 수 있는 권한이 있어야 한다. (아직 실제 호출로 검증 못함 — 크레딧 없이도
여기까지는 테스트 가능하니, Notion 연결만 해두면 이 부분은 지금 확인 가능.)
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
        page_obj = _tool_result_to_obj(create_result)
        page_id = _extract_page_id(page_obj)
        if not page_id:
            raise NotionWriteError("Notion 페이지 생성에 실패했어요 (응답에서 page_id를 찾지 못했어요).")

        await session.call_tool(
            "API-update-page-markdown",
            {"page_id": page_id, "markdown": markdown},
        )

    return {"page_id": page_id, "url": _page_url(page_obj, page_id)}
