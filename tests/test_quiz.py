"""quiz.py 단위 테스트. lesson_plan.py/worksheet.py 테스트와 같은 스타일로,
complete()를 수동 monkeypatch해서 실제 LLM 호출 없이 검증한다."""
import json

import src.quiz as quiz
from src.quiz import (
    MAX_OPTIONS,
    MIN_OPTIONS,
    QUESTION_COUNT,
    QuizError,
    _build_prompt,
    _parse_quiz_json,
    generate_quiz,
)


def _sample_question(**overrides) -> dict:
    base = {
        "question": "삼각형의 내각의 합은?",
        "options": ["90도", "180도", "270도", "360도"],
        "correct_index": 1,
        "explanation": "삼각형의 세 내각의 합은 항상 180도입니다.",
    }
    base.update(overrides)
    return base


def _raw_question(**overrides) -> dict:
    """LLM이 실제로 반환하는 원본 스키마(정답을 인덱스가 아니라 텍스트로 표시,
    2026-08-26 수정 — 아래 test_parse_quiz_json_* 참고)로 문항 하나를 만든다."""
    base = _sample_question(**overrides)
    correct_index = base.pop("correct_index")
    base["correct_answer"] = base["options"][correct_index]
    return base


def _fake_quiz_json(count: int = QUESTION_COUNT) -> str:
    return json.dumps({"questions": [_raw_question(question=f"문제 {i}") for i in range(count)]})


# 2026-08-26: NCIC 근거 기능 제거(README 18-6-2) — extract_keywords()도
# match_standards() 호출용이었으므로 quiz.py에서 같이 제거했고, _build_prompt()도
# ncic_records 파라미터가 빠졌다(subject, grade, topic, revision_request, current_questions).
def test_build_prompt_includes_topic_and_revision_note():
    prompt = _build_prompt("수학", "중2", "삼각형", None)
    assert "삼각형" in prompt
    assert "수정 요청" not in prompt

    prompt_with_revision = _build_prompt("수학", "중2", "삼각형", "더 쉽게 해줘")
    assert "수정 요청" in prompt_with_revision
    assert "더 쉽게 해줘" in prompt_with_revision
    assert "[현재 문항]" not in prompt_with_revision  # current_questions 없으면 안 붙음


def test_build_prompt_with_current_questions_grounds_the_revision():
    # "1번 문항 보기를 3개로 줄여줘" 같은 지목형 수정 요청이 실사용 중 실패했다
    # (LLM이 "1번 문항"이 뭔지 모른 채 5개를 백지에서 새로 만들다 다른 문항을 깨뜨림).
    # 현재 문항을 프롬프트에 같이 넣어주면 지목한 문항을 정확히 찾아 고칠 수 있어야 한다.
    current_questions = [
        _sample_question(question="1번 문제입니다", options=["A", "B", "C", "D"], correct_index=1),
        _sample_question(question="2번 문제입니다", options=["E", "F", "G", "H"], correct_index=0),
    ]
    prompt = _build_prompt(
        "수학", "중2", "삼각형", "1번 문항을 3개로 줄여줘", current_questions
    )
    assert "[현재 문항]" in prompt
    assert "1번 문제입니다" in prompt
    assert "2번 문제입니다" in prompt
    assert "[정답]" in prompt  # 정답 표시도 같이 넘어가야 함
    assert "1번 문항을 3개로 줄여줘" in prompt
    assert "수정 요청" in prompt


def test_parse_quiz_json_success():
    parsed = _parse_quiz_json(_fake_quiz_json())
    assert len(parsed["questions"]) == QUESTION_COUNT
    for q in parsed["questions"]:
        assert len(q["options"]) == 4
        assert 0 <= q["correct_index"] < 4
        # _raw_question()의 기본 정답은 옵션 인덱스 1("180도")이므로, 정답 텍스트로부터
        # 인덱스를 정확히 역산하는지 확인한다(2026-08-26 correct_answer 방식으로 변경).
        assert q["correct_index"] == 1
        assert q["options"][q["correct_index"]] == "180도"


def test_parse_quiz_json_handles_code_fence():
    fenced = f"```json\n{_fake_quiz_json()}\n```"
    parsed = _parse_quiz_json(fenced)
    assert len(parsed["questions"]) == QUESTION_COUNT


