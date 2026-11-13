"""생성 전 정합성 판정 UI 테스트 (한국어 데모 모드, Streamlit AppTest, 2026-11-13).

실제 데모에서 본 두 증상과 맞지 않는 조합을 화면 단위로 재현한다. 성취기준 검색은
진짜 데이터를 쓰고, LLM 판정(topic_check.complete)과 생성 함수만 가짜로 바꾼다.
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
from src.lesson_plan import PLAN_SECTIONS


class _Recorder:
    def __init__(self):
        self.plan_calls: list[dict] = []
        self.quiz_calls: list[dict] = []
        self.judge_prompts: list[str] = []
        self.verdict: dict = {"verdict": "ok"}

    def plan(self, subject, topic, grade="고1", revision_request=None, locale="ko", **_):
        self.plan_calls.append({"subject": subject, "grade": grade, "topic": topic})
        records = topic_check.get_provider("ncic").match_standards(
            subject, grade=grade, keywords=lesson_plan.extract_keywords(topic)
        )
        plan = {k: f"{k} 내용" for k in PLAN_SECTIONS}
        plan.update(ncic_references=[r["code"] for r in records], subject=subject, grade=grade, topic=topic, locale=locale)
        return plan

    def quiz(self, subject, topic, grade="고1", revision_request=None, current_draft=None, locale="ko"):
        self.quiz_calls.append({"subject": subject, "grade": grade, "topic": topic})
        return {
            "subject": subject, "grade": grade, "topic": topic, "locale": locale,
            "questions": [{"question": "문항", "options": ["가", "나"], "correct_index": 0, "explanation": "해설"}],
        }

    def judge(self, prompt, max_tokens=1000):
        self.judge_prompts.append(prompt)
        return json.dumps(self.verdict, ensure_ascii=False)


@pytest.fixture
def demo_ko(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(config, "LOCALE", "ko")
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(lesson_plan, "generate_lesson_plan", rec.plan)
    monkeypatch.setattr(quiz, "generate_quiz", rec.quiz)
    monkeypatch.setattr(topic_check, "complete", rec.judge)
    monkeypatch.setattr(usage, "sink", lambda row: None)
    return rec


def _start(activity: str = "토의·토론") -> AppTest:
    at = AppTest.from_file("../chat_app.py", default_timeout=30).run()
    if activity != "토의·토론":
        at.radio(key="activity").set_value(activity).run()
    return at


def _chat(at: AppTest, *messages: str) -> None:
    for text in messages:
        at.chat_input[0].set_value(text).run()


def _assistant_texts(at: AppTest) -> list[str]:
    return [m.markdown[0].value for m in at.chat_message if m.name == "assistant" and m.markdown]


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click().run()


def test_matched_topic_generates_without_judge_call(demo_ko):
    at = _start()
    _chat(at, "수학", "중학교 3학년", "이차함수")
    assert not at.exception
    assert len(demo_ko.plan_calls) == 1
    assert demo_ko.judge_prompts == []  # 성취기준이 있으면 추가 LLM 호출 없음
    assert not any("성취기준 근거 없이" in i.value for i in at.info)


def test_wrong_grade_asks_before_generating_and_button_switches_grade(demo_ko):
    demo_ko.verdict = {"verdict": "other_grade", "suggested_grade": "중3", "narrower_topics": ["덧셈과 뺄셈"]}
    at = _start()
    _chat(at, "수학", "초등학교 1학년", "이차함수")
    assert not at.exception
    assert demo_ko.plan_calls == []  # 생성하지 않고 되묻는다
    assert "중학교 3학년에서 배우는 내용" in _assistant_texts(at)[-1]
    labels = [b.label for b in at.button]
    assert {"중학교 3학년으로 바꾸기", "주제: 덧셈과 뺄셈", "그대로 만들기"} <= set(labels)

    _click(at, "중학교 3학년으로 바꾸기")
    assert not at.exception
    assert demo_ko.plan_calls == [{"subject": "수학", "grade": "중3", "topic": "이차함수"}]
    assert len(demo_ko.judge_prompts) == 1  # 바뀐 조합은 성취기준이 있어 재판정에 LLM 불필요


def test_symptom1_unmatched_plan_is_labelled_when_user_proceeds(demo_ko):
    # 실제 데모 증상 1: 도덕 중2 "성선설 성악설" — 이제 먼저 묻고, 그대로 진행하면 근거 없음을 표시한다.
    demo_ko.verdict = {"verdict": "other_grade", "suggested_grade": "고2"}
    at = _start()
    _chat(at, "도덕", "중학교 2학년", "성선설 성악설")
    assert demo_ko.plan_calls == []
    _click(at, "그대로 만들기")
    assert not at.exception
    assert len(demo_ko.plan_calls) == 1
    assert any("성취기준 근거 없이" in i.value for i in at.info)


def test_valid_but_unmatched_topic_is_not_blocked(demo_ko):
    demo_ko.verdict = {"verdict": "ok"}
    at = _start()
    _chat(at, "국어", "고등학교 1학년", "고전시가")
    assert len(demo_ko.plan_calls) == 1
    assert any("성취기준 근거 없이" in i.value for i in at.info)


def test_symptom2_quiz_broad_topic_asks_to_narrow(demo_ko):
    # 실제 데모 증상 2의 입력: Quiz, 영어 고1 "문법".
    demo_ko.verdict = {"verdict": "too_broad", "narrower_topics": ["관계대명사 who/which", "현재완료"]}
    at = _start("Quiz")
    _chat(at, "영어", "고등학교 1학년", "문법")
    assert demo_ko.quiz_calls == []
    assert "좁혀" in _assistant_texts(at)[-1]
    _click(at, "주제: 관계대명사 who/which")
    assert not at.exception
    assert demo_ko.quiz_calls == [{"subject": "영어", "grade": "고1", "topic": "관계대명사 who/which"}]
    assert len(demo_ko.judge_prompts) == 1  # 추천 주제는 다시 판정하지 않는다


def test_typed_new_topic_is_checked_again(demo_ko):
    demo_ko.verdict = {"verdict": "too_broad", "narrower_topics": ["현재완료"]}
    at = _start("Quiz")
    _chat(at, "영어", "고등학교 1학년", "문법")
    _chat(at, "품사 총정리")  # 직접 입력한 주제(성취기준 0건) -> 다시 판정 (여전히 넓다고 하면 다시 묻는다)
    assert demo_ko.quiz_calls == []
    assert len(demo_ko.judge_prompts) == 2
    assert "품사 총정리" in _assistant_texts(at)[-1]


def test_wrong_subject_typed_answer_changes_subject(demo_ko):
    demo_ko.verdict = {"verdict": "other_subject", "suggested_subject": "국어"}
    at = _start("Quiz")
    _chat(at, "영어", "고등학교 1학년", "고전시가")
    assert demo_ko.quiz_calls == []
    demo_ko.verdict = {"verdict": "ok"}
    _chat(at, "국어로 바꿔줘")
    assert not at.exception
    assert demo_ko.quiz_calls == [{"subject": "국어", "grade": "고1", "topic": "고전시가"}]


def test_us_locale_wrong_grade_flow(demo_ko, monkeypatch):
    monkeypatch.setattr(config, "LOCALE", "us")
    demo_ko.verdict = {"verdict": "other_grade", "suggested_grade": "9"}
    at = _start()
    _chat(at, "Math", "Grade 1", "quadratic functions")
    assert not at.exception
    assert demo_ko.plan_calls == []
    assert "Grade 9" in _assistant_texts(at)[-1]
    _click(at, "Switch to Grade 9")
    assert not at.exception
    assert demo_ko.plan_calls == [{"subject": "Math", "grade": "9", "topic": "quadratic functions"}]
