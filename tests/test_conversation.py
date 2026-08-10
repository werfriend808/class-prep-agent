"""conversation.py (멀티턴 대화 상태 관리) 단위 테스트."""
from src.conversation import ConversationState, Phase, extract_grade, extract_subject


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
