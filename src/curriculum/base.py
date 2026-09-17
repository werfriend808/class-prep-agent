"""CurriculumProvider: 국가/교육과정별 성취기준 매칭을 추상화하는 인터페이스.

2026-09-17: 지금까지는 `src/ncic_matcher.py`가 한국 2022 개정 교육과정(NCIC)
전용 함수(과목 목록/학년군 변환/성취기준 매칭)를 모듈 레벨 함수로 직접
제공했고, `lesson_plan.py`/`chat_app.py` 등이 이 모듈을 바로 import해서 썼다.
미국 Common Core Math 등 다른 교육과정을 추가로 지원하려면(계획: 한국 NCIC는
그대로 유지하면서 미국판을 추가) 호출부가 "지금 어떤 교육과정을 쓰는지" 몰라도
되도록 이 인터페이스 뒤로 숨겨야 한다. 이 파일은 그 인터페이스만 정의하고,
기존 `ncic_matcher.py`의 로직/데이터는 전혀 건드리지 않는다 — 첫 구현체는
`ncic_provider.NCICProvider`가 기존 함수를 그대로 호출하는 얇은 어댑터다.

학년 그룹핑(grade_groups_for)의 두 가지 형태:
    - 밴드형(한국 NCIC): 여러 학년이 하나의 학년군 라벨을 공유한다
      (예: 초3/초4가 모두 "초등 3~4학년"). 고등학교처럼 한 학년이 여러 밴드에
      걸치는 경우도 있다(고1~3은 "고등학교 공통"과 "고등학교 선택" 둘 다 후보).
    - 학년별형(미국 Common Core Math 예정): 학년마다 개별 라벨이 있고(K, 1,
      2, 3, ...), 밴드라는 개념 자체가 없다.
  이 차이를 인터페이스 차원에서 특별 취급하지는 않는다 — 학년별형 provider는
  grade_groups_for(grade)가 그냥 [grade] 자기 자신을 반환하면 된다("이 학년의
  성취기준은 이 학년 라벨로만 찾는다"는 것도 그룹핑의 한 형태일 뿐이다).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CurriculumProvider(ABC):
    """교육과정(국가/과정)별 성취기준 제공자의 공통 인터페이스.

    `match_standards()`가 반환하는 레코드(dict)의 정확한 필드 구성은 구현체마다
    다를 수 있다 — 다만 `format_citation()`이 그 레코드를 받아 사람이 읽을 인용
    문자열로 바꿀 수 있어야 한다는 계약만 지키면 된다(NCIC는 code/text/
    source_doc 필드를 쓰지만, 다른 교육과정은 다른 필드를 쓸 수 있다).
    """

    #: 짧은 식별자 (예: "ncic"). `config.CURRICULUM_PROVIDER`에서 이 값으로
    #: provider를 고른다 — `curriculum.get_provider()` 참고.
    id: str

    @abstractmethod
    def subjects(self) -> list[str]:
        """이 교육과정에 존재하는 과목(또는 영역) 목록을 반환한다."""

    @abstractmethod
    def grade_groups_for(self, grade: str) -> list[str]:
        """구체적인 학년 표기를 이 교육과정 데이터셋의 학년 그룹 라벨로 변환한다.

        인식하지 못하는 학년 표기를 만났을 때 어떻게 폴백할지는 구현체 재량이다
        (NCIC는 "전체 학년군 후보로"를 택했다 — ncic_matcher.grade_bands_for
        참고).
        """

    @abstractmethod
    def match_standards(
        self,
        subject: str,
        grade: str,
        keywords: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """과목(+선택적으로 학년/키워드)에 맞는 성취기준을 관련도 순으로 반환한다.

        Args:
            subject: 이 교육과정의 과목명(또는 그 일부 문자열).
            grade: 구체적인 학년 표기. 내부적으로 `grade_groups_for()`로 데이터셋
                라벨로 변환한 뒤 필터링하는 것이 일반적이다.
            keywords: 성취기준 텍스트와 대조할 핵심어. 비어있거나 None이면
                필터링 없이(또는 구현체가 정의한 기본 동작으로) 반환한다.
            limit: 반환할 최대 개수.
        """

    @abstractmethod
    def format_citation(self, record: dict) -> str:
        """성취기준 레코드를 수업계획안/문서 본문에 넣을 인용 문자열로 변환한다."""
