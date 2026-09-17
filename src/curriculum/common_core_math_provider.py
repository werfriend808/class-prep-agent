"""`src/common_core_math_matcher.py`(미국 Common Core Math)를 CurriculumProvider로
감싼 두 번째 구현체.

`ncic_provider.NCICProvider`와 완전히 같은 패턴(로직은 별도 모듈에 두고 여기서는
얇게 위임)이다. 학년 그루핑이 밴드형(NCIC)이 아니라 대부분 학년별형이라는 점만
다르지만, 인터페이스(grade_groups_for)는 그 차이를 몰라도 되게 설계돼 있다 —
common_core_math_matcher.grade_groups_for()가 그 학년에 해당하는 라벨(+전 학년
공통 "K-12")을 리스트로 반환하기만 하면 된다.
"""
from __future__ import annotations

from .. import common_core_math_matcher as ccm
from .base import CurriculumProvider


class CommonCoreMathProvider(CurriculumProvider):
    """미국 Common Core State Standards for Mathematics(CCSSM) provider."""

    id = "common_core_math"

    def subjects(self) -> list[str]:
        return ccm.available_subjects()

    def grade_groups_for(self, grade: str) -> list[str]:
        return ccm.grade_groups_for(grade)

    def match_standards(
        self,
        subject: str,
        grade: str = "8",
        keywords: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        return ccm.match_standards(subject, grade=grade, keywords=keywords, limit=limit)

    def format_citation(self, record: dict) -> str:
        return ccm.format_citation(record)
