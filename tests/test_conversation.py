"""conversation.py (멀티턴 대화 상태 관리) 단위 테스트."""
from src.conversation import (
    ConversationState,
    Phase,
    extract_grade,
    extract_grade_us,
    extract_subject,
    extract_subject_us,
)


def test_extract_subject_prefers_specific_over_generic():
    # "통합사회"/"한국사"가 "사회"보다 먼저 검사되어야 한다.
    assert extract_subject("통합사회로 할게요") == "통합사회"
    assert extract_subject("한국사 수업이요") == "한국사"
    assert extract_subject("그냥 사회 과목이요") == "사회"
    assert extract_subject("과학 시간에 할 거예요") == "과학"
    assert extract_subject("전혀 관련 없는 말") is None


def test_extract_grade_detects_various_forms():
    assert extract_grade("고등학교 1학년이요") == "고1"
    assert extract_grade("고1 학생 대상으로요") == "고1"
    assert extract_grade("초등학교 3학년 대상이에요") == "초3"
    assert extract_grade("중학교 2학년") == "중2"
    assert extract_grade("초5 학생들이요") == "초5"
    # 학교급 없이 "1학년"만 말하면 어느 학교급인지 알 수 없어 인식하지 못한다
    # (학교급을 잘못 추측하면 ncic_matcher가 엉뚱한 학년군을 찾게 되므로 재질문한다).
    assert extract_grade("1학년이요") is None
    assert extract_grade("아무 언급 없음") is None


def test_initial_question_is_subject():
    conv = ConversationState()
    assert "과목" in conv.next_question()


def test_collecting_subject_then_grade_then_topic_transitions_to_ready():
    conv = ConversationState()
    conv.handle_message("사회 과목으로 하고 싶어요")
    assert conv.phase == Phase.COLLECTING
    assert conv.slots["subject"] == "사회"
    assert "grade" not in conv.slots  # 학년은 아직 안 물어봄

    reply = conv.handle_message("고등학교 1학년이요")
    assert conv.slots["grade"] == "고1"
    assert conv.phase == Phase.COLLECTING
    assert "주제" in reply  # 학년까지 채워지면 다음 질문(주제)으로 넘어감

    conv.handle_message("환경 보전과 개발 중 무엇을 우선해야 하는가")
    assert conv.phase == Phase.READY
    assert conv.slots["topic"] == "환경 보전과 개발 중 무엇을 우선해야 하는가"


def test_unrecognized_subject_reprompts_without_advancing():
    conv = ConversationState()
    reply = conv.handle_message("아무거나 다 좋아요")
    assert conv.phase == Phase.COLLECTING
    assert "subject" not in conv.slots
    assert "과목" in reply


def test_unrecognized_grade_reprompts_without_advancing():
    conv = ConversationState()
    conv.handle_message("국어")
    reply = conv.handle_message("아무 학년이나 괜찮아요")
    assert conv.phase == Phase.COLLECTING
    assert "grade" not in conv.slots
    assert "학년" in reply


def test_empty_topic_reprompts_without_advancing():
    conv = ConversationState()
    conv.handle_message("국어")
    conv.handle_message("고등학교 1학년")
    reply = conv.handle_message("   ")
    assert conv.phase == Phase.COLLECTING
    assert "topic" not in conv.slots
    assert reply  # 재질문 문구가 반환됨


def test_drafted_message_becomes_revision_request():
    conv = ConversationState()
    conv.handle_message("국어")
    conv.handle_message("고등학교 1학년")
    conv.handle_message("주제")
    conv.apply_draft({"자료_개요": "..."})
    assert conv.phase == Phase.DRAFTED

    conv.handle_message("토론 쟁점을 3개로 줄여줘")
    assert conv.phase == Phase.REVISING
    assert conv.slots["revision_request"] == "토론 쟁점을 3개로 줄여줘"


