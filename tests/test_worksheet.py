"""worksheet.py 단위 테스트. lesson_plan.py의 test_lesson_plan.py와 같은 스타일
(complete()를 수동 monkeypatch)로, 실제 LLM 호출 없이 검증한다."""
import json

import src.worksheet as worksheet
from src.worksheet import (
    WORKSHEET_SECTIONS,
    WORKSHEET_SECTIONS_US,
    WorksheetError,
    _build_prompt,
    _build_prompt_us,
    _parse_worksheet_json,
    generate_worksheet,
    worksheet_to_text,
)


def _sample_plan() -> dict:
    return {
        "subject": "사회",
        "grade": "고1",
        "topic": "환경 보전과 개발",
        "토론_쟁점": "개발과 보전 중 우선순위",
        "수업_흐름": "도입-전개-정리",
    }


def _fake_worksheet_json() -> str:
    return json.dumps({k: f"{k} 내용" for k in WORKSHEET_SECTIONS})


def test_build_prompt_includes_plan_context_and_revision_note():
    prompt = _build_prompt(_sample_plan(), None)
    assert "환경 보전과 개발" in prompt
    assert "개발과 보전 중 우선순위" in prompt
    assert "수정 요청" not in prompt

    prompt_with_revision = _build_prompt(_sample_plan(), "더 쉽게 해줘")
    assert "수정 요청" in prompt_with_revision
    assert "더 쉽게 해줘" in prompt_with_revision


def test_parse_worksheet_json_success():
    parsed = _parse_worksheet_json(_fake_worksheet_json())
    assert set(parsed.keys()) == set(WORKSHEET_SECTIONS)


def test_parse_worksheet_json_handles_code_fence():
    fenced = f"```json\n{_fake_worksheet_json()}\n```"
    parsed = _parse_worksheet_json(fenced)
    assert set(parsed.keys()) == set(WORKSHEET_SECTIONS)


def test_parse_worksheet_json_raises_on_invalid_json():
    try:
        _parse_worksheet_json("JSON 아님")
    except WorksheetError:
        pass
    else:
        raise AssertionError("WorksheetError가 발생해야 함")


def test_parse_worksheet_json_raises_on_missing_sections():
    incomplete = json.dumps({"활동_안내": "안내만 있음"})
    try:
        _parse_worksheet_json(incomplete)
    except WorksheetError as e:
        assert "배경_자료_요약" in str(e)
    else:
        raise AssertionError("WorksheetError가 발생해야 함")


def test_parse_worksheet_json_normalizes_list_sections():
    # lesson_plan.py에서 실제로 겪은 것과 같은 케이스: LLM이 문자열 대신 리스트로 응답.
    data = {k: f"{k} 내용" for k in WORKSHEET_SECTIONS}
    data["토론_질문"] = ["질문1", "질문2"]
    parsed = _parse_worksheet_json(json.dumps(data))
    assert parsed["토론_질문"] == "- 질문1\n- 질문2"


def test_generate_worksheet_success():
    fake_text = _fake_worksheet_json()

    original = worksheet.complete
    worksheet.complete = lambda prompt, max_tokens=1500: fake_text
    try:
        result = generate_worksheet(_sample_plan())
    finally:
        worksheet.complete = original

    for section in WORKSHEET_SECTIONS:
        assert section in result
    assert result["topic"] == "환경 보전과 개발"
    assert result["subject"] == "사회"


def test_generate_worksheet_wraps_api_errors():
    def _boom(prompt, max_tokens=1500):
        raise RuntimeError("credit balance too low")

    original = worksheet.complete
    worksheet.complete = _boom
    try:
        try:
            generate_worksheet(_sample_plan())
        except WorksheetError as e:
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("WorksheetError가 발생해야 함")
    finally:
        worksheet.complete = original


def test_generate_worksheet_retries_once_after_malformed_response():
    calls = {"count": 0}

    def _flaky(prompt, max_tokens=1500):
        calls["count"] += 1
        if calls["count"] == 1:
            return "JSON 아닌 응답"
        return _fake_worksheet_json()

    original = worksheet.complete
    worksheet.complete = _flaky
    try:
        result = generate_worksheet(_sample_plan())
    finally:
        worksheet.complete = original

    assert calls["count"] == 2
    for section in WORKSHEET_SECTIONS:
        assert section in result


def test_generate_worksheet_gives_up_after_second_failure():
    calls = {"count": 0}

    def _always_broken(prompt, max_tokens=1500):
        calls["count"] += 1
        return "계속 JSON 아님"

    original = worksheet.complete
    worksheet.complete = _always_broken
    try:
        try:
            generate_worksheet(_sample_plan())
        except WorksheetError:
            pass
        else:
            raise AssertionError("WorksheetError가 발생해야 함")
    finally:
        worksheet.complete = original

    assert calls["count"] == 2


