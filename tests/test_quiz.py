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
    _build_prompt_us,
    _build_verification_prompt,
    _normalize_for_match,
    _parse_quiz_json,
    _parse_verification_json,
    _try_eval_simple_expr,
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


# 2026-08-26 (추가): 정답 인덱스 버그를 correct_answer 방식으로 고친 뒤에도
# Stanley가 실사용 테스트에서 더 넓은 문제를 발견했다 — 보기 중 계산 결과가
# 실제로는 동점인데 서로 다른 보기인 것처럼 낸 경우(quiz.py 모듈 docstring
# 참고, 예: "15+27"과 "30+12"는 둘 다 42). 아래 테스트들이 이 검증을 확인한다.
def test_try_eval_simple_expr_evaluates_basic_ops():
    assert _try_eval_simple_expr("15+27") == 42
    assert _try_eval_simple_expr("30 + 12") == 42
    assert _try_eval_simple_expr("3x4") == 12
    assert _try_eval_simple_expr("4×3") == 12
    assert _try_eval_simple_expr("9-4") == 5
    assert _try_eval_simple_expr("8/2") == 4


def test_try_eval_simple_expr_returns_none_for_non_expr_or_division_by_zero():
    assert _try_eval_simple_expr("419") is None  # 결과값만 있는 보기 — 식이 아님
    assert _try_eval_simple_expr("칠 곱하기 팔은 오십육") is None  # 문장형 보기
    assert _try_eval_simple_expr("5/0") is None


def test_parse_quiz_json_raises_when_options_have_duplicate_text():
    data = {"questions": [_raw_question(options=["A", "B", "B", "C"], correct_index=0)]}
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "겹치는" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_when_simple_expr_options_tie():
    # 실제로 겪은 버그 재현: "15+27"과 "30+12"는 둘 다 42라서, 순서만 바꾼 식을
    # 서로 다른 보기인 것처럼 내면 정답이 여러 개가 된다.
    data = {
        "questions": [
            _raw_question(options=["15+27", "12+30", "21+15", "30+12"], correct_index=0)
        ]
    }
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "계산 결과" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_allows_result_value_options_even_if_some_share_digits():
    # 동점 검증은 보기가 전부 "숫자 연산자 숫자" 식일 때만 적용된다 — 계산 결과값
    # 자체를 고르는 문항(예: "246+173=?"의 보기가 "419","410","411","420")에는
    # 적용되지 않아야 오탐이 없다(419/410/411/420은 _SIMPLE_EXPR_RE에 안 걸림).
    data = {"questions": [_raw_question(options=["419", "410", "411", "420"], correct_index=0)]}
    parsed = _parse_quiz_json(json.dumps(data))
    assert parsed["questions"][0]["correct_index"] == 0


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

    # 1차 생성(형식 오류) + 2차 생성(재시도, 성공) + 검수 1회 = 3회.
    # (2026-08-26: 검수 단계 추가 전에는 생성만 2회였다.)
    assert calls["count"] == 3
    assert len(result["questions"]) == QUESTION_COUNT


def test_generate_quiz_passes_current_draft_into_prompt_for_grounded_revision():
    captured = {}

    def _capture(prompt, max_tokens=2000):
        # quiz.complete()는 생성 프롬프트와 검수 프롬프트 둘 다에 쓰이는데, 검수
        # 프롬프트는 원래 생성 프롬프트의 "[현재 문항]" 그라운딩 내용을 담지
        # 않으므로(검수는 새로 만들어진 5문항만 다시 보여준다) 검수 호출이
        # 캡처를 덮어쓰지 않도록 생성 프롬프트만 저장한다.
        if '"results"' not in prompt:
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


# 2026-08-26 (추가, 두 번째): "'to 부정사'가 형용사적으로 사용되지 않은 것을
# 고르세요" 문항처럼, 보기 셋이 전부 형용사적 용법이 아닌데도 그렇다고 전제하는
# 등 계산/중복으로는 못 잡는 "지식 자체가 틀린" 문제가 실사용 중 발견됐다
# (quiz.py 모듈 docstring 참고). Stanley 요청으로 별도의 검수 LLM 호출
# (_verify_questions())을 _generate_once()에 추가했다 — 아래 테스트들이 이
# 흐름을 검증한다. quiz.complete()는 생성/검수 두 프롬프트에 모두 쓰이므로,
# 검수 프롬프트에만 있는 '"results"' 문자열로 두 호출을 구분한다.
def _verification_response(valid_flags):
    return json.dumps(
        {
            "results": [
                {"valid": v, "reason": "" if v else "이유"} for v in valid_flags
            ]
        }
    )


