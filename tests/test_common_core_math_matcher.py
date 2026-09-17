"""common_core_math_matcher.py 단위 테스트 (네트워크/파일 외부 의존 없음, 커밋된 JSON 데이터셋만 사용).

test_ncic_matcher.py와 같은 검증 항목을 미국 Common Core Math 쪽에 맞춰 그대로
가져왔다 — 다만 학년 그루핑이 밴드형이 아니라 학년별형(+ 고등학교/전학년 공통
두 밴드)이라는 점이 다르므로 그 차이를 확인하는 테스트를 추가했다.
"""
from src.common_core_math_matcher import (
    available_subjects,
    format_citation,
    grade_groups_for,
    load_standards,
    match_standards,
)


def test_load_standards_returns_517_records():
    data = load_standards()
    assert len(data) == 517


def test_available_subjects_is_math_only():
    assert available_subjects() == ["Math"]


def test_grade_groups_for_maps_specific_grade_to_its_own_label_plus_universal():
    # 학년별형이라 밴드(NCIC의 grade_bands_for)와 달리 대부분 학년 1개당
    # 라벨 1개지만, Math Practice 기준("K-12")은 항상 같이 나와야 한다.
    assert grade_groups_for("3") == ["Grade 3", "K-12"]
    assert grade_groups_for("K") == ["Kindergarten", "K-12"]
    assert grade_groups_for("KG") == ["Kindergarten", "K-12"]


def test_grade_groups_for_groups_all_high_school_grades_together():
    # 고등학교는 학년(9~12) 단위가 아니라 도메인 단위로 조직된다 — 한국 NCIC의
    # "고등학교 공통/선택"과 비슷하게 여러 학년이 라벨 하나를 공유하는 유일한 경우.
    for grade in ("9", "10", "11", "12", "HS"):
        assert grade_groups_for(grade) == ["High School", "K-12"]


def test_grade_groups_for_accepts_dataset_label_directly():
    assert grade_groups_for("Grade 6") == ["Grade 6", "K-12"]
    assert grade_groups_for("High School") == ["High School", "K-12"]


def test_grade_groups_for_unknown_grade_falls_back_to_all_labels():
    groups = grade_groups_for("존재하지않는학년")
    assert "Kindergarten" in groups
    assert "High School" in groups
    assert "K-12" in groups


def test_match_standards_broad_subject_includes_all_domains_for_grade():
    results = match_standards("Math", grade="Grade 6", limit=200)
    domains = {r["domain_code"] for r in results}
    # 6학년 콘텐츠 도메인(RP/NS/EE/G/SP) + 전학년 공통 Math Practice(MP).
    assert {"RP", "NS", "EE", "G", "SP", "MP"} <= domains
    assert all(r["subject"] == "Math" for r in results)


def test_match_standards_narrows_to_one_domain():
    results = match_standards("Geometry", grade="Grade 6", limit=200)
    assert results
    assert all(r["domain"] == "Geometry" for r in results)

    results_by_code = match_standards("G", grade="Grade 6", limit=200)
    assert {r["code"] for r in results_by_code} == {r["code"] for r in results}


def test_match_standards_respects_grade_for_elementary():
    results = match_standards("Math", grade="3", limit=200)
    assert results
    assert all(r["grade"] in ("Grade 3", "K-12") for r in results)


def test_match_standards_respects_limit():
    results = match_standards("Math", grade="Grade 6", limit=3)
    assert len(results) == 3


def test_match_standards_keyword_scoring_orders_relevant_first():
    results = match_standards("Math", grade="Grade 4", keywords=["fraction"], limit=5)
    assert results
    assert all("fraction" in r["text"].lower() for r in results)


def test_match_standards_keyword_matching_is_case_insensitive():
    results = match_standards("Math", grade="Grade 4", keywords=["FRACTION"], limit=5)
    assert results
    assert all("fraction" in r["text"].lower() for r in results)


def test_match_standards_returns_empty_when_keywords_given_but_none_match():
    results = match_standards("Math", grade="Grade 6", keywords=["존재하지않는키워드짜리"], limit=2)
    assert results == []


def test_match_standards_returns_top_candidates_when_no_keywords_given():
    results = match_standards("Math", grade="Grade 6", keywords=None, limit=2)
    assert len(results) == 2


def test_match_standards_always_includes_math_practice_standards_regardless_of_grade():
    # 8개 Math Practice 기준은 "K-12"라 어떤 학년을 조회하든 후보에 포함돼야 한다.
    for grade in ("K", "3", "8", "10"):
        results = match_standards("Math", grade=grade, limit=200)
        assert any(r["domain_code"] == "MP" for r in results)


def test_format_citation_includes_code_and_ccss_copyright_notice():
    record = {
        "code": "6.G.1",
        "text": "성취기준 텍스트",
        "source_doc": "Common Core State Standards for Mathematics — © Copyright 2010. "
        "National Governors Association Center for Best Practices and Council of Chief "
        "State School Officers. All rights reserved.",
    }
    citation = format_citation(record)
    assert "6.G.1" in citation
    assert "성취기준 텍스트" in citation
    assert "© Copyright 2010" in citation
