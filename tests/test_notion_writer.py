"""notion_writer.py 단위 테스트.

save_lesson_plan_to_notion()의 실제 MCP 호출 부분은 실전 1의 test_pipeline.py
(_FakeSession 방식)처럼 네트워크 없이 검증하기 어려운 부분(실제 notion-mcp-server
프로세스가 필요)이라, 여기서는 순수 로직(마크다운 변환, 응답 파싱 헬퍼, 설정 누락
시의 예외 처리)만 다룬다. 실제 페이지 생성은 로컬에서 Notion 연결 후 수동으로
확인한다.
"""
import asyncio

import src.notion_writer as notion_writer
from src.notion_writer import NotionWriteError, _extract_page_id, _page_url, plan_to_markdown


def _sample_plan() -> dict:
    return {
        "subject": "사회",
        "grade": "고1",
        "topic": "환경 보전과 개발",
        "자료_개요": "개요",
        "수업_목표": "목표",
        "배경_읽기_자료": "배경 자료",
        "핵심_개념": "개념",
        "토론_쟁점": "쟁점",
        "수업_흐름": "흐름",
        "학생_활동지_예시": "활동지",
        "평가_루브릭": "루브릭",
        "ncic_references": ["[10통사1-01-01] 성취기준 텍스트 (출처: x.pdf)"],
    }


def test_plan_to_markdown_includes_all_sections():
    md = plan_to_markdown(_sample_plan())
    assert "환경 보전과 개발" in md
    assert "## 자료 개요" in md
    assert "## 평가 루브릭" in md
    assert "## NCIC 교육과정 근거" in md
    assert "10통사1-01-01" in md


def test_plan_to_markdown_omits_references_section_when_empty():
    plan = _sample_plan()
    plan["ncic_references"] = []
    md = plan_to_markdown(plan)
    assert "NCIC 교육과정 근거" not in md


def test_extract_page_id_from_dict():
    assert _extract_page_id({"id": "abc-123"}) == "abc-123"


def test_extract_page_id_returns_none_for_non_dict():
    assert _extract_page_id("문자열 응답") is None
    assert _extract_page_id(None) is None


def test_page_url_prefers_response_url():
    assert _page_url({"url": "https://notion.so/real-url"}, "abc123") == "https://notion.so/real-url"


def test_page_url_falls_back_to_constructed_url_without_hyphens():
    url = _page_url({}, "abc-123-def")
    assert url == "https://www.notion.so/abc123def"


def test_save_lesson_plan_to_notion_raises_when_parent_id_missing():
    original = notion_writer.NOTION_LESSON_PLAN_PARENT_ID
    notion_writer.NOTION_LESSON_PLAN_PARENT_ID = ""
    try:
        try:
            asyncio.run(notion_writer.save_lesson_plan_to_notion(_sample_plan()))
        except NotionWriteError as e:
            assert "NOTION_LESSON_PLAN_PARENT_ID" in str(e)
        else:
            raise AssertionError("NotionWriteError가 발생해야 함")
    finally:
        notion_writer.NOTION_LESSON_PLAN_PARENT_ID = original
