"""생성 실패 메시지 테스트 — 내부 사유와 화면 문장 분리 (src/errors.py, 2026-11-13).

실제 데모 증상 2: Quiz 영어 고1 "문법"이 검수에 두 번 걸려 실패하면서, 검수 LLM의
판단 과정이 화면 에러 메시지에 그대로 나왔다. 여기서는 그 사유 문장을 그대로 재현해서
(1) 화면 문장(user_message)에는 안 나오고 (2) 재시도 프롬프트에는 그대로 들어가는지 본다.
"""
from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

import src.config as config
import src.lesson_plan as lesson_plan
import src.quiz as quiz
import src.topic_check as topic_check
import src.usage as usage
import src.worksheet as worksheet
from src.errors import GenerationError, final_message, run_with_one_retry
from src.llm import LLMServiceError
from src.usage import QuotaExceededError

SYMPTOM2_REASON = (
    "(4) 문항 4의 정답 'who'에 대한 해설이 없는 것이 아니라, 문항 5는 (2)에 해당합니다: "
    "보기 c도 정답이 될 수 있음"
)
_QUIZ_JSON = json.dumps(
    {"questions": [{"question": "빈칸에 알맞은 관계대명사를 고르세요: The man ___ lives here.",
                    "options": ["who", "which", "what", "whose"], "correct_answer": "who",
                    "explanation": "선행사가 사람이고 주격이므로 who."}]},
    ensure_ascii=False,
)


class _Script:
    """프롬프트 종류(생성/검수)에 따라 정해진 응답을 돌려주고 모든 프롬프트를 기록한다."""

    def __init__(self, generate, verify=None):
        self.generate, self.verify, self.prompts = generate, verify, []

    def __call__(self, prompt, max_tokens=1000):
        self.prompts.append(prompt)
        # 재시도 생성 프롬프트에도 거절 사유("문항 검수에서…")가 붙으므로 검수 프롬프트 고유 문구로 구분한다.
        is_verify = "검수 담당 교사" in prompt or "reviewing a multiple-choice quiz" in prompt
        response = self.verify if is_verify else self.generate
        if isinstance(response, Exception):
            raise response
        return response


def test_symptom2_review_reason_stays_out_of_the_user_message(monkeypatch):
    verdict = json.dumps({"results": [{"valid": False, "reason": SYMPTOM2_REASON}]}, ensure_ascii=False)
    script = _Script(_QUIZ_JSON, verdict)
    monkeypatch.setattr(quiz, "complete", script)

    with pytest.raises(quiz.QuizError) as info:
        quiz.generate_quiz("영어", "문법", grade="고1")
    e = info.value

    assert len(script.prompts) == 4  # 생성+검수, 재시도 생성+검수
    assert SYMPTOM2_REASON in script.prompts[2]  # 거절 사유는 재시도 프롬프트에 그대로 간다
    assert SYMPTOM2_REASON in str(e)  # 로그용 내부 사유도 그대로
    assert "문항 4의 정답" not in e.user_message and "(2)에 해당" not in e.user_message
    assert e.user_message == final_message("review", "quiz")
    assert "구체적으로" in e.user_message


def test_review_failure_message_in_english(monkeypatch):
    verdict = json.dumps({"results": [{"valid": False, "reason": "criterion (2): option c is also correct"}]})
    monkeypatch.setattr(quiz, "complete", _Script(_QUIZ_JSON, verdict))
    with pytest.raises(quiz.QuizError) as info:
        quiz.generate_quiz("Math", "fractions", grade="5", locale="us")
    assert "criterion" not in info.value.user_message
    assert "more specific topic" in info.value.user_message


def test_format_failure_shows_generic_message_and_keeps_detail(monkeypatch):
    bad = json.dumps({"questions": [{"question": "q", "options": ["a", "b"], "correct_answer": "z"}]})
    monkeypatch.setattr(quiz, "complete", _Script(bad))
    with pytest.raises(quiz.QuizError) as info:
        quiz.generate_quiz("영어", "관계대명사", grade="고1")
    assert "correct_answer" in str(info.value)  # 어떤 검증에 걸렸는지는 내부 사유에 남는다
    assert "correct_answer" not in info.value.user_message
    assert info.value.user_message == final_message("format", "quiz")


