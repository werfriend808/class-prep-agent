"""lesson_plan.py 단위 테스트.

generate_lesson_plan()의 실제 LLM 호출 부분은 lesson_plan.complete(llm.py가
제공하는 provider-무관 어댑터)를 가짜 함수로 바꿔치기해서(테스트 파일 내에서
수동 monkeypatch, 저장/복원 방식은 test_pipeline.py의 test_summarize_or_fallback_*
테스트와 동일한 스타일) 네트워크 없이 검증한다. provider가 Claude든 클로바든
lesson_plan.py 입장에서는 complete(prompt, max_tokens) -> str 하나만 보이므로,
여기서는 provider 분기 자체는 다루지 않는다 (그건 test_llm.py에서 확인).
"""
import json

import src.lesson_plan as lesson_plan
from src.lesson_plan import (
    PLAN_SECTIONS,
    LessonPlanError,
    _build_prompt,
    _parse_plan_json,
    _stringify_section,
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


def test_stringify_section_leaves_plain_string_alone():
    assert _stringify_section("  이미 문자열  ") == "이미 문자열"


def test_stringify_section_converts_list_to_bullets():
    result = _stringify_section(["첫째", "둘째"])
    assert result == "- 첫째\n- 둘째"


def test_stringify_section_converts_nested_dict_to_bullets():
    # 실제로 클로바가 평가 루브릭을 이런 중첩 dict로 돌려준 적이 있었다.
    rubric = {"내용 이해도": {"완벽히 이해함": 5, "보통임": 3}}
    result = _stringify_section(rubric)
    assert result == "- 내용 이해도: 완벽히 이해함(5), 보통임(3)"


def test_parse_plan_json_normalizes_non_string_sections():
    # 실제로 겪은 케이스 재현: LLM이 문자열 대신 리스트/딕셔너리로 응답한 경우
    # ['항목1', '항목2'] 같은 파이썬 문법이 그대로 노출되면 안 된다.
    data = {k: f"{k} 내용" for k in PLAN_SECTIONS}
    data["핵심_개념"] = ["산업화", "환경오염"]
    data["평가_루브릭"] = {"참여도": {"우수": 5, "보통": 3}}
    parsed = _parse_plan_json(json.dumps(data))
    assert parsed["핵심_개념"] == "- 산업화\n- 환경오염"
    assert "[" not in parsed["핵심_개념"]
    assert "{" not in parsed["평가_루브릭"]


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

    original = lesson_plan.complete
    lesson_plan.complete = lambda prompt, max_tokens=2000: fake_text
    try:
        plan = generate_lesson_plan(subject="사회", topic="환경 보전과 개발", grade="고1")
    finally:
        lesson_plan.complete = original

    for section in PLAN_SECTIONS:
        assert section in plan
    assert plan["subject"] == "사회"
    assert plan["topic"] == "환경 보전과 개발"
    assert "ncic_references" in plan
    assert isinstance(plan["ncic_references"], list)


def test_generate_lesson_plan_wraps_api_errors_as_lesson_plan_error():
    def _boom(prompt, max_tokens=2000):
        raise RuntimeError("credit balance too low")

    original = lesson_plan.complete
    lesson_plan.complete = _boom
    try:
        try:
            generate_lesson_plan(subject="사회", topic="환경 보전", grade="고1")
        except LessonPlanError as e:
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("LessonPlanError가 발생해야 함")
    finally:
        lesson_plan.complete = original