def test_parse_quiz_json_raises_on_invalid_json():
    try:
        _parse_quiz_json("JSON 아님")
    except QuizError:
        pass
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_on_missing_questions_key():
    try:
        _parse_quiz_json(json.dumps({"foo": "bar"}))
    except QuizError as e:
        assert "questions" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_when_options_below_minimum():
    data = {"questions": [_raw_question(options=["A"], correct_index=0)]}
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "선택지" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_when_options_above_maximum():
    data = {
        "questions": [
            _raw_question(options=["A", "B", "C", "D", "E", "F", "G"], correct_index=0)
        ]
    }
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "선택지" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_accepts_variable_option_count_within_range():
    for count in (MIN_OPTIONS, 3, 5, MAX_OPTIONS):
        options = [f"보기{i}" for i in range(count)]
        data = {"questions": [_raw_question(options=options, correct_index=count - 1)]}
        parsed = _parse_quiz_json(json.dumps(data))
        assert len(parsed["questions"][0]["options"]) == count
        assert parsed["questions"][0]["correct_index"] == count - 1


# 2026-08-26: 실사용 중 발견된 버그(quiz.py 모듈 docstring 참고) — 해설은 정답을
# 맞게 서술하면서 correct_index만 다른 보기를 가리키는 비일관성이 있었다. LLM에게
# 인덱스 대신 정답 텍스트(correct_answer)를 그대로 옮겨 적게 하고, 파싱 단계에서
# 문자열 일치로 인덱스를 역산하도록 바꿨다 — 아래 두 테스트가 새 스키마의 실패
# 케이스를 검증한다.
def test_parse_quiz_json_raises_when_correct_answer_missing():
    data = {"questions": [_raw_question()]}
    del data["questions"][0]["correct_answer"]
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "정답" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_when_correct_answer_not_among_options():
    # 정답 텍스트가 보기 중 어디에도 없으면(오타, 재서술 등) 조용히 틀린 정답을
    # 쓰는 대신 명시적으로 실패시켜 재시도(1회)를 유도해야 한다.
    data = {"questions": [_raw_question()]}
    data["questions"][0]["correct_answer"] = "존재하지 않는 보기"
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "정답" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_generate_quiz_success():
    fake_text = _fake_quiz_json()

    original = quiz.complete
    quiz.complete = lambda prompt, max_tokens=2000: fake_text
    try:
        result = generate_quiz(subject="수학", topic="삼각형의 내각", grade="중2")
    finally:
        quiz.complete = original

    assert len(result["questions"]) == QUESTION_COUNT
    assert result["subject"] == "수학"
    assert result["topic"] == "삼각형의 내각"


def test_generate_quiz_wraps_api_errors_as_quiz_error():
    def _boom(prompt, max_tokens=2000):
        raise RuntimeError("credit balance too low")

    original = quiz.complete
    quiz.complete = _boom
    try:
        try:
            generate_quiz(subject="수학", topic="삼각형", grade="중2")
        except QuizError as e:
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("QuizError가 발생해야 함")
    finally:
        quiz.complete = original


def test_generate_quiz_retries_once_after_malformed_response():
    calls = {"count": 0}

    def _flaky(prompt, max_tokens=2000):
        calls["count"] += 1
        if calls["count"] == 1:
            return "JSON 아닌 응답"
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _flaky
    try:
        result = generate_quiz(subject="수학", topic="삼각형", grade="중2")
    finally:
        quiz.complete = original

    assert calls["count"] == 2
    assert len(result["questions"]) == QUESTION_COUNT


def test_generate_quiz_passes_current_draft_into_prompt_for_grounded_revision():
    captured = {}

    def _capture(prompt, max_tokens=2000):
        captured["prompt"] = prompt
        return _fake_quiz_json()

    current_draft = {
        "questions": [
            _sample_question(question="원래 1번 문제", options=["A", "B", "C", "D"], correct_index=0)
        ]
    }

    original = quiz.complete
    quiz.complete = _capture
    try:
        generate_quiz(
            subject="수학",
            topic="삼각형",
            grade="중2",
            revision_request="1번 문항을 3개로 줄여줘",
            current_draft=current_draft,
        )
    finally:
        quiz.complete = original

    assert "원래 1번 문제" in captured["prompt"]


def test_generate_quiz_gives_up_after_second_failure():
    calls = {"count": 0}

    def _always_broken(prompt, max_tokens=2000):
        calls["count"] += 1
        return "계속 JSON 아님"

    original = quiz.complete
    quiz.complete = _always_broken
    try:
        try:
            generate_quiz(subject="수학", topic="삼각형", grade="중2")
        except QuizError:
            pass
        else:
            raise AssertionError("QuizError가 발생해야 함")
    finally:
        quiz.complete = original

    assert calls["count"] == 2
