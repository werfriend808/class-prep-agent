"""ncic_matcher.py 단위 테스트 (네트워크/파일 외부 의존 없음, JSON 데이터셋만 사용)."""
from src.ncic_matcher import (
    available_subjects,
    format_citation,
    grade_bands_for,
    load_standards,
    match_standards,
)


def test_load_standards_returns_4199_records():
    data = load_standards()
    assert len(data) == 4199


def test_available_subjects_covers_all_16_subject_areas():
    subjects = set(available_subjects())
    assert subjects == {
        "국어", "수학", "영어", "사회", "도덕", "과학",
        "실과(기술가정)·정보", "체육", "음악", "미술", "한문", "제2외국어",
        "교양", "과학계열(전문교과)", "체육계열(전문교과)", "예술계열(전문교과)",
    }


def test_grade_bands_for_maps_specific_grade_to_dataset_bands():
    assert grade_bands_for("초3") == ["초등 3~4학년"]
    assert grade_bands_for("중2") == ["중학교 1~3학년"]
    # 고등학교는 공통과목과 선택과목 둘 다 후보로 포함한다.
    assert grade_bands_for("고1") == ["고등학교 공통", "고등학교 선택"]


def test_grade_bands_for_unknown_grade_falls_back_to_all_bands():
    bands = grade_bands_for("존재하지않는학년")
    assert "초등 1~2학년" in bands
    assert "고등학교 선택" in bands


def test_match_standards_broad_subject_includes_all_social_studies_courses():
    # "고1" 질의는 고등학교 공통+선택 밴드를 모두 후보로 삼으므로, 통합사회/한국사
    # (공통)뿐 아니라 경제/법과 사회 같은 사회계열 선택과목도 함께 나와야 한다.
    results = match_standards("사회", grade="고1", limit=200)
    courses = {r["course"] for r in results}
    assert {"한국사1", "한국사2", "통합사회1", "통합사회2"} <= courses
    assert all(r["subject"] == "사회" for r in results)


def test_match_standards_specific_subject_narrows_to_one_course_pair():
    results = match_standards("통합사회", grade="고1", limit=200)
    assert results
    assert all(r["course"] in ("통합사회1", "통합사회2") for r in results)

    results = match_standards("한국사", grade="고1", limit=200)
    assert results
    assert all(r["course"] in ("한국사1", "한국사2") for r in results)


def test_match_standards_respects_grade_band_for_elementary():
    results = match_standards("수학", grade="초3", limit=200)
    assert results
    assert all(r["grade"] == "초등 3~4학년" for r in results)


def test_match_standards_respects_limit():
    results = match_standards("수학", grade="고1", limit=3)
    assert len(results) == 3


def test_match_standards_keyword_scoring_orders_relevant_first():
    results = match_standards("사회", grade="고1", keywords=["환경"], limit=5)
    assert results
    # 상위 결과는 전부 "환경"이 텍스트에 포함되어야 한다.
    assert all("환경" in r["text"] for r in results)


# 2026-08-26: 원래는 키워드가 하나도 안 걸리면 무관한 후보를 그대로 채워서
# 반환했는데(quiz.py 실사용 중 이게 프롬프트 오염 원인으로 드러남 — README
# 18-6-2/13-7), 이제는 빈 리스트를 반환한다. "keywords 자체가 없음"(None/빈
# 리스트)과는 다른 경로라는 걸 구분하려고 두 테스트로 나눴다.
def test_match_standards_returns_empty_when_keywords_given_but_none_match():
    results = match_standards("수학", grade="고1", keywords=["존재하지않는키워드짜리"], limit=2)
    assert results == []


def test_match_standards_returns_top_candidates_when_no_keywords_given():
    # keywords 자체를 안 넘기면(주제에서 뽑을 키워드가 아예 없던 경우) 검색할
    # 단서가 없다는 뜻이라 필터링 없이 해당 과목 후보를 그대로 반환한다 —
    # test_match_standards_respects_limit()과 같은 경로.
    results = match_standards("수학", grade="고1", keywords=None, limit=2)
    assert len(results) == 2
    assert all(r["subject"] == "수학" for r in results)


def test_format_citation_includes_code_and_source():
    record = {
        "code": "10통사1-01-01",
        "text": "성취기준 텍스트",
        "source_doc": "[별책7] 사회과 교육과정.pdf",
    }
    citation = format_citation(record)
    assert "10통사1-01-01" in citation
    assert "성취기준 텍스트" in citation
    assert "[별책7] 사회과 교육과정.pdf" in citation
