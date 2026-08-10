"""ncic_matcher.py 단위 테스트 (네트워크/파일 외부 의존 없음, JSON 데이터셋만 사용)."""
from src.ncic_matcher import available_subjects, format_citation, load_standards, match_standards


def test_load_standards_returns_157_records():
    data = load_standards()
    assert len(data) == 157


def test_available_subjects_returns_four_top_level_subjects():
    subjects = available_subjects()
    assert set(subjects) == {"국어", "수학", "영어", "사회"}


def test_match_standards_broad_subject_includes_all_social_studies_courses():
    results = match_standards("사회", limit=200)
    courses = {r["course"] for r in results}
    assert courses == {"한국사1·2", "통합사회1·2"}


def test_match_standards_specific_subject_narrows_to_one_course():
    results = match_standards("통합사회", limit=200)
    assert results
    assert all(r["course"] == "통합사회1·2" for r in results)

    results = match_standards("한국사", limit=200)
    assert results
    assert all(r["course"] == "한국사1·2" for r in results)


def test_match_standards_respects_limit():
    results = match_standards("수학", limit=3)
    assert len(results) == 3


def test_match_standards_keyword_scoring_orders_relevant_first():
    results = match_standards("사회", keywords=["환경"], limit=5)
    assert results
    # 상위 결과는 전부 "환경"이 텍스트에 포함되어야 한다.
    assert all("환경" in r["text"] for r in results)


def test_match_standards_falls_back_to_candidates_when_no_keyword_matches():
    # 존재하지 않을 법한 키워드 -> 빈 결과 대신 해당 과목 후보를 그대로 반환해야 한다.
    results = match_standards("수학", keywords=["존재하지않는키워드짜리"], limit=2)
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
