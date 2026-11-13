"""과목·학년·주제 정합성 판정 (2026-11-13).

문제: 대화는 과목 -> 학년 -> 주제를 하나씩 받아서 바로 생성으로 넘어가고, 세 값이
서로 맞는지 보는 단계가 없었다. 그래서 "초1 수학 + 이차함수", "영어 + 고전시가",
"영어 고1 + 문법"처럼 맞지 않거나 너무 넓은 입력도 그대로 생성됐고, 성취기준
매칭이 0건이어도 사용자에게 알리지 않았다(실제 데모에서 계획안 개요에 "성취기준이
별도로 지정되지 않은 상황"이라고 나온 것이 그 증상).

설계 — 규칙 먼저, LLM은 규칙이 판단 못 할 때만 (README "토픽 정합성 판정" 참고):
  1단계 (규칙, LLM 0회): `match_standards()`가 이 과목·학년에서 1건 이상 찾으면
        OK. 대부분의 정상 입력은 여기서 끝나서 호출 비용이 늘지 않는다.
  2단계 (규칙, LLM 0회): 0건이면 `locate_topic()`으로 같은 키워드를 전체
        데이터셋에서 찾아 "다른 학년/과목에는 있다"는 근거를 모은다.
  3단계 (LLM 1회): 근거를 함께 주고 판정만 받는다(ok/다른 학년/다른 과목/너무
        넓음/안 맞음 + 추천 학년·과목·좁힌 주제). 키워드 매칭은 표현이 다르면
        못 찾기 때문에(실측: 국어 고1 "고전시가", 도덕 고2 "성선설 성악설"은
        데이터셋 어디에서도 0건) 1단계만으로 막으면 정상 입력까지 막힌다.

LLM 출력은 그대로 화면에 내보내지 않는다. 판정 값은 정해진 집합 안에서만,
추천 학년·과목은 대화 단계의 슬롯 추출기가 알아듣는 값일 때만, 좁힌 주제는 짧은
한 줄일 때만 받아들이고, 사용자에게 보이는 문장은 `format_message()`의 템플릿으로
만든다 — Quiz 검수 LLM의 판단 과정이 에러 메시지에 그대로 노출됐던 문제를 이
경로에서는 구조적으로 막으려는 것이다.

LLM 판정이 실패하면(응답 형식 오류 등) 2단계 근거만으로 되묻는 NO_MATCH로
물러난다 — 판정 단계 때문에 생성 자체가 막히면 안 된다. 다만 호출 한도 초과와
서비스 장애는 그대로 올린다: 그 상황에서는 생성도 어차피 실패하므로, 되묻기를
보여준 뒤에 같은 에러를 또 보여주는 것보다 바로 알리는 쪽이 낫다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .conversation import extract_grade, extract_grade_us, extract_subject, extract_subject_us
from .curriculum import CurriculumProvider, get_provider
from .lesson_plan import extract_keywords
from .llm import LLMServiceError, complete
from .usage import QuotaExceededError

OK = "ok"  # 이 과목·학년에서 성취기준을 찾음 (LLM 미호출)
OK_UNMATCHED = "ok_unmatched"  # 성취기준은 못 찾았지만 LLM이 맞는 조합으로 판정 -> 근거 없이 생성
OTHER_GRADE = "other_grade"
OTHER_SUBJECT = "other_subject"
TOO_BROAD = "too_broad"
MISMATCH = "mismatch"
NO_MATCH = "no_match"  # LLM 판정을 못 받음 -> 규칙 근거만으로 되묻기

_LLM_VERDICTS = {
    "ok": OK_UNMATCHED,
    "other_grade": OTHER_GRADE,
    "other_subject": OTHER_SUBJECT,
    "too_broad": TOO_BROAD,
    "mismatch": MISMATCH,
}
_MAX_NARROWER = 3
# 판정 응답은 JSON 한 줄이지만, thinking이 기본으로 켜진 모델은 thinking 토큰도 이 한도에
# 포함된다. 처음엔 400으로 잡았다가 실제 실행(2026-11-13, claude-sonnet-5)에서 응답이
# 잘려 판정을 못 받았다. 과금은 실제로 생성한 만큼만이라 quiz 검수 호출과 같은 1500을 쓴다.
JUDGE_MAX_TOKENS = 1500
_MAX_TOPIC_LEN = 40
_US_GRADES = {"K", *[str(n) for n in range(1, 13)]}


@dataclass
class TopicCheck:
    status: str
    subject: str
    grade: str
    topic: str
    standards: list[dict] = field(default_factory=list)  # 이 과목·학년에서 찾은 성취기준
    locations: list[dict] = field(default_factory=list)  # locate_topic() 결과 (0건일 때만 채움)
    suggested_grade: str | None = None  # 대화 슬롯 형식 ("중3" / "9")
    suggested_subject: str | None = None
    narrower_topics: list[str] = field(default_factory=list)
    used_llm: bool = False
    # 판정 LLM의 원문 응답. 화면에는 절대 쓰지 않고, scripts/check_topic_live.py가 판정이
    # 기대와 다를 때 "모델이 실제로 뭐라고 답했는지" 보여주는 진단용으로만 쓴다.
    llm_raw: str | None = None

    @property
    def needs_clarification(self) -> bool:
        return self.status not in (OK, OK_UNMATCHED)


def check_topic(
    subject: str,
    grade: str,
    topic: str,
    provider: CurriculumProvider | None = None,
    locale: str = "ko",
) -> TopicCheck:
    """세 슬롯이 서로 맞는지 판정한다. 성취기준이 1건 이상이면 LLM을 부르지 않는다."""
    provider = provider or get_provider("common_core_math" if locale == "us" else "ncic")
    keywords = extract_keywords(topic)
    standards = provider.match_standards(subject, grade=grade, keywords=keywords, limit=5)
    if standards:
        return TopicCheck(OK, subject, grade, topic, standards=standards)

    locations = provider.locate_topic(keywords)
    check = TopicCheck(NO_MATCH, subject, grade, topic, locations=locations, used_llm=True)
    prompt = (
        _build_prompt_us(subject, grade, topic, locations)
        if locale == "us"
        else _build_prompt(subject, grade, topic, locations, provider.subjects())
    )
    try:
        raw = complete(prompt, max_tokens=JUDGE_MAX_TOKENS)
    except (QuotaExceededError, LLMServiceError):
        raise
    except Exception:  # noqa: BLE001 — 판정 실패는 규칙 근거만으로 되묻는다
        return check
    check.llm_raw = raw
    _apply_verdict(check, raw, locale)
    return check


def _evidence_lines(locations: list[dict], locale: str) -> str:
    if not locations:
        return "(none)" if locale == "us" else "(없음)"
    if locale == "us":
        return "\n".join(f"- {loc['grade_group']}: {loc['count']}" for loc in locations)
    return "\n".join(f"- {loc['subject']} / {loc['grade_group']}: {loc['count']}건" for loc in locations)


def _build_prompt(subject: str, grade: str, topic: str, locations: list[dict], subjects: list[str]) -> str:
    return (
        "당신은 한국 2022 개정 교육과정에 익숙한 교사입니다. 교사가 수업 자료를 만들려고 "
        "아래 세 가지를 입력했습니다. 세 값이 서로 맞는지 판정해주세요.\n\n"
        f"과목: {subject}\n학년: {grade}\n주제: {topic}\n\n"
        f"이 과목·학년의 성취기준 문장에서 주제 키워드를 찾지 못했습니다. 같은 키워드가 "
        f"나오는 성취기준 위치(과목 / 학년군: 건수):\n{_evidence_lines(locations, 'ko')}\n"
        "(키워드가 문장에 그대로 있는지만 본 결과라, 표현이 다르면 실제로 있는 내용도 0건일 수 있습니다.)\n\n"
        "verdict는 다음 중 하나입니다:\n"
        "- ok: 이 과목·학년에서 다룰 만한 주제 (표현만 성취기준과 다른 경우 포함)\n"
        "- other_grade: 이 과목이지만 주로 다른 학년(학교급)에서 배우는 내용\n"
        "- other_subject: 다른 과목에서 배우는 내용\n"
        "- too_broad: 과목·학년은 맞지만 한 번의 수업이나 퀴즈로 다루기엔 범위가 너무 넓음\n"
        "- mismatch: 이 과목·학년과 맞지 않고 위 어느 것에도 해당하지 않음\n\n"
        "다음 JSON으로만 답하세요 (다른 설명 없이 JSON만): "
        '{"verdict": "...", "suggested_grade": "초1~고3 형식 또는 null", '
        '"suggested_subject": "과목명 또는 null", "narrower_topics": ["...", "..."]}. '
        "suggested_grade는 other_grade일 때만 '중3'처럼 학교급+학년으로 적고, "
        f"suggested_subject는 other_subject일 때만 다음 중 하나로 적으세요: {', '.join(subjects)}. "
        "narrower_topics는 too_broad일 때 이 과목·학년에 맞게 좁힌 주제 3개(각각 짧은 명사구), "
        "other_grade/other_subject/mismatch일 때는 원래 과목·학년에 맞는 대안 주제 2~3개입니다. "
        "성취기준 코드나 문장을 지어내지 마세요."
    )


def _build_prompt_us(subject: str, grade: str, topic: str, locations: list[dict]) -> str:
    return (
        "You are a teacher familiar with the Common Core State Standards for Mathematics. A teacher "
        "entered the three values below to create class material. Judge whether they fit together.\n\n"
        f"Subject: {subject}\nGrade: {grade}\nTopic: {topic}\n\n"
        "No standard for this grade contains the topic keywords. Grades whose standards do contain "
        f"them (grade: count):\n{_evidence_lines(locations, 'us')}\n"
        "(This is literal keyword matching, so a topic worded differently from the standards can show 0.)\n\n"
        "verdict is one of:\n"
        "- ok: a reasonable topic for this subject and grade (including wording that differs from the standards)\n"
        "- other_grade: mainly taught in a different grade\n"
        "- too_broad: right grade, but too broad for a single lesson or quiz\n"
        "- mismatch: doesn't fit this subject/grade and none of the above applies\n\n"
        "Respond with JSON only (no other text): "
        '{"verdict": "...", "suggested_grade": "K, 1-12, or null", "suggested_subject": null, '
        '"narrower_topics": ["...", "..."]}. '
        "Give suggested_grade only for other_grade (e.g. \"8\"). narrower_topics: for too_broad, 3 "
        "narrower topics that fit this grade (short noun phrases); for other_grade/mismatch, 2-3 "
        "alternative topics that fit the original grade. Don't invent standard codes or text."
    )


def _apply_verdict(check: TopicCheck, raw: str, locale: str) -> None:
    """LLM 응답을 검증해서 check에 반영한다. 형식이 틀리면 check를 NO_MATCH 그대로 둔다."""
    # "JSON만 답하라"고 해도 앞뒤에 설명이나 코드 펜스를 붙이는 경우가 있어서, 첫 '{'부터
    # 마지막 '}'까지만 잘라서 파싱한다. 그래도 안 되면 NO_MATCH 그대로 둔다.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    status = _LLM_VERDICTS.get(str(data.get("verdict", "")).strip().lower())
    if status is None:
        return
    check.status = status
    if status == OK_UNMATCHED:
        return

    check.suggested_grade = _valid_grade(data.get("suggested_grade"), check.grade, locale)
    check.suggested_subject = _valid_subject(data.get("suggested_subject"), check.subject, locale)
    check.narrower_topics = _valid_topics(data.get("narrower_topics"), check.topic)


def _valid_grade(value: object, current: str, locale: str) -> str | None:
    """추천 학년을 대화 슬롯 형식으로 정규화한다. 못 알아들으면 None.

    2026-11-13 Haiku 실행에서 US 판정이 other_grade인데 추천 학년이 버려졌다 — "9"
    문자열만 받았는데, 모델은 숫자(9)나 "9th grade"/"High School"처럼 답할 수 있다.
    숫자도 받고, 문자열은 대화 단계와 같은 추출기(extract_grade_us)로 한 번 더 읽는다.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if locale == "us":
        normalized = value.upper().removeprefix("GRADE").strip()
        grade = normalized if normalized in _US_GRADES else extract_grade_us(value)
    else:
        grade = extract_grade(value)
    return grade if grade and grade != current else None


