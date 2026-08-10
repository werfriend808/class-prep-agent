"""토의·토론 수업계획안 생성 (실전 프로젝트 2 핵심 기능).

LLM으로 계획안 본문(8개 섹션)을 생성하고, NCIC 근거(성취기준 코드/텍스트)는
LLM이 지어내지 않도록 우리 쪽 데이터(ncic_matcher)에서 직접 붙인다 — 성취기준
코드를 잘못 인용하는 것보다는 데이터셋에 실제로 있는 항목만 보여주는 게 안전하다.

`llm.complete()`를 통해 호출하므로 `.env`의 `LLM_PROVIDER` 설정(기본 Claude,
"clova"면 네이버 클로바 스튜디오)에 따라 실제 사용되는 provider가 바뀐다 —
자세한 내용은 llm.py 참고. 어느 쪽이든 크레딧/사용량이 있어야 동작한다.
크레딧이 없으면 LessonPlanError를 그대로 올려서 UI에서 안내 메시지로 보여준다
(실전 1의 요약과 달리 "계획안 생성" 자체가 핵심 기능이라 의미 있는 폴백이 없다).
"""
from __future__ import annotations

import json
import re

from .llm import complete
from .ncic_matcher import format_citation, match_standards

PLAN_SECTIONS = [
    "자료_개요",
    "수업_목표",
    "배경_읽기_자료",
    "핵심_개념",
    "토론_쟁점",
    "수업_흐름",
    "학생_활동지_예시",
    "평가_루브릭",
]


class LessonPlanError(RuntimeError):
    """계획안 생성 실패(크레딧 부족, 응답 파싱 실패 등)를 UI에 알리기 위한 예외."""


def extract_keywords(topic: str) -> list[str]:
    """주제 문장에서 NCIC 매칭에 쓸 핵심어를 뽑는다 (2글자 이상 토큰, 중복 제거)."""
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", topic)
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return seen


def _build_prompt(
    subject: str,
    grade: str,
    topic: str,
    ncic_records: list[dict],
    revision_request: str | None,
) -> str:
    ncic_context = "\n".join(f"- [{r['code']}] {r['text']}" for r in ncic_records) or "(관련 성취기준 없음)"
    sections_desc = ", ".join(PLAN_SECTIONS)
    revision_note = (
        f"\n\n[수정 요청]\n이전 초안에 대해 다음 피드백을 반영해서 다시 작성해주세요: {revision_request}"
        if revision_request
        else ""
    )
    return (
        f"당신은 고등학교 {subject} 교사를 돕는 수업 설계 도우미입니다. "
        f"{grade} 학생 대상 토의·토론 수업계획안을 아래 조건에 맞춰 작성해주세요.\n\n"
        f"주제: {topic}\n\n"
        f"참고할 국가교육과정 성취기준(2022 개정):\n{ncic_context}\n\n"
        f"다음 {len(PLAN_SECTIONS)}개 항목을 반드시 포함한 JSON 객체로만 답하세요 (다른 설명 없이 JSON만): "
        f"{sections_desc}. 각 값은 한국어 문자열이며, '수업_흐름'과 '학생_활동지_예시'는 "
        f"여러 줄(줄바꿈 포함)로 구체적으로 작성하세요."
        f"{revision_note}"
    )


def generate_lesson_plan(
    subject: str,
    topic: str,
    grade: str = "고1",
    revision_request: str | None = None,
) -> dict:
    """토의·토론 수업계획안을 생성한다.

    반환값에는 8개 섹션 텍스트 + "ncic_references"(근거 문자열 리스트),
    subject/grade/topic이 들어있다. 실패 시(크레딧 부족, JSON 파싱 실패 등)
    LessonPlanError를 올린다 — chat_app.py에서 st.error로 잡아서 보여준다.
    """
    keywords = extract_keywords(topic)
    ncic_records = match_standards(subject, grade=grade, keywords=keywords, limit=5)

    prompt = _build_prompt(subject, grade, topic, ncic_records, revision_request)

    try:
        raw_text = complete(prompt, max_tokens=2000)
    except Exception as e:  # noqa: BLE001 — 크레딧 부족, 네트워크 오류 등 예상 밖 오류 포함
        raise LessonPlanError(f"수업계획안 생성에 실패했어요 (LLM 호출 오류): {e}") from e

    plan = _parse_plan_json(raw_text)
    plan["ncic_references"] = [format_citation(r) for r in ncic_records]
    plan["subject"] = subject
    plan["grade"] = grade
    plan["topic"] = topic
    return plan


def _stringify_section(value: object) -> str:
    """섹션 값을 화면/Notion 마크다운에 그대로 쓸 수 있는 문자열로 정규화한다.

    프롬프트에 "각 값은 문자열로"라고 명시했는데도, 실제로 클로바(HyperCLOVA X)로
    생성해보니 일부 섹션(배경 읽기 자료, 핵심 개념, 수업 흐름, 학생 활동지 예시,
    평가 루브릭)이 문자열 대신 리스트나 중첩 딕셔너리로 오는 경우가 있었다
    (scripts/verify_lesson_plan_generation.py로 실제 확인). 이걸 그냥
    str(value)로 넘기면 Notion 본문에 `['항목1', '항목2']` 같은 파이썬 문법이
    그대로 노출된다 — 리스트/딕셔너리는 사람이 읽기 좋은 형태로 변환한다.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(f"- {_stringify_section(item)}" for item in value)
    if isinstance(value, dict):
        lines = []
        for key, val in value.items():
            if isinstance(val, dict):
                sub = ", ".join(f"{sk}({sv})" for sk, sv in val.items())
                lines.append(f"- {key}: {sub}")
            elif isinstance(val, list):
                lines.append(f"- {key}: {', '.join(str(v) for v in val)}")
            else:
                lines.append(f"- {key}: {val}")
        return "\n".join(lines)
    return str(value)


def _parse_plan_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LessonPlanError("LLM 응답을 계획안 형식으로 해석하지 못했어요. 다시 시도해주세요.") from e

    missing = [s for s in PLAN_SECTIONS if s not in data]
    if missing:
        raise LessonPlanError(f"응답에 필요한 항목이 빠졌어요: {', '.join(missing)}")
    return {k: _stringify_section(data[k]) for k in PLAN_SECTIONS}