def test_build_verification_prompt_marks_the_correct_option():
    questions = [_sample_question()]
    prompt = _build_verification_prompt("수학", "중2", "삼각형", questions)
    assert "180도" in prompt
    assert "[표시된 정답]" in prompt
    assert "삼각형" in prompt


def test_parse_verification_json_returns_none_on_length_mismatch():
    # results 개수가 문항 수와 다르면(형식이 안 맞으면) 검수를 신뢰하지 않고
    # None을 반환해서 원 결과를 그대로 쓰게 한다.
    assert _parse_verification_json(_verification_response([True]), expected_count=2) is None


def test_parse_verification_json_returns_none_on_invalid_json():
    assert _parse_verification_json("JSON 아님", expected_count=1) is None


def test_generate_quiz_calls_verification_and_accepts_when_valid():
    calls = {"count": 0}

    def _fake(prompt, max_tokens=2000):
        calls["count"] += 1
        if '"results"' in prompt:
            return _verification_response([True] * QUESTION_COUNT)
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _fake
    try:
        result = generate_quiz(subject="수학", topic="삼각형", grade="중2")
    finally:
        quiz.complete = original

    assert calls["count"] == 2  # 생성 1회 + 검수 1회
    assert len(result["questions"]) == QUESTION_COUNT


def test_generate_quiz_retries_once_when_verification_flags_a_question():
    calls = {"count": 0}

    def _fake(prompt, max_tokens=2000):
        calls["count"] += 1
        if '"results"' in prompt:
            if calls["count"] <= 2:
                # 1차 생성에 대한 검수 — 하나가 invalid
                return _verification_response([False] + [True] * (QUESTION_COUNT - 1))
            return _verification_response([True] * QUESTION_COUNT)
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _fake
    try:
        result = generate_quiz(subject="수학", topic="삼각형", grade="중2")
    finally:
        quiz.complete = original

    # 1차 생성 + 1차 검수(실패) + 2차 생성(재시도) + 2차 검수(통과) = 4회
    assert calls["count"] == 4
    assert len(result["questions"]) == QUESTION_COUNT


def test_generate_quiz_gives_up_after_verification_fails_twice():
    def _fake(prompt, max_tokens=2000):
        if '"results"' in prompt:
            return _verification_response([False] * QUESTION_COUNT)
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _fake
    try:
        try:
            generate_quiz(subject="수학", topic="삼각형", grade="중2")
        except QuizError as e:
            assert "검수" in str(e)
        else:
            raise AssertionError("QuizError가 발생해야 함")
    finally:
        quiz.complete = original


def test_generate_quiz_ignores_verification_infra_failure():
    # 검수 호출 자체가 실패해도(네트워크 등) 정상적으로 생성된 퀴즈까지
    # 버리지 않아야 한다 — 검수는 안전장치일 뿐 필수 관문이 아니다.
    def _fake(prompt, max_tokens=2000):
        if '"results"' in prompt:
            raise RuntimeError("network down")
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _fake
    try:
        result = generate_quiz(subject="수학", topic="삼각형", grade="중2")
    finally:
        quiz.complete = original

    assert len(result["questions"]) == QUESTION_COUNT


def test_generate_quiz_ignores_malformed_verification_response():
    # 검수 응답이 JSON이 아니거나 형식이 안 맞아도(예: results 개수 불일치)
    # 원 생성 결과를 그대로 써야 한다.
    def _fake(prompt, max_tokens=2000):
        if '"results"' in prompt:
            return "이상한 응답"
        return _fake_quiz_json()

    original = quiz.complete
    quiz.complete = _fake
    try:
        result = generate_quiz(subject="수학", topic="삼각형", grade="중2")
    finally:
        quiz.complete = original

    assert len(result["questions"]) == QUESTION_COUNT


# 2026-08-26 (추가, 세 번째): 영어 문항("to부정사" 단원)에서 "3번 문항의
# 정답(correct_answer)이 보기 중에 없어요"가 실사용 중 반복 발생했다(Stanley
# 보고). LLM이 정답 자체는 맞게 골랐는데도 따옴표를 덧붙이거나 대소문자를 바꿔
# 옮겨 적어서 완전 일치 비교가 실패했을 가능성이 있어, 따옴표/마침표/대소문자
# 차이만 있으면 구제하는 관대한 매칭을 추가했다(quiz.py 모듈 docstring 참고).
def test_normalize_for_match_strips_quotes_and_punctuation_and_lowercases():
    assert _normalize_for_match('"interested in playing"') == "interested in playing"
    assert _normalize_for_match("'interested in playing'") == "interested in playing"
    assert _normalize_for_match("Interested in playing.") == "interested in playing"
    assert _normalize_for_match("  Interested in playing  ") == "interested in playing"


