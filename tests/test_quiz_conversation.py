"""QuizConversationState (conversation.py) 단위 테스트.

test_conversation.py의 ConversationState 테스트와 같은 구조 — 상태 전이
로직이 동일해서 시나리오도 그대로 대응시켰다. extract_subject/extract_grade
자체는 test_conversation.py에서 이미 검증하므로 여기서 다시 다루지 않는다.
"""
from src.conversation import Phase, QuizConversationState


def test_initial_question_is_subject():
    conv = QuizConversationState()
    assert "과목" in conv.next_question()


def test_collecting_subject_then_grade_then_topic_transitions_to_ready():
    conv = QuizConversationState()
    conv.handle_message("수학 과목으로 하고 싶어요")
    assert conv.phase == Phase.COLLECTING
    assert conv.slots["subject"] == "수학"

    reply = conv.handle_message("중학교 2학년이요")
    assert conv.slots["grade"] == "중2"
    assert conv.phase == Phase.COLLECTING
    assert "단원" in reply or "주제" in reply

    conv.handle_message("삼각형의 내각")
    assert conv.phase == Phase.READY
    assert conv.slots["topic"] == "삼각형의 내각"


def test_unrecognized_subject_reprompts_without_advancing():
    conv = QuizConversationState()
    reply = conv.handle_message("아무거나 다 좋아요")
    assert conv.phase == Phase.COLLECTING
    assert "subject" not in conv.slots
    assert "과목" in reply


def test_unrecognized_grade_reprompts_without_advancing():
    conv = QuizConversationState()
    conv.handle_message("수학")
    reply = conv.handle_message("아무 학년이나 괜찮아요")
    assert conv.phase == Phase.COLLECTING
    assert "grade" not in conv.slots
    assert "학년" in reply


def test_empty_topic_reprompts_without_advancing():
    conv = QuizConversationState()
    conv.handle_message("수학")
    conv.handle_message("중학교 2학년")
    reply = conv.handle_message("   ")
    assert conv.phase == Phase.COLLECTING
    assert "topic" not in conv.slots
    assert reply


def test_drafted_message_becomes_revision_request():
    conv = QuizConversationState()
    conv.handle_message("수학")
    conv.handle_message("중학교 2학년")
    conv.handle_message("삼각형")
    conv.apply_draft({"questions": []})
    assert conv.phase == Phase.DRAFTED

    conv.handle_message("문제를 더 쉽게 만들어줘")
    assert conv.phase == Phase.REVISING
    assert conv.slots["revision_request"] == "문제를 더 쉽게 만들어줘"


def test_apply_draft_sets_phase_and_clears_revision_request():
    conv = QuizConversationState()
    conv.slots["revision_request"] = "이전 요청"
    conv.apply_draft({"questions": [{"question": "새 문항"}]})
    assert conv.phase == Phase.DRAFTED
    assert conv.draft == {"questions": [{"question": "새 문항"}]}
    assert "revision_request" not in conv.slots


def test_reset_clears_state():
    conv = QuizConversationState()
    conv.handle_message("수학")
    conv.handle_message("중학교 2학년")
    conv.handle_message("삼각형")
    conv.apply_draft({"questions": []})
    conv.form_id = "abc123"
    conv.edit_url = "https://docs.google.com/forms/d/abc123/edit"
    conv.responder_url = "https://docs.google.com/forms/d/abc123/viewform"

    conv.reset()
    assert conv.phase == Phase.COLLECTING
    assert conv.slots == {}
    assert conv.draft is None
    assert conv.form_id is None
    assert conv.edit_url is None
    assert conv.responder_url is None


# 2026-09-18: locale="us" 경로 -- test_conversation.py의 ConversationState US 테스트와
# 같은 시나리오를 QuizConversationState에도 대응시켰다.
def test_quiz_conversation_state_us_locale_initial_question_is_english():
    conv = QuizConversationState(locale="us")
    assert "subject" in conv.next_question().lower()


def test_quiz_conversation_state_us_locale_full_flow_to_ready():
    conv = QuizConversationState(locale="us")
    conv.handle_message("Math")
    assert conv.slots["subject"] == "Math"

    reply = conv.handle_message("Grade 5")
    assert conv.slots["grade"] == "5"
    assert "unit" in reply.lower() or "topic" in reply.lower()

    conv.handle_message("Fractions")
    assert conv.phase == Phase.READY
    assert conv.slots["topic"] == "Fractions"


def test_quiz_conversation_state_us_locale_unrecognized_subject_reprompts_in_english():
    conv = QuizConversationState(locale="us")
    reply = conv.handle_message("something totally unrelated")
    assert conv.phase == Phase.COLLECTING
    assert "subject" not in conv.slots
    assert "Math" in reply


def test_quiz_conversation_state_us_locale_unrecognized_grade_reprompts_in_english():
    conv = QuizConversationState(locale="us")
    conv.handle_message("Math")
    reply = conv.handle_message("no idea")
    assert conv.phase == Phase.COLLECTING
    assert "grade" not in conv.slots
    assert "grade" in reply.lower()


def test_quiz_conversation_state_us_locale_drafted_message_becomes_revision_request():
    conv = QuizConversationState(locale="us")
    conv.handle_message("Math")
    conv.handle_message("Grade 5")
    conv.handle_message("fractions")
    conv.apply_draft({"questions": []})
    assert conv.phase == Phase.DRAFTED

    reply = conv.handle_message("make it easier")
    assert conv.phase == Phase.REVISING
    assert conv.slots["revision_request"] == "make it easier"
    assert "revise" in reply.lower()


def test_quiz_conversation_state_ko_locale_is_default_and_unaffected():
    conv = QuizConversationState()
    assert conv.locale == "ko"
    assert "과목" in conv.next_question()
