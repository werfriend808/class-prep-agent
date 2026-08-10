"""NCIC 성취기준 데이터셋에서 과목/학년/키워드로 관련 성취기준을 찾는다.

`ncic_standards/go1_common_subjects.json` (고1 공통 과목, 157건)을 대상으로 한
단순 필터링 + 키워드 스코어링. 데이터 규모가 작고(157건) 우리가 직접 정리한
정적 데이터셋이라 필드가 깨끗해서, 임베딩/벡터DB 없이도 이 정도면 충분히
정확하다 — 그리고 임베딩은 보통 유료 API 호출이 필요해서 크레딧 없이 개발을
진행해야 하는 이번 상황과도 맞지 않는다 (자세한 배경은
ncic_standards/README.md의 "다음 단계" 참고).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "ncic_standards" / "go1_common_subjects.json"


@lru_cache(maxsize=1)
def load_standards() -> list[dict]:
    """성취기준 데이터셋을 로드한다 (프로세스당 1회만 파일을 읽고 캐시)."""
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _subject_matches(record_subject: str, record_course: str, query_subject: str) -> bool:
    """과목 질의어가 레코드에 맞는지 판단한다.

    "사회"처럼 상위 과목명을 말하면 한국사/통합사회를 모두 포함하고,
    "통합사회"/"한국사"처럼 세부 과목명을 말하면 그 과목만 정확히 좁힌다.
    """
    query_subject = (query_subject or "").strip()
    if not query_subject:
        return True
    return (
        query_subject == record_subject
        or query_subject in record_subject
        or query_subject in record_course
    )


def match_standards(
    subject: str,
    grade: str = "고1",
    keywords: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """과목(+선택적으로 학년/키워드)에 맞는 성취기준을 관련도 순으로 반환한다.

    Args:
        subject: "국어" / "수학" / "영어" / "사회" / "통합사회" / "한국사" 등.
        grade: 현재 데이터셋이 전부 "고1"이라 사실상 영향은 없지만, 데이터셋이
            확장될 것을 대비해 남겨둔 인자.
        keywords: 수업 주제에서 뽑은 핵심어(예: ["환경", "토론"]). 주어지면
            성취기준 텍스트에 포함된 키워드 개수로 점수를 매겨 정렬한다.
            키워드가 하나도 안 걸리면(주제가 성취기준 문구와 안 겹치는 경우)
            빈 리스트 대신 해당 과목의 성취기준을 그대로 상위 limit개 반환한다
            — "관련 성취기준을 못 찾았다"보다는 "과목 내에서 참고할 만한 것들"을
            보여주는 게 수업계획안 생성에는 더 유용하기 때문.
        limit: 반환할 최대 개수.
    """
    standards = load_standards()
    candidates = [
        s
        for s in standards
        if _subject_matches(s["subject"], s["course"], subject) and s["grade"] == grade
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