def test_worksheet_to_text_includes_all_sections():
    data = {k: f"{k} 내용" for k in WORKSHEET_SECTIONS}
    data.update(topic="환경 보전", subject="사회", grade="고1")
    text = worksheet_to_text(data)
    assert "환경 보전 학생 활동지" in text
    assert "배경 자료 요약" in text
    assert "모둠 토의 기록표" in text
    assert "토론_질문 내용" in text


# 2026-09-18: locale="us" 경로 -- 영어 프롬프트/섹션 키를 쓰고, generate_worksheet()가
# 반환하는 dict에 "locale" 필드가 채워지는지, worksheet_to_text()가 그 필드를 보고
# 영어로 렌더링하는지 확인한다. 기존 ko 기본 경로(locale 인자를 안 주는 모든 테스트)는
# 이 파일에서 하나도 안 건드렸으니 그대로 회귀 검증이 된다.
def _sample_plan_us() -> dict:
    return {
        "subject": "Math",
        "grade": "8",
        "topic": "Linear Equations",
        "discussion_issues": "Should we prioritize speed or accuracy when solving equations?",
        "lesson_flow": "Intro-Explore-Discuss-Wrap up",
    }


def _fake_worksheet_json_us() -> str:
    return json.dumps({k: f"{k} content" for k in WORKSHEET_SECTIONS_US})


def test_build_prompt_us_includes_plan_context_and_revision_note():
    prompt = _build_prompt_us(_sample_plan_us(), None)
    assert "Linear Equations" in prompt
    assert "Should we prioritize speed or accuracy" in prompt
    assert "Revision request" not in prompt

    prompt_with_revision = _build_prompt_us(_sample_plan_us(), "make it easier")
    assert "Revision request" in prompt_with_revision
    assert "make it easier" in prompt_with_revision


def test_parse_worksheet_json_us_success():
    parsed = _parse_worksheet_json(_fake_worksheet_json_us(), locale="us")
    assert set(parsed.keys()) == set(WORKSHEET_SECTIONS_US)


def test_parse_worksheet_json_us_raises_english_message_on_invalid_json():
    try:
        _parse_worksheet_json("not JSON", locale="us")
    except WorksheetError as e:
        assert "Couldn't parse" in str(e)
    else:
        raise AssertionError("WorksheetError가 발생해야 함")


def test_parse_worksheet_json_us_raises_english_message_on_missing_sections():
    incomplete = json.dumps({"activity_instructions": "only this one"})
    try:
        _parse_worksheet_json(incomplete, locale="us")
    except WorksheetError as e:
        assert "background_summary" in str(e)
        assert "missing required fields" in str(e)
    else:
        raise AssertionError("WorksheetError가 발생해야 함")


def test_generate_worksheet_us_success_sets_locale_and_english_sections():
    fake_text = _fake_worksheet_json_us()

    original = worksheet.complete
    worksheet.complete = lambda prompt, max_tokens=1500: fake_text
    try:
        result = generate_worksheet(_sample_plan_us(), locale="us")
    finally:
        worksheet.complete = original

    for section in WORKSHEET_SECTIONS_US:
        assert section in result
    assert result["locale"] == "us"
    assert result["topic"] == "Linear Equations"
    assert result["subject"] == "Math"


def test_generate_worksheet_us_wraps_api_errors_in_english():
    def _boom(prompt, max_tokens=1500):
        raise RuntimeError("credit balance too low")

    original = worksheet.complete
    worksheet.complete = _boom
    try:
        try:
            generate_worksheet(_sample_plan_us(), locale="us")
        except WorksheetError as e:
            assert "Failed to generate the student worksheet" in str(e)
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("WorksheetError가 발생해야 함")
    finally:
        worksheet.complete = original


def test_generate_worksheet_ko_locale_is_default_and_unaffected():
    # locale을 안 주면 기존 한국어 동작 그대로다 -- 명시적으로 한 번 더 확인.
    fake_text = _fake_worksheet_json()
    original = worksheet.complete
    worksheet.complete = lambda prompt, max_tokens=1500: fake_text
    try:
        result = generate_worksheet(_sample_plan())
    finally:
        worksheet.complete = original
    assert result["locale"] == "ko"
    for section in WORKSHEET_SECTIONS:
        assert section in result


def test_worksheet_to_text_us_includes_all_sections():
    data = {k: f"{k} content" for k in WORKSHEET_SECTIONS_US}
    data.update(topic="Linear Equations", subject="Math", grade="8", locale="us")
    text = worksheet_to_text(data)
    assert "Linear Equations Student Worksheet" in text
    assert "Background Summary" in text
    assert "Group Discussion Notes" in text
    assert "discussion_questions content" in text
