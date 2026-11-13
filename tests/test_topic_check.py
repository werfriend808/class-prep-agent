"""topic_check.py 단위 테스트 — 과목·학년·주제 정합성 판정.

성취기준 검색(1·2단계)은 실제 데이터셋을 쓰고, LLM 판정(3단계)은 `complete`를
가짜로 바꾼다. 그래서 이 테스트가 보장하는 것은 "어떤 판정이 오면 우리가 올바르게
처리한다"까지다 — LLM이 실제로 맞게 판정하는지는 scripts/check_topic_live.py로
따로 확인한다.

케이스는 실제 데모에서 본 두 증상(도덕 중2 "성선설 성악설", 영어 고1 "문법")과
맞지 않는 조합 예시(초1 수학 "이차함수", 영어 "고전시가"), 그리고 막히면 안 되는
정상 입력(국어 고1 "고전시가")이다.
"""
from __future__ import annotations

import json

import pytest

import src.topic_check as tc
from src.llm import LLMServiceError
from src.usage import QuotaExceededError


class _FakeLLM:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def __call__(self, prompt, max_tokens=1000):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response if isinstance(self.response, str) else json.dumps(self.response, ensure_ascii=False)


@pytest.fixture
def fake_llm(monkeypatch):
    def install(response=None, error=None):
        fake = _FakeLLM(response, error)
        monkeypatch.setattr(tc, "complete", fake)
        return fake

    return install


# --- 1단계: 성취기준이 있으면 LLM을 부르지 않는다 ------------------------------------
@pytest.mark.parametrize(
    ("subject", "grade", "topic"),
    [("수학", "중3", "이차함수"), ("과학", "중2", "광합성"), ("수학", "중2", "일차함수")],
)
def test_matched_topic_is_ok_without_llm_call(fake_llm, subject, grade, topic):
    fake = fake_llm(error=AssertionError("성취기준이 있으면 LLM을 부르면 안 됨"))
    check = tc.check_topic(subject, grade, topic)
    assert check.status == tc.OK
    assert check.standards
    assert not check.needs_clarification
    assert not check.used_llm and fake.prompts == []


# --- 2·3단계: 0건이면 근거를 모아 LLM 판정 1회 ------------------------------------
def test_wrong_grade_math_topic_is_flagged_with_evidence(fake_llm):
    # 초1 수학 + 이차함수: 다른 학년군(중학교/고등 공통)에 있다는 근거가 프롬프트로 간다.
    fake = fake_llm({"verdict": "other_grade", "suggested_grade": "중3", "narrower_topics": ["덧셈과 뺄셈"]})
    check = tc.check_topic("수학", "초1", "이차함수")

    assert len(fake.prompts) == 1
    assert "중학교 1~3학년" in fake.prompts[0] and "고등학교 공통" in fake.prompts[0]
    assert check.status == tc.OTHER_GRADE and check.needs_clarification
    assert check.suggested_grade == "중3"
    assert check.narrower_topics == ["덧셈과 뺄셈"]
    message = tc.format_message(check)
    assert "중학교 3학년" in message and "그대로 만들기" in message


def test_topic_from_another_subject_is_flagged(fake_llm):
    fake_llm({"verdict": "other_subject", "suggested_subject": "국어", "narrower_topics": ["관계대명사"]})
    check = tc.check_topic("영어", "고1", "고전시가")
    assert check.status == tc.OTHER_SUBJECT
    assert check.suggested_subject == "국어"
    assert "국어 과목" in tc.format_message(check)


def test_too_broad_topic_offers_narrower_topics(fake_llm):
    # 실제 데모 증상 2(Quiz, 영어 고1 "문법")의 입력.
    fake_llm({"verdict": "too_broad", "narrower_topics": ["관계대명사 who/which", "현재완료", "to부정사의 용법", "가정법"]})
    check = tc.check_topic("영어", "고1", "문법")
    assert check.status == tc.TOO_BROAD
    assert check.narrower_topics == ["관계대명사 who/which", "현재완료", "to부정사의 용법"]  # 최대 3개
    assert "좁혀" in tc.format_message(check)


def test_symptom1_ethics_topic_in_middle_school_is_no_longer_silent(fake_llm):
    # 실제 데모 증상 1: 도덕 중2 "성선설 성악설"은 성취기준 0건인데 그대로 생성됐다.
    fake_llm({"verdict": "other_grade", "suggested_grade": "고2", "narrower_topics": ["인간 존엄성"]})
    check = tc.check_topic("도덕", "중2", "성선설 성악설")
    assert check.needs_clarification
    assert check.locations == []  # 표현이 달라 어디에서도 못 찾는 경우
    assert "고등학교 2학년" in tc.format_message(check)


def test_valid_topic_with_different_wording_is_not_blocked(fake_llm):
    # 국어 고1 "고전시가"는 정상 입력이지만 키워드 매칭은 0건 — 규칙만으로 막으면 안 된다.
    fake_llm({"verdict": "ok"})
    check = tc.check_topic("국어", "고1", "고전시가")
    assert check.status == tc.OK_UNMATCHED
    assert not check.needs_clarification
    assert check.standards == []  # 근거 없이 생성된다는 사실은 UI가 표시한다


def test_us_locale_flags_quadratic_functions_in_grade_1(fake_llm):
    fake = fake_llm({"verdict": "other_grade", "suggested_grade": "9"})
    check = tc.check_topic("Math", "1", "quadratic functions", locale="us")
    assert "High School" in fake.prompts[0]
    assert check.suggested_grade == "9"
    assert "Grade 9" in tc.format_message(check, "us")


