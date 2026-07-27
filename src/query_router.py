"""자연어 질의를 3가지 필수 유형 중 하나로 분류한다.

- TOPIC: 주제/키워드 검색 (예: "토론 수업 진행 방법 관련 페이지 찾아줘")
- TITLE: 제목 정확 매칭 (예: "3학년 식물의 한살이 수업계획안 페이지 요약해줘")
- FILTER: 속성 필터 - 학년/과목/날짜 (예: "지난달 작성된 수학 교과 자료 찾아줘")

설계 메모 (왜 규칙만으로는 부족한가):
    "3학년 관련 자료 찾아줘"(FILTER)와 "3학년 식물의 한살이 수업계획안 페이지
    요약해줘"(TITLE)는 둘 다 학년 정보를 담고 있지만 유형이 다르다. 차이는
    질의에 '구체적인 제목처럼 보이는 고유한 명사구'가 있는지 여부이고, 이건
    정규식만으로 안정적으로 판별하기 어렵다.

    그래서 이 모듈은 하이브리드로 동작한다:
    1) 학년/과목/날짜 후보값은 항상 규칙 기반(정규식)으로 뽑아서 FILTER 검색에
       바로 쓸 수 있게 만들어둔다.
    2) TOPIC/TITLE/FILTER 중 최종 유형 판단은 Claude API에 위임한다.
    3) API 키가 없거나 호출이 실패하면 `_heuristic_classify`로 안전하게
       degrade한다 (네트워크 없이도 테스트 가능하도록).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from .config import SUMMARY_MODEL
from .llm import get_client


class QueryType(str, Enum):
    TOPIC = "topic"
    TITLE = "title"
    FILTER = "filter"


@dataclass
class ParsedQuery:
    query_type: QueryType
    raw_query: str
    # FILTER 유형일 때(또는 다른 유형이어도 참고용으로) 채워지는 속성 후보.
    # 예: {"학년": "고1", "과목": "수학", "날짜": "지난달"}
    filters: dict[str, str] = field(default_factory=dict)


# 샘플 데이터셋(golden_set/queries.md 참고)에서 관찰된 학년/과목 표기 패턴.
# 실제 팀 데이터셋에 맞게 자유롭게 추가/수정할 것.
# 학교급(초/중/고)이 없는 "3학년"처럼 모호한 표현도 일단 후보로 잡아두고,
# 실제 검색 시점에 학교급을 되물을지는 파이프라인(#8)에서 결정한다.
_GRADE_PATTERN = re.compile(
    r"(초등학교|중학교|고등학교|초|중|고)\s*([1-6])\s*학년|(초|중|고)([1-6])(?!\d)|([1-6])\s*학년"
)

_KNOWN_SUBJECTS = [
    "통합사회", "통합 사회", "통합과학", "통합 과학", "한국사",
    "공통영어", "공통 영어", "공통국어", "공통 국어", "공통수학", "공통 수학",
    "수학", "영어", "국어", "사회", "과학",
]

# 상대적인 날짜 표현 / 명시적 연월. 실제 날짜 범위 계산(오늘 기준 지난달 등)은
# pipeline.py에서 이 힌트 문자열을 보고 처리한다.
_DATE_HINT_PATTERN = re.compile(
    r"(지난달|이번달|지난주|이번주|올해|작년|내년|\d{2,4}\s*년\s*\d{1,2}\s*월)"
)

# "25-2", "26-1"처럼 우리 샘플 데이터셋의 "학기" 속성(select) 값과 동일한 형식.
# 날짜(date) 프로퍼티가 아니라 학기(select) 프로퍼티에 매핑되므로 별도로 뽑는다.
_SEMESTER_PATTERN = re.compile(r"\b(\d{2}-\d)\b")


def _normalize_grade(query: str) -> str | None:
    m = _GRADE_PATTERN.search(query)
    if not m:
        return None
    if m.group(1) and m.group(2):
        level_map = {"초등학교": "초", "중학교": "중", "고등학교": "고"}
        level = level_map.get(m.group(1), m.group(1))
        return f"{level}{m.group(2)}"
    if m.group(3) and m.group(4):
        return f"{m.group(3)}{m.group(4)}"
    if m.group(5):
        # 학교급 없이 "3학년"만 있는 경우 — 값 그대로 후보로 반환
        return f"{m.group(5)}학년"
    return None


def _find_subject(query: str) -> str | None:
    for subject in _KNOWN_SUBJECTS:
        if subject in query:
            return subject
    return None


def _find_date_hint(query: str) -> str | None:
    m = _DATE_HINT_PATTERN.search(query)
    return m.group(0) if m else None


def _find_semester(query: str) -> str | None:
    m = _SEMESTER_PATTERN.search(query)
    return m.group(0) if m else None


def extract_filters(query: str) -> dict[str, str]:
    """질의에서 학년/과목/날짜/학기 후보값을 규칙 기반으로 뽑는다.

    반환 키: "학년", "과목", "날짜"(상대적 시점 힌트), "학기"("25-2" 형식).
    """
    filters: dict[str, str] = {}
    if grade := _normalize_grade(query):
        filters["학년"] = grade
    if subject := _find_subject(query):
        filters["과목"] = subject
    if date_hint := _find_date_hint(query):
        filters["날짜"] = date_hint
    if semester := _find_semester(query):
        filters["학기"] = semester
    return filters


_TITLE_DOC_SUFFIXES = ("계획안", "교안", "활동지", "퀴즈", "수업안", "단원", "보고서")
_TOPIC_MARKERS = ("관련", "방법", "진행", "대한")

# Notion search API는 의미 기반 검색이 아니라 단순 텍스트 매칭에 가깝다.
# "토론 수업 관련 자료 찾아줘" 같은 문장을 통째로 넘기면 제목과 거의 안
# 겹쳐서 엉뚱한 결과가 나온다 (실사용 테스트로 확인, golden_set 참고).
# 그래서 검색어로 넘기기 전에 요청/조사성 표현을 제거해 핵심 키워드만 남긴다.
_FILLER_PATTERN = re.compile(
    r"(관련된|관련|페이지|자료|찾아줘|알려줘|요약해줘|검색해줘|보여줘|주세요|해줘)"
)


def clean_search_query(query: str) -> str:
    """자연어 질의에서 검색에 방해되는 요청 표현을 제거해 핵심 키워드만 남긴다.

    예) "토론 수업 관련 자료 찾아줘" -> "토론 수업"
        "학교생활 챗봇 만들기 페이지 요약해줘" -> "학교생활 챗봇 만들기"
    """
    cleaned = _FILLER_PATTERN.sub("", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query  # 다 지워지면(빈 문자열) 원본 질의를 그대로 사용


def _heuristic_classify(query: str, filters: dict[str, str]) -> QueryType:
    """LLM 없이 쓰는 폴백 규칙 (LLM 호출 실패 시에만 사용).

    기본값은 TOPIC으로 두고, 더 강한 신호가 있을 때만 FILTER/TITLE로
    올린다. 완벽하지 않으므로 실제 서비스에서는 LLM 분류(_llm_classify)를
    우선 사용할 것 — 이 함수는 안전망이다.
    """
    has_topic_marker = any(marker in query for marker in _TOPIC_MARKERS)
    has_title_suffix = any(suffix in query for suffix in _TITLE_DOC_SUFFIXES)
    has_quote = '"' in query or "'" in query or "“" in query

    # 우선순위 1: 문서유형 접미사(계획안/교안/퀴즈 등)나 따옴표로 감싼 구체적
    # 제목이 있고, "관련"/"방법" 같은 일반 주제어 마커가 없으면 TITLE.
    # (학년/과목이 같이 섞여 있어도 구체적 제목이 있으면 TITLE을 우선한다.)
    if (has_title_suffix or has_quote) and not has_topic_marker:
        return QueryType.TITLE

    # 우선순위 2: 학년/과목/날짜 필터 후보가 하나라도 있으면 FILTER.
    if filters:
        return QueryType.FILTER

    # 기본값: TOPIC.
    return QueryType.TOPIC


def _llm_classify(query: str, filters: dict[str, str]) -> QueryType:
    client = get_client()
    prompt = f"""다음은 사용자가 Notion 수업 자료를 찾기 위해 입력한 검색 질의입니다.
