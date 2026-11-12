"""usage.check_quota(): 세션 한도, 전역 일일 한도(DB 카운트 반영), DB 장애 시 로컬 카운터."""
import pytest

import src.usage as usage


@pytest.fixture
def limits():
    saved = (usage.SESSION_LLM_CALL_LIMIT, usage.DAILY_LLM_CALL_LIMIT, usage._db_count_today, usage.sink)
    usage.sink = lambda row: None
    usage.bind_session("s1")

    def set_limits(session, daily, db_count=None):
        usage.SESSION_LLM_CALL_LIMIT = session
        usage.DAILY_LLM_CALL_LIMIT = daily
        usage._db_count_today = lambda day: db_count

    try:
        yield set_limits
    finally:
        (usage.SESSION_LLM_CALL_LIMIT, usage.DAILY_LLM_CALL_LIMIT, usage._db_count_today, usage.sink) = saved


def test_session_limit(limits):
    limits(session=2, daily=0)
    usage.check_quota()
    usage.check_quota()
    with pytest.raises(usage.QuotaExceededError):
        usage.check_quota()
    usage.bind_session("s2")  # 다른 세션은 영향 없음
    usage.check_quota()


def test_daily_limit_uses_db_count(limits):
    limits(session=0, daily=10, db_count=9)  # 다른 프로세스/재시작 전 호출이 9건
    usage.check_quota()  # 9 -> 10번째 허용
    with pytest.raises(usage.QuotaExceededError):
        usage.check_quota()


def test_daily_limit_falls_back_to_local_count_when_db_unavailable(limits):
    limits(session=0, daily=3, db_count=None)
    for _ in range(3):
        usage.check_quota()
    with pytest.raises(usage.QuotaExceededError):
        usage.check_quota()


def test_zero_means_unlimited(limits):
    limits(session=0, daily=0)
    for _ in range(100):
        usage.check_quota()


def test_quota_error_surfaces_as_lesson_plan_error(limits):
    """한도 초과가 기존 에러 처리 경로(LessonPlanError -> st.error)로 화면에 뜨는지."""
    import src.lesson_plan as lesson_plan

    limits(session=0, daily=0)
    usage.SESSION_LLM_CALL_LIMIT = 0
    usage.DAILY_LLM_CALL_LIMIT = 1
    usage._db_count_today = lambda day: 1  # 이미 오늘 한도 소진
    saved_locale, usage.LOCALE = usage.LOCALE, "us"
    try:
        with pytest.raises(lesson_plan.LessonPlanError) as exc:
            lesson_plan.generate_lesson_plan("Math", "fractions", grade="5", locale="us")
    finally:
        usage.LOCALE = saved_locale
    assert "usage limit" in str(exc.value)