def _valid_subject(value: object, current: str, locale: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    subject = extract_subject_us(value) if locale == "us" else extract_subject(value)
    return subject if subject and subject != current else None


def _valid_topics(value: object, current_topic: str) -> list[str]:
    if not isinstance(value, list):
        return []
    topics: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip().strip("'\"")
        if not item or len(item) > _MAX_TOPIC_LEN or "\n" in item:
            continue
        # 대소문자·앞뒤 공백만 다른 원래 주제도 대안이 아니다 (Haiku 실행에서 "quadratic functions"
        # 입력에 "Quadratic functions"가 대안으로 나왔다).
        if item.casefold() == current_topic.strip().casefold() or item.casefold() in (t.casefold() for t in topics):
            continue
        topics.append(item)
        if len(topics) == _MAX_NARROWER:
            break
    return topics


# --- 사용자에게 보여줄 문장 (전부 템플릿; LLM 문장을 그대로 쓰지 않는다) ----------
def grade_label(grade: str, locale: str = "ko") -> str:
    if locale == "us":
        return "Kindergarten" if grade == "K" else f"Grade {grade}"
    levels = {"초": "초등학교", "중": "중학교", "고": "고등학교"}
    if len(grade) == 2 and grade[0] in levels:
        return f"{levels[grade[0]]} {grade[1]}학년"
    return grade


def _josa_eun(word: str) -> str:
    """'은'/'는' 선택 — 마지막 글자가 한글이면 받침으로, 아니면 '은(는)'."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "은" if (ord(last) - 0xAC00) % 28 else "는"
    return "은(는)"


def _josa_wa(word: str) -> str:
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "과" if (ord(last) - 0xAC00) % 28 else "와"
    return "와(과)"


def _relevant_locations(check: TopicCheck) -> list[dict]:
    """되묻기 메시지에 근거로 보여줄 위치만 고른다.

    2026-11-13 실제 실행: 영어 고1 "문법"(too_broad) 메시지에 "예술계열(전문교과)에서 관련
    내용이 있어요"가 붙었다 — 키워드가 우연히 겹친 위치라 판정과 상관없고 사용자를
    헷갈리게 한다. 그래서 판정을 뒷받침하는 위치만 보여준다:
      - 다른 학년: 같은 과목의 위치만
      - 다른 과목: 추천 과목의 위치만 (추천 과목이 없으면 보여주지 않음)
      - 너무 넓음 / 맞는 조합: 보여주지 않음 (위치가 판정 근거가 아님)
      - 안 맞음 / LLM 판정 없음: 전부 (규칙 근거가 유일한 정보)
    """
    if check.status == OTHER_GRADE:
        return [loc for loc in check.locations if loc["subject"] == check.subject]
    if check.status == OTHER_SUBJECT:
        return [loc for loc in check.locations if loc["subject"] == check.suggested_subject]
    if check.status in (MISMATCH, NO_MATCH):
        return check.locations
    return []


def format_message(check: TopicCheck, locale: str = "ko") -> str:
    """되묻기 메시지. needs_clarification인 판정에만 쓴다."""
    if locale == "us":
        return _format_message_us(check)
    topic = check.topic.strip()
    where = f"{grade_label(check.grade)} {check.subject}"
    head = f"'{topic}'{_josa_eun(topic)}"
    if check.status == OTHER_GRADE:
        target = grade_label(check.suggested_grade) if check.suggested_grade else "다른 학년"
        lines = [f"{head} {where} 성취기준에서 찾지 못했어요. {target}에서 배우는 내용에 더 가까워 보여요."]
    elif check.status == OTHER_SUBJECT:
        target = f"{check.suggested_subject} 과목" if check.suggested_subject else "다른 과목"
        lines = [f"{head} {where} 성취기준에서 찾지 못했어요. {target}에서 배우는 내용에 더 가까워 보여요."]
    elif check.status == TOO_BROAD:
        lines = [f"{head} 범위가 넓어서 한 번의 수업이나 퀴즈로 다루기 어려워요. 조금 더 좁혀 주시겠어요?"]
    elif check.status == MISMATCH:
        lines = [f"{head} {where}{_josa_wa(where)} 맞지 않는 주제로 보여요."]
    else:
        lines = [f"{head} {where} 성취기준에서 찾지 못했어요."]

    found = [f"{loc['subject']} {loc['grade_group']}" for loc in _relevant_locations(check)][:3]
    if found:
        lines.append(f"(성취기준 검색: {', '.join(found)}에서 관련 내용이 있어요.)")
    if check.narrower_topics:
        lines.append("이런 주제는 어떨까요: " + " / ".join(check.narrower_topics))
    lines.append(
        "학년이나 과목을 바꾸려면 '중학교 3학년', '국어'처럼 적어주시고, 다른 주제를 그냥 적어주셔도 돼요. "
        "지금 입력 그대로 만들려면 '그대로 만들기'라고 적어주세요."
    )
    return "\n\n".join(lines)


def _format_message_us(check: TopicCheck) -> str:
    topic = check.topic.strip()
    where = f"{grade_label(check.grade, 'us')} {check.subject}"
    if check.status == OTHER_GRADE:
        target = (
            f"{grade_label(check.suggested_grade, 'us')} content"
            if check.suggested_grade
            else "content from a different grade"
        )
        lines = [f"I couldn't find '{topic}' in the {where} standards. It looks closer to {target}."]
    elif check.status == TOO_BROAD:
        lines = [f"'{topic}' is too broad to cover in a single lesson or quiz. Could you narrow it down?"]
    elif check.status in (MISMATCH, OTHER_SUBJECT):
        lines = [f"'{topic}' doesn't look like a fit for {where}."]
    else:
        lines = [f"I couldn't find '{topic}' in the {where} standards."]
    found = [loc["grade_group"] for loc in _relevant_locations(check)][:3]
    if found:
        lines.append(f"(Standards search: related content appears in {', '.join(found)}.)")
    if check.narrower_topics:
        lines.append("Some options: " + " / ".join(check.narrower_topics))
    lines.append(
        "To change the grade, type it (e.g. 'Grade 8'), or type a different topic. "
        "To go ahead as entered, type 'use as is'."
    )
    return "\n\n".join(lines)