@pytest.mark.parametrize("error", [QuotaExceededError("이 세션의 데모 사용 한도에 도달했어요."),
                                   LLMServiceError("AI 서비스를 일시적으로 사용할 수 없어요.")])
@pytest.mark.parametrize(
    ("module", "call"),
    [
        (quiz, lambda: quiz.generate_quiz("영어", "관계대명사", grade="고1")),
        (lesson_plan, lambda: lesson_plan.generate_lesson_plan("수학", "이차함수", grade="중3")),
        (worksheet, lambda: worksheet.generate_worksheet({"topic": "t", "subject": "s", "grade": "g"})),
    ],
)
def test_quota_and_service_errors_are_not_retried(monkeypatch, module, call, error):
    script = _Script(error)
    monkeypatch.setattr(module, "complete", script)
    with pytest.raises(GenerationError) as info:
        call()
    assert len(script.prompts) == 1  # 다시 불러도 같은 결과라 재시도하지 않는다
    assert info.value.user_message == str(error)  # 이미 사용자용 문장 — 감싸지 않는다
    assert "LLM 호출 오류" not in info.value.user_message


def test_lesson_plan_missing_sections_hides_internal_keys(monkeypatch):
    partial = json.dumps({"자료_개요": "개요"}, ensure_ascii=False)
    monkeypatch.setattr(lesson_plan, "complete", _Script(partial))
    with pytest.raises(lesson_plan.LessonPlanError) as info:
        lesson_plan.generate_lesson_plan("수학", "이차함수", grade="중3")
    assert "수업_흐름" in str(info.value)
    assert "수업_흐름" not in info.value.user_message and "_" not in info.value.user_message


def test_unexpected_llm_error_is_retried_once_then_generic(monkeypatch):
    script = _Script(RuntimeError("Error code: 400 - credit balance too low (request_id=req_123)"))
    monkeypatch.setattr(lesson_plan, "complete", script)
    with pytest.raises(lesson_plan.LessonPlanError) as info:
        lesson_plan.generate_lesson_plan("수학", "이차함수", grade="중3")
    assert len(script.prompts) == 2
    assert "request_id" in str(info.value)
    assert "request_id" not in info.value.user_message
    assert info.value.user_message == final_message("service", "lesson_plan")


def test_run_with_one_retry_returns_second_attempt():
    seen = []

    def attempt(previous):
        seen.append(previous)
        if previous is None:
            raise GenerationError("first")
        return "ok"

    assert run_with_one_retry(attempt, GenerationError, "quiz") == "ok"
    assert seen[0] is None and str(seen[1]) == "first"


def test_quiz_screen_shows_only_the_user_message(monkeypatch):
    def failing_quiz(*_a, **_k):
        raise quiz.QuizError(f"문항 검수에서 문제가 발견됐어요: {SYMPTOM2_REASON}",
                             user_message=final_message("review", "quiz"), kind="review", retryable=False)

    monkeypatch.setattr(config, "LOCALE", "ko")
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(quiz, "generate_quiz", failing_quiz)
    monkeypatch.setattr(topic_check, "complete", lambda *a, **k: '{"verdict": "ok"}')
    monkeypatch.setattr(usage, "sink", lambda row: None)

    at = AppTest.from_file("../chat_app.py", default_timeout=30).run()
    at.radio(key="activity").set_value("Quiz").run()
    # 2026-11-14: Quiz 입력은 채팅 대신 폼
    at.selectbox(key="quiz_form_subject").set_value("영어")
    at.selectbox(key="quiz_form_grade").set_value("고1")
    at.text_input(key="quiz_form_topic").input("관계대명사 who/which")
    next(b for b in at.button if b.label == "퀴즈 만들기").click().run()
    errors = [e.value for e in at.error]
    assert errors == [final_message("review", "quiz")]
    assert not any("문항 4의 정답" in e for e in errors)