# --- LLM 응답 검증과 폴백 ------------------------------------------------------
@pytest.mark.parametrize("raw", ["판정 불가", "[]", '{"verdict": "maybe"}', "```json\n{}\n```"])
def test_malformed_llm_response_falls_back_to_rule_based_clarification(fake_llm, raw):
    fake_llm(raw)
    check = tc.check_topic("수학", "초1", "이차함수")
    assert check.status == tc.NO_MATCH and check.needs_clarification
    assert "수학 중학교 1~3학년" in tc.format_message(check)  # 규칙 근거는 그대로 보여준다


def test_llm_call_failure_falls_back(fake_llm):
    fake_llm(error=RuntimeError("timeout"))
    assert tc.check_topic("수학", "초1", "이차함수").status == tc.NO_MATCH


@pytest.mark.parametrize("error", [QuotaExceededError("한도"), LLMServiceError("장애")])
def test_quota_and_service_errors_propagate(fake_llm, error):
    fake_llm(error=error)
    with pytest.raises(type(error)):
        tc.check_topic("수학", "초1", "이차함수")


def test_invalid_suggestions_are_dropped(fake_llm):
    fake_llm(
        {
            "verdict": "other_grade",
            "suggested_grade": "초7",  # 없는 학년
            "suggested_subject": "천문학",  # 없는 과목
            "narrower_topics": ["이차함수", "x" * 80, "줄\n바꿈", 3, "도형의 기초"],
        }
    )
    check = tc.check_topic("수학", "초1", "이차함수")
    assert check.status == tc.OTHER_GRADE
    assert check.suggested_grade is None and check.suggested_subject is None
    assert check.narrower_topics == ["도형의 기초"]  # 원래 주제·너무 긴 것·여러 줄·비문자열 제외
    assert "다른 학년" in tc.format_message(check)


def test_suggestion_equal_to_current_value_is_dropped(fake_llm):
    fake_llm({"verdict": "other_grade", "suggested_grade": "초등학교 1학년"})
    assert tc.check_topic("수학", "초1", "이차함수").suggested_grade is None


def test_message_never_contains_raw_llm_text(fake_llm):
    fake_llm({"verdict": "mismatch", "reason": "이 문항은 (2)에 해당합니다: 내부 판단 과정"})
    message = tc.format_message(tc.check_topic("영어", "고1", "고전시가"))
    assert "내부 판단" not in message
    assert "영어와 맞지 않는" in message


def test_grade_label_and_josa():
    assert tc.grade_label("중2") == "중학교 2학년"
    assert tc.grade_label("K", "us") == "Kindergarten"
    assert tc._josa_eun("문법") == "은" and tc._josa_eun("이차함수") == "는"
    assert tc._josa_wa("고등학교 1학년 도덕") == "과" and tc._josa_wa("고등학교 1학년 영어") == "와"


# --- 실제 실행(2026-11-13, scripts/check_topic_live.py) 결과로 고친 부분 --------------
def test_judge_call_leaves_room_for_thinking_tokens(fake_llm):
    # 출력 한도 400에서 도덕 중2 "성선설 성악설" 판정 응답이 잘려 판정을 못 받았다.
    calls = []
    fake = fake_llm({"verdict": "other_grade", "suggested_grade": "고2"})
    original = fake.__call__

    def capture(prompt, max_tokens=1000):
        calls.append(max_tokens)
        return original(prompt, max_tokens)

    tc.complete = capture
    tc.check_topic("도덕", "중2", "성선설 성악설")
    assert calls == [tc.JUDGE_MAX_TOKENS] and tc.JUDGE_MAX_TOKENS >= 1500


def test_json_surrounded_by_text_is_still_parsed(fake_llm):
    fake_llm('판정 결과입니다:\n```json\n{"verdict": "other_grade", "suggested_grade": "고2"}\n```\n이상입니다.')
    check = tc.check_topic("도덕", "중2", "성선설 성악설")
    assert check.status == tc.OTHER_GRADE and check.suggested_grade == "고2"


def test_too_broad_message_does_not_show_unrelated_locations(fake_llm):
    # 실제 출력: 영어 고1 "문법" 메시지에 "예술계열(전문교과) ... 관련 내용이 있어요"가 붙었다.
    fake_llm({"verdict": "too_broad", "narrower_topics": ["관계대명사절 이해하기"]})
    check = tc.check_topic("영어", "고1", "문법")
    assert check.locations  # 근거는 모았지만
    message = tc.format_message(check)
    assert "성취기준 검색" not in message and "예술계열" not in message  # 보여주지 않는다


def test_other_grade_shows_only_same_subject_locations():
    check = tc.TopicCheck(
        tc.OTHER_GRADE, "수학", "초1", "이차함수", suggested_grade="중3",
        locations=[{"subject": "수학", "grade_group": "중학교 1~3학년", "count": 3},
                   {"subject": "과학계열(전문교과)", "grade_group": "고등학교 선택", "count": 9}],
    )
    message = tc.format_message(check)
    assert "수학 중학교 1~3학년" in message and "과학계열" not in message


def test_other_subject_shows_only_suggested_subject_locations():
    check = tc.TopicCheck(
        tc.OTHER_SUBJECT, "영어", "고1", "문법", suggested_subject="국어",
        locations=[{"subject": "예술계열(전문교과)", "grade_group": "고등학교 선택", "count": 2},
                   {"subject": "국어", "grade_group": "고등학교 공통", "count": 1}],
    )
    message = tc.format_message(check)
    assert "국어 고등학교 공통" in message and "예술계열" not in message
