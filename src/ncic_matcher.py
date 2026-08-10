"""NCIC 성취기준 데이터셋에서 과목/학년/키워드로 관련 성취기준을 찾는다.

`ncic_standards/achievement_standards.json` (2022 개정 교육과정 별책 16종,
초등~고등 전 학년/전 과목, 4,199건)을 대상으로 한 단순 필터링 + 키워드
스코어링. 과제 스펙(실전 2)이 "대상 학년/과목: 전체 (제한 없음)"이라고 명시하고
있어, 처음에 고1 공통 과목 5개(157건)로 좁혔던 범위를 전체로 넓혔다. 데이터가
우리가 직접 정리한 정적 데이터셋이라 필드가 깨끗해서, 이 규모(4천여 건)에서도
임베딩/벡터DB 없이 과목+학년군 필터링과 키워드 매칭만으로 충분히 정확하다 —
임베딩은 보통 유료 API 호출이 필요해서 크레딧 없이 개발을 진행해야 하는 이번
상황과도 맞지 않는다 (자세한 배경은 ncic_standards/README.md 참고).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "ncic_standards" / "achievement_standards.json"

# 데이터셋의 "grade" 필드는 성취기준 코드의 학년군 접두어(2/4/6/9/10/12)를 그대로
# 옮긴 학년군 라벨이다. 사용자가 말하는 구체적인 학년(예: "초3", "고1")을 이
# 라벨로 변환해야 매칭이 된다. 고등학교는 공통과목/선택과목 둘 다 관련이 있을 수
# 있어 두 밴드 모두 후보로 포함한다.
_GRADE_BAND_MAP: dict[str, list[str]] = {
    "초1": ["초등 1~2학년"], "초2": ["초등 1~2학년"],
    "초3": ["초등 3~4학년"], "초4": ["초등 3~4학년"],
    "초5": ["초등 5~6학년"], "초6": ["초등 5~6학년"],
    "중1": ["중학교 1~3학년"], "중2": ["중학교 1~3학년"], "중3": ["중학교 1~3학년"],
    "고1": ["고등학교 공통", "고등학교 선택"],
    "고2": ["고등학교 공통", "고등학교 선택"],
    "고3": ["고등학교 공통", "고등학교 선택"],
}
_ALL_GRADE_BANDS = [
    "초등 1~2학년", "초등 3~4학년", "초등 5~6학년",
    "중학교 1~3학년", "고등학교 공통", "고등학교 선택",
]


def grade_bands_for(grade: str) -> list[str]:
    """구체적인 학년 표기(예: "고1", "초3")를 데이터셋의 학년군 라벨로 변환한다.

    인식하지 못하는 형식이면 전체 학년군을 후보로 반환한다 — "학년을 몰라서
    아예 못 찾음"보다는 "일단 과목 내에서 넓게 찾아봄"이 계획안 생성에는
    더 유용하기 때문이다 (match_standards의 키워드 미매칭 시 폴백과 같은 원칙).
    """
    return _GRADE_BAND_MAP.get(grade, _ALL_GRADE_BANDS)


@lru_cache(maxsize=1)
def load_standards() -> list[dict]:
    """성취기준 데이터셋을 로드한다 (프로세스당 1회만 파일을 읽고 캐시)."""
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _top_level_subjects() -> frozenset[str]:
    """데이터셋에 실제로 존재하는 상위 과목명 집합 (예: "국어", "수학", ...)."""
    return frozenset(s["subject"] for s in load_standards())


class _TopLevelSubjectsProxy:
    """`in` 연산자로만 쓰이는 지연 평가 프록시 (모듈 로드 시점엔 데이터셋을 안 읽음)."""

    def __contains__(self, item: str) -> bool:
        return item in _top_level_subjects()


TOP_LEVEL_SUBJECTS = _TopLevelSubjectsProxy()


def _subject_matches(record_subject: str, record_course: str, query_subject: str) -> bool:
    """과목 질의어가 레코드에 맞는지 판단한다.

    "사회"처럼 상위 과목명을 말하면 그 과목의 모든 세부 과목(한국사/통합사회/
    경제/법과 사회 등)을 포함하고, "통합사회"/"한국사"처럼 세부 과목명을 말하면
    그 과목만 정확히 좁힌다.

    데이터셋이 16개 과목·수백 개 세부 과목으로 커지면서, 세부 과목명이 다른
    과목의 상위 과목명을 우연히 포함하는 경우가 생겼다(예: 과학계열 전문교과의
    "이산 수학"이라는 과목명에 "수학"이 들어있음). 그래서 질의어가 데이터셋의
    실제 상위 과목명 중 하나(TOP_LEVEL_SUBJECTS)와 정확히 같으면 과목(subject)
    필드로만 매칭하고, 세부 과목명(course) 안에 포함되는지는 보지 않는다 —
    세부 과목 좁히기는 "통합사회"처럼 상위 과목명이 아닌 질의에만 적용한다.
    """
    query_subject = (query_subject or "").strip()
    if not query_subject:
        return True
    if query_subject == record_subject or query_subject in record_subject:
        return True
    if query_subject in TOP_LEVEL_SUBJECTS:
        return False  # 상위 과목명인데 record_subject와 안 맞으면 세부 과목명은 안 본다.
    return query_subject in record_course


def match_standards(
    subject: str,
    grade: str = "고1",
    keywords: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """과목(+선택적으로 학년/키워드)에 맞는 성취기준을 관련도 순으로 반환한다.

    Args:
        subject: "국어" / "수학" / "영어" / "사회" / "통합사회" / "한국사" /
            "도덕" / "과학" / "음악" / "미술" / "체육" / "한문" / "제2외국어" /
            "교양" / "실과(기술가정)·정보" 등 데이터셋에 있는 과목명(또는 그
            일부 문자열).
        grade: "고1"처럼 구체적인 학년. `grade_bands_for()`로 데이터셋의
            학년군 라벨(예: "고등학교 공통")로 변환한 뒤 필터링한다.
        keywords: 수업 주제에서 뽑은 핵심어(예: ["환경", "토론"]). 주어지면
            성취기준 텍스트에 포함된 키워드 개수로 점수를 매겨 정렬한다.
            키워드가 하나도 안 걸리면(주제가 성취기준 문구와 안 겹치는 경우)
            빈 리스트 대신 해당 과목의 성취기준을 그대로 상위 limit개 반환한다
            — "관련 성취기준을 못 찾았다"보다는 "과목 내에서 참고할 만한 것들"을
            보여주는 게 수업계획안 생성에는 더 유용하기 때문.
        limit: 반환할 최대 개수.
    """
    standards = load_standards()
    bands = grade_bands_for(grade)
    candidates = [
        s
        for s in standards
        if _subject_matches(s["subject"], s["course"], subject) and s["grade"] in bands
    ]

    if not keywords:
        return candidates[:limit]

    def score(record: dict) -> int:
        return sum(1 for kw in keywords if kw and kw in record["text"])

    scored = [(score(s), s) for s in candidates]
    if any(sc > 0 for sc, _ in scored):
        scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [s for _, s in scored[:limit]]


def format_citation(record: dict) -> str:
    """수업계획안 본문/Notion 페이지에 넣을 근거 표기 문자열."""
    return f"[{record['code']}] {record['text']} (출처: {record['source_doc']})"


def available_subjects() -> list[str]:
    """현재 데이터셋에 존재하는 과목 목록 (챗봇에서 선택지로 보여줄 때 사용)."""
    standards = load_standards()
    seen: list[str] = []
    for s in standards:
        if s["subject"] not in seen:
            seen.append(s["subject"])
    return seen
