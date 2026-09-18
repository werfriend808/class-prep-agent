from src.edit_propagation import (
    WORKSHEET_RELEVANT_FIELDS,
    WORKSHEET_RELEVANT_FIELDS_US,
    classify_edit_target,
    worksheet_needs_update,
)


def test_classify_edit_target_defaults_to_plan_without_keywords():
    assert classify_edit_target("토론 시간을 20분으로 늘려줘", has_worksheet=True) == "plan"


def test_classify_edit_target_detects_worksheet_keyword():
    assert classify_edit_target("활동지 난이도를 낮춰줘", has_worksheet=True) == "worksheet"
    assert classify_edit_target("학생 활동 질문을 줄여줘", has_worksheet=True) == "worksheet"
    assert classify_edit_target("워크시트 좀 더 쉽게 만들어줘", has_worksheet=True) == "worksheet"


def test_classify_edit_target_always_plan_when_no_worksheet_exists():
    # 활동지가 아직 없으면 "활동지" 키워드가 있어도 고칠 대상이 없으니 plan으로 취급.
    assert classify_edit_target("활동지 난이도를 낮춰줘", has_worksheet=False) == "plan"


def _plan(**overrides) -> dict:
    base = {
        "topic": "환경 보전과 개발",
        "subject": "사회",
        "grade": "고1",
        "토론_쟁점": "쟁점 원본",
        "수업_흐름": "흐름 원본",
        "평가_루브릭": "루브릭 원본",
        "배경_읽기_자료": "배경 원본",
    }
    base.update(overrides)
    return base


def test_no_update_needed_when_nothing_changed():
    old = _plan()
    new = _plan()
    assert worksheet_needs_update(old, new) is False


def test_no_update_needed_when_only_irrelevant_field_changed():
    old = _plan()
    new = _plan(평가_루브릭="루브릭 수정됨", 배경_읽기_자료="배경 수정됨")
    assert worksheet_needs_update(old, new) is False


def test_update_needed_when_discussion_issue_changed():
    old = _plan()
    new = _plan(토론_쟁점="쟁점 수정됨")
    assert worksheet_needs_update(old, new) is True


def test_update_needed_when_flow_changed():
    old = _plan()
    new = _plan(수업_흐름="흐름 수정됨")
    assert worksheet_needs_update(old, new) is True


def test_update_needed_when_topic_changed():
    old = _plan()
    new = _plan(topic="다른 주제")
    assert worksheet_needs_update(old, new) is True


def test_no_update_needed_when_old_plan_missing():
    # 최초 생성(비교 대상 없음) 상황에서는 활동지 자동 생성을 트리거하지 않는다
    # (활동지 최초 생성은 사용자가 버튼으로 시작하는 opt-in 흐름).
    assert worksheet_needs_update(None, _plan()) is False
    assert worksheet_needs_update({}, _plan()) is False


def test_relevant_fields_match_worksheet_prompt_inputs():
    # 이 상수가 worksheet._build_prompt()가 실제로 쓰는 필드와 어긋나면
    # 판단 로직 전체가 의미 없어지므로, 두 목록이 계속 같은지 회귀 테스트로 고정.
    assert set(WORKSHEET_RELEVANT_FIELDS) == {"topic", "subject", "grade", "토론_쟁점", "수업_흐름"}


# 2026-09-18: locale="us" 경로 -- 영어 키워드(_WORKSHEET_KEYWORDS_US)와 영어 계획안
# 필드(discussion_issues/lesson_flow, WORKSHEET_RELEVANT_FIELDS_US)를 쓰는지 확인한다.
def test_classify_edit_target_us_locale_defaults_to_plan_without_keywords():
    assert classify_edit_target("make the discussion longer", has_worksheet=True, locale="us") == "plan"


def test_classify_edit_target_us_locale_detects_worksheet_keyword():
    assert classify_edit_target("make the worksheet easier", has_worksheet=True, locale="us") == "worksheet"
    assert classify_edit_target("shorten the student activity", has_worksheet=True, locale="us") == "worksheet"
    assert classify_edit_target("simplify the Activity Sheet", has_worksheet=True, locale="us") == "worksheet"


def test_classify_edit_target_us_locale_always_plan_when_no_worksheet_exists():
    assert classify_edit_target("make the worksheet easier", has_worksheet=False, locale="us") == "plan"


def _plan_us(**overrides) -> dict:
    base = {
        "topic": "Environment vs Development",
        "subject": "Science",
        "grade": "8",
        "discussion_issues": "original issues",
        "lesson_flow": "original flow",
        "assessment_rubric": "original rubric",
        "background_reading": "original background",
    }
    base.update(overrides)
    return base


def test_worksheet_needs_update_us_locale_no_update_when_nothing_changed():
    assert worksheet_needs_update(_plan_us(), _plan_us(), locale="us") is False


def test_worksheet_needs_update_us_locale_no_update_when_only_irrelevant_field_changed():
    new = _plan_us(assessment_rubric="revised rubric", background_reading="revised background")
    assert worksheet_needs_update(_plan_us(), new, locale="us") is False


def test_worksheet_needs_update_us_locale_update_needed_when_discussion_issues_changed():
    new = _plan_us(discussion_issues="revised issues")
    assert worksheet_needs_update(_plan_us(), new, locale="us") is True


def test_worksheet_needs_update_us_locale_update_needed_when_lesson_flow_changed():
    new = _plan_us(lesson_flow="revised flow")
    assert worksheet_needs_update(_plan_us(), new, locale="us") is True


def test_relevant_fields_us_match_worksheet_prompt_inputs():
    assert set(WORKSHEET_RELEVANT_FIELDS_US) == {"topic", "subject", "grade", "discussion_issues", "lesson_flow"}


def test_worksheet_needs_update_ko_locale_is_default_and_unaffected():
    # locale을 안 주면 기존 한국어 동작 그대로다 -- 명시적으로 한 번 더 확인.
    old = _plan()
    new = _plan(토론_쟁점="쟁점 수정됨")
    assert worksheet_needs_update(old, new) is True
    assert set(WORKSHEET_RELEVANT_FIELDS) == {"topic", "subject", "grade", "토론_쟁점", "수업_흐름"}