아래 세 가지 유형 중 하나로 분류하세요.

- topic: 특정 주제/키워드에 대한 자료를 찾는 일반적인 질의
  예) "토론 수업 진행 방법 관련 페이지 찾아줘"
- title: 특정 페이지의 실제 제목처럼 보이는 고유 명사구가 포함된 질의
  예) "3학년 식물의 한살이 수업계획안 페이지 요약해줘"
- filter: 학년/과목/날짜 같은 속성 조건 위주이고, 구체적인 제목이 없는 질의
  예) "3학년 관련 자료 찾아줘", "지난달 작성된 수학 교과 자료 찾아줘"

질의: "{query}"
규칙 기반으로 미리 뽑아둔 속성 후보: {json.dumps(filters, ensure_ascii=False)}

반드시 아래 JSON 형식으로만 답하세요. 다른 말은 하지 마세요.
{{"type": "topic" | "title" | "filter"}}
"""
    message = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    try:
        parsed = json.loads(text)
        return QueryType(parsed["type"])
    except (json.JSONDecodeError, KeyError, ValueError):
        # LLM이 형식을 어겼을 때를 대비한 폴백
        return _heuristic_classify(query, filters)


def classify_query(query: str) -> ParsedQuery:
    filters = extract_filters(query)
    try:
        query_type = _llm_classify(query, filters)
    except Exception:
        # ANTHROPIC_API_KEY가 없거나(RuntimeError), 키가 유효하지 않거나,
        # 네트워크 문제로 API 호출이 실패하는 경우 등 — 어떤 이유로든 LLM
        # 분류가 안 되면 규칙 기반 폴백으로 서비스가 죽지 않게 한다.
        query_type = _heuristic_classify(query, filters)
    return ParsedQuery(query_type=query_type, raw_query=query, filters=filters)