def test_parse_quiz_json_accepts_correct_answer_with_quotes_or_case_difference():
    data = {
        "questions": [
            _raw_question(
                options=["happy to see you", "difficult to understand", "easy to learn", "interested in playing"],
                correct_index=3,
            )
        ]
    }
    # LLM이 정답을 그대로 베끼지 않고 따옴표를 둘러서 적은 경우를 재현
    data["questions"][0]["correct_answer"] = '"interested in playing"'
    parsed = _parse_quiz_json(json.dumps(data))
    assert parsed["questions"][0]["correct_index"] == 3


def test_parse_quiz_json_raises_when_fuzzy_match_is_ambiguous():
    # 정규화했을 때 두 보기가 같아져 버리면(예: 대소문자만 다른 중복) 어느 쪽인지
    # 확신할 수 없으므로 그대로 실패 처리해야 한다 — 이 경우는 애초에 보기 자체가
    # 중복 검증(test_parse_quiz_json_raises_when_options_have_duplicate_text)에
    # 걸리지 않도록 대소문자만 다르게 구성했다.
    data = {"questions": [_raw_question(options=["Apple", "apple", "Banana", "Cherry"], correct_index=0)]}
    data["questions"][0]["correct_answer"] = "APPLE"
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "정답" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_raises_when_latex_escape_corrupts_json_string():
    # 실사용 중 재현된 패턴: LLM이 explanation에 LaTeX 표기(\times, \frac{}{})를
    # JSON 이스케이프 없이 그대로 냈다. JSON 표준상 "\t"/"\f"는 유효한 이스케이프라서
    # json.loads()가 예외 없이 통과시키면서 "\times"는 탭+"imes", "\frac"는
    # 폼피드+"rac"로 조용히 망가진다(2026-08-26, README 18-6-7 참고) — 이 손상을
    # 재현하려고 json.dumps가 아니라 실제 malformed 텍스트를 직접 구성한다.
    raw_text = (
        '{"questions": [{"question": "월요일에는 몇 권을 읽었습니까?", '
        '"options": ["10권", "12권", "14권", "16권"], '
        '"correct_answer": "12권", '
        '"explanation": "전체 \\times \\frac{30}{100} = 12 이므로 전체는 40권입니다."}]}'
    )
    try:
        _parse_quiz_json(raw_text)
    except QuizError as e:
        assert "깨진" in str(e) or "제어문자" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_allows_newline_inside_explanation():
    # 제어문자 검증이 과도하게 엄격해서 정상적인 줄바꿈까지 막으면 안 된다 —
    # 줄바꿈(\n)은 허용 목록에 있어야 한다(_UNEXPECTED_CONTROL_CHAR_RE 정의부 참고).
    data = {"questions": [_raw_question(explanation="첫 번째 줄입니다.\n두 번째 줄입니다.")]}
    parsed = _parse_quiz_json(json.dumps(data))
    assert parsed["questions"][0]["explanation"] == "첫 번째 줄입니다.\n두 번째 줄입니다."


def test_parse_quiz_json_raises_when_question_references_missing_visual():
    # 실사용 중 재현된 패턴: Quiz는 텍스트만 Forms에 반영하고 그래프/표/그림을
    # 따로 만들어 붙이지 않는데, 문항이 "다음은 ~을 나타낸 상대도입니다"처럼 학생이
    # 볼 수 없는 시각 자료를 전제로 만들어졌다(2026-08-26, Stanley 실사용 보고,
    # README 18-6-8 참고).
    data = {
        "questions": [
            _raw_question(
                question="다음은 어느 학급에서 조사한 일주일 동안 읽은 책의 수를 나타낸 상대도입니다. "
                "월요일에는 몇 권을 읽었습니까?",
            )
        ]
    }
    try:
        _parse_quiz_json(json.dumps(data))
    except QuizError as e:
        assert "그래프" in str(e) or "표" in str(e) or "그림" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_allows_question_with_data_written_out_as_text():
    # 위 문항의 올바른 형태: 그래프를 참조하는 대신 데이터를 문항 문장 안에 직접
    # 적었다면 정상적으로 통과해야 한다(오탐 방지 확인).
    data = {
        "questions": [
            _raw_question(
                question="어느 학급의 요일별 독서량은 월 8권, 화 12권, 수 10권, 목 6권, 금 4권입니다. "
                "월요일에는 몇 권을 읽었습니까?",
            )
        ]
    }
    parsed = _parse_quiz_json(json.dumps(data))
    assert "8권" in parsed["questions"][0]["question"]


