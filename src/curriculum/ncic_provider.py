"""`src/ncic_matcher.py`(한국 2022 개정 교육과정, NCIC)를 CurriculumProvider로 감싼 첫 구현체.

2026-09-17: 여기서는 기존 `ncic_matcher.py`의 함수/데이터/동작을 하나도 바꾸지
않는다 — 같은 함수를 그대로 호출하는 얇은 어댑터일 뿐이다. `ncic_matcher.py`를
직접 import해서 쓰던 기존 코드(테스트 포함)도 그대로 계속 동작한다. 이렇게
분리한 이유는 `ncic_matcher.py` 자체를 다시 쓰는 것보다, 기존에 검증된 로직을
그대로 둔 채 그 위에 인터페이스만 씌우는 쪽이 "동작 변경 없는 순수 리팩터링"
목표에 맞기 때문이다.
"""
from __future__ import annotations

from .. import ncic_matcher
from .base import CurriculumProvider


class NCICProvider(CurriculumProvider):
    """한국 2022 개정 교육과정(국가교육과정정보센터, NCIC) 성취기준 provider."""

    id = "ncic"

    def subjects(self) -> list[str]:
        return ncic_matcher.available_subjects()

    def grade_groups_for(self, grade: str) -> list[str]:
        return ncic_matcher.grade_bands_for(grade)

    def match_standards(
        self,
        subject: str,
        grade: str = "고1",
        keywords: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        return ncic_matcher.match_standards(subject, grade=grade, keywords=keywords, limit=limit)

    def format_citation(self, record: dict) -> str:
        return ncic_matcher.format_citation(record)
