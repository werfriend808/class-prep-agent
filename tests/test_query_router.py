"""query_router 단위 테스트.

extract_filters / _heuristic_classify는 정규식 기반이라 네트워크나 API 키
없이도 항상 결정적으로 통과해야 한다. classify_query()는 실제로는
Claude API를 우선 호출하므로(.env에 유효한 ANTHROPIC_API_KEY가 있으면),
그 결과는 LLM 응답에 따라 달라질 수 있어 별도로 관대하게만 검증한다.
"""
from src.query_router import (
    QueryType,
    _heuristic_classify,
    classify_query,
    clean_search_query,
    extract_filters,
)


def test_extract_filters_grade():
    assert extract_filters("고1 학생 대상 자료 찾아줘")["학년"] == "고1"
    assert extract_filters("고등학교 1학년 자료 찾아줘")["학년"] == "고1"


def test_extract_filters_subject():
    assert extract_filters("지난달 작성된 수학 교과 자료 찾아줘")["과목"] == "수학"


def test_extract_filters_date_hint():
    filters = extract_filters("지난달 작성된 수학 교과 자료 찾아줘")
    assert filters["날짜"] == "지난달"


def test_extract_filters_no_match():
    assert extract_filters("토론 수업 진행 방법 관련 페이지 찾아줘") == {}


def test_heuristic_prefers_topic_for_generic_query():
    query = "토론 수업 진행 방법 관련 페이지 찾아줘"
    assert _heuristic_classify(query, extract_filters(query)) == QueryType.TOPIC


def test_heuristic_prefers_filter_for_spec_example():
    query = "지난달 작성된 수학 교과 자료 찾아줘"
    filters = extract_filters(query)
    assert filters == {"과목": "수학", "날짜": "지난달"}
    assert _heuristic_classify(query, filters) == QueryType.FILTER


def test_heuristic_prefers_filter_for_grade_only_query():
    query = "고3 관련 자료 찾아줘"
    filters = extract_filters(query)
    assert filters == {"학년": "고3"}
    assert _heuristic_classify(query, filters) == QueryType.FILTER


def test_heuristic_prefers_title_when_doc_suffix_present():
    query = "3학년 식물의 한살이 수업계획안 페이지 요약해줘"
    assert _heuristic_classify(query, extract_filters(query)) == QueryType.TITLE


def test_clean_search_query_strips_filler_words():
    # 실사용 테스트로 확인: Notion search에 문장을 통째로 넘기면 제목과 거의
    # 안 겹쳐서 엉뚱한 결과가 나온다. 요청 표현을 제거해 핵심만 남겨야 한다.
    assert clean_search_query("토론 수업 관련 자료 찾아줘") == "토론 수업"
    assert clean_search_query("학교생활 챗봇 만들기 페이지 요약해줘") == "학교생활 챗봇 만들기"


def test_clean_search_query_falls_back_to_original_when_empty():
    assert clean_search_query("찾아줘") == "찾아줘"


def test_classify_query_returns_a_valid_parsed_query():
    # 실제 분류 결과(TOPIC/TITLE/FILTER 중 무엇이든)는 LLM 응답에 따라
    # 달라질 수 있으므로, 여기서는 예외 없이 유효한 ParsedQuery를
    # 반환하는지만 확인한다 (키가 없거나 네트워크가 없어도 폴백으로 통과).
    parsed = classify_query("고3 관련 자료 찾아줘")
    assert isinstance(parsed.query_type, QueryType)
    assert parsed.raw_query == "고3 관련 자료 찾아줘"