def test_apply_draft_sets_phase_and_clears_revision_request():
    conv = ConversationState()
    conv.slots["revision_request"] = "이전 요청"
    conv.apply_draft({"자료_개요": "새 초안"})
    assert conv.phase == Phase.DRAFTED
    assert conv.draft == {"자료_개요": "새 초안"}
    assert "revision_request" not in conv.slots


def test_reset_clears_state():
    conv = ConversationState()
    conv.handle_message("국어")
    conv.handle_message("고등학교 1학년")
    conv.handle_message("주제")
    conv.apply_draft({"x": "y"})
    conv.notion_url = "https://notion.so/abc"

    conv.reset()
    assert conv.phase == Phase.COLLECTING
    assert conv.slots == {}
    assert conv.draft is None
    assert conv.notion_url is None


# 2026-09-17 (Phase 3): 영어/미국(Common Core Math) 버전 슬롯 추출 + ConversationState.
# 한국어 경로(locale 기본값 "ko")는 위 테스트들 그대로 커버하므로 여기서는
# locale="us"일 때의 동작만 확인한다.
def test_extract_subject_us_recognizes_math():
    assert extract_subject_us("I want to teach Math") == "Math"
    assert extract_subject_us("let's do math") == "Math"  # 대소문자 무관
    assert extract_subject_us("something unrelated") is None


def test_extract_grade_us_detects_various_forms():
    assert extract_grade_us("Kindergarten please") == "K"
    assert extract_grade_us("K") == "K"
    assert extract_grade_us("grade K") == "K"
    assert extract_grade_us("Grade 3") == "3"
    assert extract_grade_us("3rd grade students") == "3"
    assert extract_grade_us("9th grade") == "9"
    assert extract_grade_us("freshman year") == "9"
    assert extract_grade_us("sophomore") == "10"
    assert extract_grade_us("junior") == "11"
    assert extract_grade_us("senior") == "12"
    assert extract_grade_us("high school") == "9"
    assert extract_grade_us("no grade mentioned") is None


def test_conversation_state_us_locale_initial_question_is_english():
    conv = ConversationState(locale="us")
    assert "subject" in conv.next_question().lower()


def test_conversation_state_us_locale_full_flow_to_ready():
    conv = ConversationState(locale="us")
    conv.handle_message("Math")
    assert conv.slots["subject"] == "Math"

    reply = conv.handle_message("Grade 3")
    assert conv.slots["grade"] == "3"
    assert "topic" in reply.lower()

    conv.handle_message("Fractions and equivalent fractions")
    assert conv.phase == Phase.READY
    assert conv.slots["topic"] == "Fractions and equivalent fractions"


def test_conversation_state_us_locale_unrecognized_subject_reprompts_in_english():
    conv = ConversationState(locale="us")
    reply = conv.handle_message("something totally unrelated")
    assert conv.phase == Phase.COLLECTING
    assert "subject" not in conv.slots
    assert "Math" in reply


def test_conversation_state_us_locale_unrecognized_grade_reprompts_in_english():
    conv = ConversationState(locale="us")
    conv.handle_message("Math")
    reply = conv.handle_message("no idea")
    assert conv.phase == Phase.COLLECTING
    assert "grade" not in conv.slots
    assert "grade" in reply.lower()


def test_conversation_state_us_locale_drafted_message_becomes_revision_request():
    conv = ConversationState(locale="us")
    conv.handle_message("Math")
    conv.handle_message("Grade 3")
    conv.handle_message("Fractions")
    conv.apply_draft({"overview": "..."})
    assert conv.phase == Phase.DRAFTED

    reply = conv.handle_message("make it shorter")
    assert conv.phase == Phase.REVISING
    assert conv.slots["revision_request"] == "make it shorter"
    assert "revise" in reply.lower()


def test_conversation_state_ko_locale_is_default_and_unaffected():
    # locale을 안 주면 기존 한국어 동작 그대로다 — 명시적으로 한 번 더 확인.
    conv = ConversationState()
    assert conv.locale == "ko"
    assert "과목" in conv.next_question()