# 2026-09-18: locale="us" 경로 -- 영어 프롬프트/에러 메시지를 쓰고, 결과 dict에
# "locale" 필드가 채워지는지, 영어 전용 시각 자료 참조 정규식(_VISUAL_REFERENCE_RE_US)이
# 실제로 걸러내는지 확인한다. 기존 ko 기본 경로(locale 인자를 안 주는 모든 테스트)는
# 이 파일에서 하나도 안 건드렸으니 그대로 회귀 검증이 된다.
def _raw_question_us(**overrides) -> dict:
    base = {
        "question": "What is the sum of the interior angles of a triangle?",
        "options": ["90 degrees", "180 degrees", "270 degrees", "360 degrees"],
        "correct_index": 1,
        "explanation": "The three interior angles of a triangle always add up to 180 degrees.",
    }
    base.update(overrides)
    correct_index = base.pop("correct_index")
    base["correct_answer"] = base["options"][correct_index]
    return base


def _fake_quiz_json_us(count: int = QUESTION_COUNT) -> str:
    return json.dumps({"questions": [_raw_question_us(question=f"Question {i}") for i in range(count)]})


def test_build_prompt_us_includes_topic_and_revision_note():
    prompt = _build_prompt_us("Math", "8", "triangles", None)
    assert "triangles" in prompt
    assert "Revision request" not in prompt

    prompt_with_revision = _build_prompt_us("Math", "8", "triangles", "make it easier")
    assert "Revision request" in prompt_with_revision
    assert "make it easier" in prompt_with_revision


def test_generate_quiz_us_locale_success_sets_locale_and_english_fields():
    fake_text = _fake_quiz_json_us()

    original = quiz.complete
    quiz.complete = lambda prompt, max_tokens=2000: fake_text
    try:
        result = generate_quiz(subject="Math", topic="triangle interior angles", grade="8", locale="us")
    finally:
        quiz.complete = original

    assert len(result["questions"]) == QUESTION_COUNT
    assert result["locale"] == "us"
    assert result["subject"] == "Math"
    assert result["topic"] == "triangle interior angles"


def test_generate_quiz_us_locale_wraps_api_errors_in_english():
    def _boom(prompt, max_tokens=2000):
        raise RuntimeError("credit balance too low")

    original = quiz.complete
    quiz.complete = _boom
    try:
        try:
            generate_quiz(subject="Math", topic="triangles", grade="8", locale="us")
        except QuizError as e:
            assert "Failed to generate the quiz" in str(e)
            assert "credit balance too low" in str(e)
        else:
            raise AssertionError("QuizError가 발생해야 함")
    finally:
        quiz.complete = original


def test_parse_quiz_json_us_locale_raises_english_message_on_invalid_json():
    try:
        _parse_quiz_json("not JSON", locale="us")
    except QuizError as e:
        assert "Couldn't parse" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_us_locale_raises_when_question_references_missing_visual():
    data = {
        "questions": [
            _raw_question_us(question="Look at the following graph. What is the highest value shown?")
        ]
    }
    try:
        _parse_quiz_json(json.dumps(data), locale="us")
    except QuizError as e:
        assert "graph/table/image" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_parse_quiz_json_us_locale_allows_question_with_data_written_out_as_text():
    data = {
        "questions": [
            _raw_question_us(
                question="A class read the following number of books each day: Mon 8, Tue 12. "
                "How many more books were read on Tuesday?"
            )
        ]
    }
    parsed = _parse_quiz_json(json.dumps(data), locale="us")
    assert len(parsed["questions"]) == 1


def test_parse_quiz_json_us_locale_raises_english_message_when_correct_answer_missing():
    data = {"questions": [{"question": "q?", "options": ["a", "b"]}]}
    try:
        _parse_quiz_json(json.dumps(data), locale="us")
    except QuizError as e:
        assert "missing a correct_answer" in str(e)
    else:
        raise AssertionError("QuizError가 발생해야 함")


def test_generate_quiz_ko_locale_is_default_and_unaffected():
    # locale을 안 주면 기존 한국어 동작 그대로다 -- 명시적으로 한 번 더 확인.
    fake_text = _fake_quiz_json()
    original = quiz.complete
    quiz.complete = lambda prompt, max_tokens=2000: fake_text
    try:
        result = generate_quiz(subject="수학", topic="삼각형의 내각", grade="중2")
    finally:
        quiz.complete = original
    assert result["locale"] == "ko"
    assert len(result["questions"]) == QUESTION_COUNT
