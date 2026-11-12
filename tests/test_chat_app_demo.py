"""데모 모드(US) UI 스모크 테스트 — Streamlit AppTest로 chat_app.py를 실제로 실행한다.

LLM 호출부(generate_lesson_plan/generate_worksheet/generate_quiz)만 가짜로
바꾸고, 대화 상태 머신·렌더링·다운로드 버튼·외부 연동 스킵 분기는 진짜 코드를
탄다. 외부 쓰기 함수(Notion/Docs/Forms)는 호출되면 바로 실패하도록 바꿔서,
데모 모드에서 정말로 한 번도 불리지 않는지 확인한다.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

import src.config as config
import src.google_docs_writer as docs_writer
import src.forms_writer as forms_writer
import src.lesson_plan as lesson_plan
import src.notion_writer as notion_writer
import src.quiz as quiz
import src.usage as usage
import src.worksheet as worksheet
from src.lesson_plan import PLAN_SECTIONS_US
from src.worksheet import WORKSHEET_SECTIONS_US


def _fake_plan(subject, topic, grade="8", revision_request=None, locale="ko", **_):
    plan = {k: f"{k} text" + (f" (revised: {revision_request})" if revision_request else "") for k in PLAN_SECTIONS_US}
    plan.update(standards_references=["5.NF.A.1 — Add fractions"], subject=subject, grade=grade, topic=topic, locale=locale)
    return plan


def _fake_worksheet(plan, revision_request=None, locale="ko"):
    ws = {k: f"{k} for students" for k in WORKSHEET_SECTIONS_US}
    ws.update(topic=plan["topic"], subject=plan["subject"], grade=plan["grade"], locale=locale)
    return ws


def _fake_quiz(subject, topic, grade="8", revision_request=None, current_draft=None, locale="ko"):
    return {
        "subject": subject, "grade": grade, "topic": topic, "locale": locale,
        "questions": [
            {"question": "1/2 + 1/4 = ?", "options": ["3/4", "2/6", "1/8", "1"], "correct_index": 0,
             "explanation": "Common denominator."},
        ],
    }


def _boom(*_a, **_k):
    raise AssertionError("데모 모드에서 외부 쓰기 함수가 호출됨")


@pytest.fixture
def demo_us():
    saved = {
        (config, "LOCALE"): config.LOCALE,
        (config, "DEMO_MODE"): config.DEMO_MODE,
        (lesson_plan, "generate_lesson_plan"): lesson_plan.generate_lesson_plan,
        (worksheet, "generate_worksheet"): worksheet.generate_worksheet,
        (quiz, "generate_quiz"): quiz.generate_quiz,
        (notion_writer, "save_lesson_plan_to_notion"): notion_writer.save_lesson_plan_to_notion,
        (docs_writer, "create_and_write_doc"): docs_writer.create_and_write_doc,
        (forms_writer, "create_quiz_form"): forms_writer.create_quiz_form,
        (usage, "sink"): usage.sink,
        (config, "FEEDBACK_URL"): config.FEEDBACK_URL,
    }
    events = []
    config.LOCALE = "us"
    config.DEMO_MODE = True
    config.FEEDBACK_URL = "https://forms.example.com/feedback"
    lesson_plan.generate_lesson_plan = _fake_plan
    worksheet.generate_worksheet = _fake_worksheet
    quiz.generate_quiz = _fake_quiz
    notion_writer.save_lesson_plan_to_notion = _boom
    docs_writer.create_and_write_doc = _boom
    forms_writer.create_quiz_form = _boom
    usage.sink = lambda row: events.append(row["event"])
    try:
        yield events
    finally:
        for (mod, name), value in saved.items():
            setattr(mod, name, value)


def _chat(at: AppTest, text: str) -> AppTest:
    at.chat_input[0].set_value(text).run()
    return at


def test_lesson_plan_flow_in_demo_mode(demo_us):
    at = AppTest.from_file("../chat_app.py", default_timeout=30).run()
    assert not at.exception
    for msg in ["Math", "Grade 5", "adding fractions"]:
        _chat(at, msg)
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("Discussion Lesson Plan" in h.value for h in at.subheader)
    assert any("Demo mode" in i.value for i in at.info)
    # 피드백 링크: 사이드바 + 결과 직후 두 군데
    feedback_links = [e for e in at.get("link_button") if "forms.example.com" in e.proto.url]
    assert len(feedback_links) == 2
    labels = [b.label for b in at.get("download_button")]
    assert "Download lesson plan (.md)" in labels

    # 활동지 생성 -> Google Docs 없이도 만들어지고 다운로드 버튼이 생겨야 함
    next(b for b in at.button if b.label == "Also make a student worksheet").click().run()
    assert not at.exception
    labels = [b.label for b in at.get("download_button")]
    assert "Download worksheet (.txt)" in labels

    # 채팅으로 수정 요청 -> 다시 생성되고 에러 없음
    _chat(at, "make the lesson flow fit a 30-minute class")
    assert not at.exception
    assert not at.error, [e.value for e in at.error]

    events = demo_us
    assert events.count("session_start") == 1  # 재실행(rerun)마다 다시 세지 않음
    assert "plan_generated" in events
    assert "worksheet_generated" in events
    assert "plan_revised" in events


def test_quiz_flow_in_demo_mode(demo_us):
    at = AppTest.from_file("../chat_app.py", default_timeout=30).run()
    at.radio(key="activity").set_value("Quiz").run()
    for msg in ["Math", "Grade 5", "adding fractions"]:
        _chat(at, msg)
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("Quiz" in h.value for h in at.subheader)
    labels = [b.label for b in at.get("download_button")]
    assert "Download quiz (.md)" in labels
    assert "quiz_generated" in demo_us
