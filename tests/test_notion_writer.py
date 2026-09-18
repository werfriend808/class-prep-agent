"""notion_writer.py 단위 테스트.

save_lesson_plan_to_notion()의 실제 MCP 호출 부분은 실전 1의 test_pipeline.py
(_FakeSession 방식)처럼 네트워크 없이 검증하기 어려운 부분(실제 notion-mcp-server
프로세스가 필요)이라, 여기서는 순수 로직(마크다운 변환, 응답 파싱 헬퍼, 설정 누락
시의 예외 처리)만 다룬다. 실제 페이지 생성은 로컬에서 Notion 연결 후 수동으로
확인한다.
"""
import asyncio
from types import SimpleNamespace

import src.notion_writer as notion_writer
from src.notion_writer import NotionWriteError, _extract_page_id, _page_url, _raise_if_tool_error, plan_to_markdown


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


# 2026-08-26: 한 번 완전히 제거했다가(README 13-7 참고) 강사가 보는 자료에는
# 근거가 필요하다는 판단으로 토의·토론에 한해 다시 복원했다(README 13-8 참고).
# Quiz는 여전히 NCIC 근거를 쓰지 않는다.
def test_plan_to_markdown_includes_all_sections():
    md = plan_to_markdown(_sample_plan())
    assert "환경 보전과 개발" in md
    assert "## 자료 개요" in md
    assert "## 평가 루브릭" in md
    assert "## NCIC 교육과정 근거" in md
    assert "[10통사1-01-01]" in md


def test_plan_to_markdown_omits_ncic_section_when_no_references():
    plan = _sample_plan()
    plan["ncic_references"] = []
    md = plan_to_markdown(plan)
    assert "NCIC" not in md


# 2026-09-17 (Phase 3): plan["locale"] == "us"면 영어 섹션 제목/근거 문구로 렌더링된다.
def _sample_plan_us() -> dict:
    return {
        "subject": "Math",
        "grade": "3",
        "topic": "Fractions",
        "locale": "us",
        "overview": "Overview text",
        "objectives": "Objectives text",
        "background_reading": "Background text",
        "key_concepts": "Key concepts text",
        "discussion_issues": "Discussion issues text",
        "lesson_flow": "Lesson flow text",
        "sample_worksheet": "Sample worksheet text",
        "assessment_rubric": "Assessment rubric text",
        "standards_references": ["[3.NF.1] some standard text (Source: Common Core ...)"],
    }


def test_plan_to_markdown_us_locale_uses_english_titles_and_references():
    md = plan_to_markdown(_sample_plan_us())
    assert "Fractions" in md
    assert "## Overview" in md
    assert "## Assessment Rubric" in md
    assert "## Common Core Standards" in md
    assert "[3.NF.1]" in md
    # 한국어 섹션 제목/근거 문구가 섞여 들어가면 안 된다.
    assert "자료 개요" not in md
    assert "NCIC" not in md


def test_plan_to_markdown_us_locale_omits_standards_section_when_no_references():
    plan = _sample_plan_us()
    plan["standards_references"] = []
    md = plan_to_markdown(plan)
    assert "Common Core Standards" not in md


def test_plan_to_markdown_missing_locale_key_defaults_to_korean():
    # generate_lesson_plan()이 없던 예전 dict(또는 다른 곳에서 만든 plan dict)도
    # locale 필드가 없으면 그냥 기존 한국어 렌더링으로 떨어져야 한다.
    plan = _sample_plan()
    assert "locale" not in plan
    md = plan_to_markdown(plan)
    assert "## 자료 개요" in md


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


def test_raise_if_tool_error_does_nothing_when_not_error():
    result = SimpleNamespace(isError=False, content=[])
    _raise_if_tool_error(result, "테스트 액션")  # 예외 없이 통과해야 함


def test_raise_if_tool_error_raises_with_message_from_content():
    # 실제로 겪은 버그 재현: API-update-page-markdown이 검증 에러를 돌려줘도
    # 예전 코드는 이 결과를 무시해서 페이지 본문이 비는 채로 "성공"이라고 나왔다.
    result = SimpleNamespace(
        isError=True,
        content=[SimpleNamespace(text='{"status":400,"message":"body.type should be defined"}')],
    )
    try:
        _raise_if_tool_error(result, "Notion 페이지 본문 작성")
    except NotionWriteError as e:
        assert "Notion 페이지 본문 작성" in str(e)
        assert "body.type should be defined" in str(e)
    else:
        raise AssertionError("NotionWriteError가 발생해야 함")


def test_raise_if_tool_error_detects_error_hidden_in_content_json():
    # 실제로 겪은 두 번째 버그: notion-mcp-server는 Notion API 검증 에러가 나도
    # isError를 True로 세팅하지 않고, content JSON 안에만 {"object":"error",...}
    # 형태로 담아 보낸다. isError만 보면 이 실패를 놓친다.
    result = SimpleNamespace(
        isError=False,
        content=[
            SimpleNamespace(
                text='{"status":400,"object":"error","message":"body.insert_content should be an object"}'
            )
        ],
    )
    try:
        _raise_if_tool_error(result, "Notion 페이지 본문 작성")
    except NotionWriteError as e:
        assert "body.insert_content should be an object" in str(e)
    else:
        raise AssertionError("NotionWriteError가 발생해야 함")


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
