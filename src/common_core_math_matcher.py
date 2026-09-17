"""Common Core Math 성취기준 데이터셋에서 학년/키워드로 관련 성취기준을 찾는다.

`common_core_standards/math_standards.json`(517건, Common Core State Standards
for Mathematics — 데이터 출처/스키마는 common_core_standards/README.md 참고)을
대상으로 한 단순 필터링 + 키워드 스코어링. `ncic_matcher.py`와 완전히 같은
설계(임베딩·벡터DB 없이 학년 필터링 + 키워드 매칭)를 그대로 따른다 — 정적
데이터셋이라 필드가 깨끗해서 이 방식으로 충분하고, 크레딧 없이 개발한다는
방침과도 맞는다.

한국 NCIC(ncic_matcher.py)와의 핵심 차이는 학년 그루핑이다: NCIC는 여러
학년이 학년군 라벨을 공유하는 밴드형(초1~2, 초3~4, ...)인 반면, 여기는
대부분 학년 1개당 라벨 1개인 학년별형("Grade 6" 등)이다 — 다만 고등학교는
학년(9~12)이 아니라 도메인 단위로 조직되어 있어 "High School" 하나로 묶이고,
"Standards for Mathematical Practice" 8개는 모든 학년에 공통 적용되는
"K-12" 라벨을 쓴다. 그래서 grade_groups_for()는 밴드형이 아닌데도 여전히
여러 라벨을 반환할 수 있다(예: 3학년 조회 시 ["Grade 3", "K-12"]).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "common_core_standards" / "math_standards.json"
)

# "Standards for Mathematical Practice" 8개는 모든 학년에 공통 적용되므로 어떤
# 학년을 조회하든 항상 후보에 포함시킨다 (common_core_standards/README.md 참고).
_UNIVERSAL_GRADE = "K-12"

_SPECIFIC_GRADE_LABELS = [
    "Kindergarten",
    "Grade 1", "Grade 2", "Grade 3", "Grade 4",
    "Grade 5", "Grade 6", "Grade 7", "Grade 8",
    "High School",
]
_ALL_GRADE_LABELS = _SPECIFIC_GRADE_LABELS + [_UNIVERSAL_GRADE]

# 사용자가 말하는 구체적인 학년 표기("K", "3", "10" 등)를 데이터셋의 학년
# 라벨로 변환하는 맵. 고등학교(9~10~11~12)는 학년별이 아니라 도메인 단위로
# 조직되어 있어 전부 "High School" 하나로 묶인다(README 참고).
_GRADE_LABEL_MAP: dict[str, str] = {
    "K": "Kindergarten", "KG": "Kindergarten", "0": "Kindergarten",
    "1": "Grade 1", "2": "Grade 2", "3": "Grade 3", "4": "Grade 4",
    "5": "Grade 5", "6": "Grade 6", "7": "Grade 7", "8": "Grade 8",
    "9": "High School", "10": "High School", "11": "High School", "12": "High School",
    "HS": "High School",
}


def grade_groups_for(grade: str) -> list[str]:
    """구체적인 학년 표기를 데이터셋의 학년 라벨로 변환한다.

    반환값은 항상 그 학년에 특정된 라벨(있으면) + 전 학년 공통 "K-12"를
    포함한다 — Math Practice 기준이 어떤 학년을 조회하든 같이 나오게 하려는
    것이다. 인식하지 못하는 형식이면 (ncic_matcher.grade_bands_for()와 같은
    원칙으로) 전체 라벨을 후보로 반환한다.
    """
    normalized = (grade or "").strip()
    label = _GRADE_LABEL_MAP.get(normalized) or _GRADE_LABEL_MAP.get(normalized.upper())
    if label is None:
        # "Grade 6"/"High School"처럼 데이터셋 라벨을 그대로 넘긴 경우도 허용한다.
        if normalized in _SPECIFIC_GRADE_LABELS:
            label = normalized
        else:
            return _ALL_GRADE_LABELS
    return [label, _UNIVERSAL_GRADE]


@lru_cache(maxsize=1)
def load_standards() -> list[dict]:
    """성취기준 데이터셋을 로드한다 (프로세스당 1회만 파일을 읽고 캐시)."""
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _subject_matches(record: dict, query_subject: str) -> bool:
    """과목 질의어가 레코드에 맞는지 판단한다.

    "Math"(이 데이터셋의 유일한 최상위 과목명)를 말하면 도메인 상관없이 전부
    포함하고, "Geometry"/"Algebra"처럼 도메인명(또는 도메인 코드, 예: "G")을
    말하면 그 도메인만 정확히 좁힌다 — ncic_matcher._subject_matches()의
    "상위 과목명 vs 세부 과목명" 구분과 같은 원칙이다.
    """
    query_subject = (query_subject or "").strip()
    if not query_subject or query_subject.lower() == "math":
        return True
    domain = record.get("domain") or ""
    domain_code = record.get("domain_code") or ""
    return query_subject.lower() in domain.lower() or query_subject.lower() == domain_code.lower()


def match_standards(
    subject: str,
    grade: str = "8",
    keywords: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """과목(+선택적으로 학년/키워드)에 맞는 성취기준을 관련도 순으로 반환한다.

    Args:
        subject: "Math"(전체) 또는 도메인명/도메인 코드(예: "Geometry", "G")로
            좁힐 수 있다.
        grade: "3", "K", "10"처럼 구체적인 학년. `grade_groups_for()`로
            데이터셋 라벨(예: "Grade 3")로 변환한 뒤 필터링한다.
        keywords: 수업 주제에서 뽑은 핵심어(예: ["fraction", "area"]). 주어지면
            성취기준 텍스트에 포함된 키워드 개수로 점수를 매겨, 점수가 0보다
            큰 것만 정렬해서 반환한다(대소문자 구분 없음). 키워드를 하나도
            못 뽑았으면(`keywords`가 비어있거나 None) 이 필터링 자체를
            건너뛰고 후보를 그대로 상위 limit개 반환한다.

            ncic_matcher.match_standards()와 동일한 원칙으로, 키워드가 있는데
            전부 0점이면 무관한 후보를 채워 넣지 않고 빈 리스트를 반환한다 —
            무관한 성취기준이 LLM 프롬프트를 오염시키는 문제(README 13-7/
            18-6-2)가 여기서도 재발하지 않게 하려는 것이다.
        limit: 반환할 최대 개수.
    """
    standards = load_standards()
    groups = grade_groups_for(grade)
    candidates = [
        s for s in standards if _subject_matches(s, subject) and s["grade"] in groups
    ]

    if not keywords:
        return candidates[:limit]

    def score(record: dict) -> int:
        text = record["text"].lower()
        return sum(1 for kw in keywords if kw and kw.lower() in text)

    scored = [(sc, s) for s in candidates if (sc := score(s)) > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [s for _, s in scored[:limit]]


def format_citation(record: dict) -> str:
    """수업계획안 본문에 넣을 근거 표기 문자열. source_doc에 CCSS 저작권 고지가
    고정으로 들어있어(README 참고) 인용마다 라이선스 요건이 자동으로 따라간다."""
    return f"[{record['code']}] {record['text']} (Source: {record['source_doc']})"


def available_subjects() -> list[str]:
    """현재 데이터셋에 존재하는 과목 목록 (지금은 "Math" 하나뿐)."""
    standards = load_standards()
    seen: list[str] = []
    for s in standards:
        if s["subject"] not in seen:
            seen.append(s["subject"])
    return seen
