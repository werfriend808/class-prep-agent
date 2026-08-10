"""worksheet.py 단위 테스트. lesson_plan.py의 test_lesson_plan.py와 같은 스타일
(complete()를 수동 monkeypatch)로, 실제 LLM 호출 없이 검증한다."""
import json

import src.worksheet as worksheet
from src.worksheet import (
    WORKSHEET_SECTIONS,
    WorksheetError,
    _build_prompt,
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
