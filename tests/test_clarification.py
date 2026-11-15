"""CLARIFYING 단계 상태 전이 테스트 (conversation._ClarificationMixin, 2026-11-13).

판정 자체(src/topic_check.py)는 여기서 다루지 않는다 — chat_app이 판정 결과로
request_clarification()을 부른 다음, 사용자의 답에 따라 상태가 어떻게 바뀌는지만
본다. 토의·토론(ConversationState)과 Quiz(QuizConversationState), ko/us 모두.
"""
import pytest

from src.conversation import ConversationState, Phase, QuizConversationState


def _ready(cls, subject, grade, topic, locale="ko"):
    conv = cls(locale=locale)
    for msg in (subject, grade, topic):
        conv.handle_message(msg)
    assert conv.phase == Phase.READY and not conv.topic_checked
    conv.request_clarification("되묻기 메시지", check="판정객체")
    assert conv.phase == Phase.CLARIFYING
    assert conv.history[-1] == {"role": "assistant", "content": "되묻기 메시지"}
    return conv


BOTH = pytest.mark.parametrize("cls", [ConversationState, QuizConversationState])


@BOTH
def test_grade_answer_changes_only_grade_and_rechecks(cls):
    conv = _ready(cls, "수학", "초등학교 1학년", "이차함수")
    conv.handle_message("중학교 3학년으로 바꿀게요")
    assert conv.slots == {"subject": "수학", "grade": "중3", "topic": "이차함수"}
    assert conv.phase == Phase.READY
    assert not conv.topic_checked  # 바뀐 값으로 다시 판정해야 한다


@BOTH
def test_subject_only_answer_changes_subject(cls):
    conv = _ready(cls, "영어", "고1", "고전시가")
    conv.handle_message("국어로 바꿔줘")
    assert conv.slots["subject"] == "국어" and conv.slots["topic"] == "고전시가"
    assert conv.phase == Phase.READY and not conv.topic_checked


@BOTH
def test_other_answer_becomes_new_topic(cls):
    conv = _ready(cls, "영어", "고1", "문법")
    conv.handle_message("관계대명사 who/which")
    assert conv.slots["topic"] == "관계대명사 who/which"
    assert conv.slots["subject"] == "영어"
    assert conv.phase == Phase.READY and not conv.topic_checked


@BOTH
@pytest.mark.parametrize("topic", ["사회적 거리두기", "국어 문법 정리"])
def test_topic_containing_a_subject_word_is_not_a_subject_change(cls, topic):
    conv = _ready(cls, "과학", "중2", "광합성 실험 설계")
    conv.handle_message(topic)
    assert conv.slots["subject"] == "과학"
    assert conv.slots["topic"] == topic


@BOTH
def test_accept_as_is_skips_the_check(cls):
    conv = _ready(cls, "도덕", "중2", "성선설 성악설")
    reply = conv.handle_message("그대로 만들기")
    assert conv.phase == Phase.READY
    assert conv.topic_checked
    assert conv.slots["topic"] == "성선설 성악설"
    assert "그대로" in reply


@BOTH
def test_empty_answer_reprompts(cls):
    conv = _ready(cls, "수학", "초1", "이차함수")
    conv.handle_message("   ")
    assert conv.phase == Phase.CLARIFYING


@BOTH
def test_us_locale_clarification(cls):
    conv = _ready(cls, "math", "Grade 1", "quadratic functions", locale="us")
    conv.handle_message("Grade 9")
    assert conv.slots["grade"] == "9" and conv.phase == Phase.READY
    conv.request_clarification("again")
    reply = conv.handle_message("use as is")
    assert conv.topic_checked and "go ahead" in reply


@BOTH
def test_button_methods_and_reset(cls):
    conv = _ready(cls, "영어", "고1", "문법")
    conv.change_slot("topic", "현재완료")
    assert conv.slots["topic"] == "현재완료" and conv.phase == Phase.READY
    conv.mark_topic_checked("ok")
    assert conv.topic_checked
    conv.reset()
    assert not conv.topic_checked and conv.topic_check is None
