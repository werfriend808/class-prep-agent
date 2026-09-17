"""CurriculumProvider 인터페이스 + NCICProvider(첫 구현체) 단위 테스트.

2026-09-17 (Phase 1): NCICProvider는 `src/ncic_matcher.py`를 그대로 감싸는
어댑터일 뿐이므로, 여기서는 "ncic_matcher를 직접 부른 것과 결과가 완전히
같은가"를 확인한다 — 로직을 새로 검증하는 게 아니라 위임이 올바른지만 본다.
`ncic_matcher.py` 자체의 동작 검증(성취기준 4,199건, 학년군 매핑, 키워드
스코어링 등)은 tests/test_ncic_matcher.py의 몫이다.
"""
import pytest

from src import ncic_matcher
from src.curriculum import CurriculumProvider, NCICProvider, get_provider


def test_get_provider_defaults_to_ncic():
    provider = get_provider()
    assert isinstance(provider, NCICProvider)
    assert provider.id == "ncic"


def test_get_provider_accepts_explicit_name():
    provider = get_provider("ncic")
    assert isinstance(provider, NCICProvider)


def test_get_provider_raises_on_unknown_name():
    with pytest.raises(ValueError, match="ncic"):
        get_provider("common_core_math")  # 아직 등록 안 됨 (Phase 2에서 추가 예정)


def test_curriculum_provider_cannot_be_instantiated_directly():
    # 추상 메서드가 구현 안 됐으므로 직접 인스턴스화하면 TypeError.
    with pytest.raises(TypeError):
        CurriculumProvider()  # type: ignore[abstract]


def test_ncic_provider_subjects_matches_ncic_matcher():
    assert NCICProvider().subjects() == ncic_matcher.available_subjects()


def test_ncic_provider_grade_groups_for_matches_grade_bands_for():
    provider = NCICProvider()
    for grade in ("초3", "중2", "고1", "존재하지않는학년"):
        assert provider.grade_groups_for(grade) == ncic_matcher.grade_bands_for(grade)


def test_ncic_provider_match_standards_delegates_with_same_results():
    provider = NCICProvider()
    direct = ncic_matcher.match_standards("사회", grade="고1", keywords=["환경"], limit=5)
    via_provider = provider.match_standards("사회", grade="고1", keywords=["환경"], limit=5)
    assert via_provider == direct
    assert via_provider  # 비어있지 않음을 확인 (delegate가 아무것도 안 넘기는 버그 방지)


def test_ncic_provider_match_standards_default_grade_matches_ncic_matcher_default():
    # ncic_matcher.match_standards()의 grade 기본값("고1")과 동일해야 한다 —
    # 어댑터에서 기본값을 다르게 적어 조용히 동작이 바뀌는 걸 방지.
    provider = NCICProvider()
    assert provider.match_standards("수학") == ncic_matcher.match_standards("수학")


def test_ncic_provider_format_citation_matches_ncic_matcher():
    record = {
        "code": "10통사1-01-01",
        "text": "성취기준 텍스트",
        "source_doc": "[별책7] 사회과 교육과정.pdf",
    }
    assert NCICProvider().format_citation(record) == ncic_matcher.format_citation(record)
