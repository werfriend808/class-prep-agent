"""lesson_plan.py 단위 테스트.

generate_lesson_plan()의 실제 Claude API 호출 부분은 lesson_plan.get_client를
가짜 클라이언트로 바꿔치기해서(테스트 파일 내에서 수동 monkeypatch, 저장/복원
방식은 test_pipeline.py의 test_summarize_or_fallback_* 테스트와 동일한 스타일)
네트워크 없이 검증한다.
"""
import json
from types import SimpleNamespace

import src.lesson_plan as lesson_plan
from src.lesson_plan import (
    PLAN_SECTIONS,
    LessonPlanError,
    _build_prompt,
    _parse_plan_json,
    extract_keywords,
    generate_lesson_plan,
)


def test_extract_keywords_dedupes_and_filters_short_tokens():
    keywords = extract_keywords("환경 환경 보전과 개발 중 무엇을 우선해야 하는가")
    assert keywords.count("환경") == 1  # 중복 제거
    assert "중" not in keywords  # 1글자 토큰은 제외


def test_build_prompt_includes_ncic_context_and_revision_note():
    records = [{"code": "10통사1-01-01", "text": "성취기준 텍스트"}]
    prompt = _build_prompt("사회", "고1", "환경 보전", records, None)
    assert "10통사1-01-01" in prompt
    assert "환경 보전" in prompt
    assert "수정 요청" not in prompt

    prompt_with_revision = _build_prompt("사회", "고1", "환경 보전", records, "더 짧게 해줘")
    assert "수정 요청" in prompt_with_revision
    assert "더 짧게 해줘" in prompt_with_revision


def _fake_plan_json() -> str:
    return json.dumps({k: f"{k} 내용" for k in PLAN_SECTIONS})


def test_parse_plan_json_success():
    parsed = _parse_plan_json(_fake_plan_json())
    assert set(parsed.keys()) == set(PLAN_SECTIONS)


def test_parse_plan_json_handles_code_fence():
    fenced = f"```json\n{_fake_plan_json()}\n```"
    parsed = _parse_plan_json(fenced)
    assert set(parsed.keys()) == set(PLAN_SECTIONS)


def test_parse_plan_json_raises_on_invalid_json():
    try:
        _parse_plan_json("이건 JSON이 아니에요")
    except LessonPlanError:
        pass
    else:
        raise AssertionError("LessonPlanError가 발생해야 함")


def test_parse_plan_json_raises_on_missing_sections():
    incomplete = json.dumps({"자료_개요": "개요만 있음"})
    try:
        _parse_plan_json(incomplete)
    except LessonPlanError as e:
        assert "수업_목표" in str(e)
    else:
        raise AssertionError("LessonPlanError가 발생해야 함")


def test_generate_lesson_plan_success():
    fake_text = _fake_plan_json()

    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text=fake_text)])

    class _FakeClient:
        messages = _FakeMessages()

    original = lesson_plan.get_client
    lesson_plan.get_client = lambda: _FakeClient()
    try:
        plan = generate_lesson_plan(subject="사회", topic="환경 보전과 개발", grade="고1")
    finally:
        lesson_plan.get_client = original

    for section in PLAN_SECTIONS:
        assert section in plan
    assert plan["subject"] == "사회"
    assert plan["topic"] == "환경 보전과 개발"
    assert "ncic_references" in plan
    assert isinstance(plan["ncic_references"], list)


def test_generate_lesson_plan_wraps_api_errors_as_lesson_plan_error():
    def _boom():
        raise RuntimeError("credit balance too low")

    original = lesson_plan.get_client
    lesson_plan.get_client = _boom
    try:
        try:
            generate_lesson_plan(subject="사회", topic="환경 보전", grade="고1")
        except LessonPlanError as e:
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("LessonPlanError가 발생해야 함")
    finally:
        lesson_plan.get_client = original
