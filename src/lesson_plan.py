"""토의·토론 수업계획안 생성 (실전 프로젝트 2 핵심 기능).

Claude API로 계획안 본문(8개 섹션)을 생성하고, NCIC 근거(성취기준 코드/텍스트)는
LLM이 지어내지 않도록 우리 쪽 데이터(ncic_matcher)에서 직접 붙인다 — 성취기준
코드를 잘못 인용하는 것보다는 데이터셋에 실제로 있는 항목만 보여주는 게 안전하다.

주의: 이 모듈은 Claude API 크레딧이 있어야 실제로 동작한다. 실전 1의 요약과
달리 "계획안 생성" 자체가 핵심 기능이라 의미 있는 폴백이 없다 — 크레딧이
없으면 LessonPlanError를 그대로 올려서 UI에서 안내 메시지로 보여준다.
"""
from __future__ import annotations

import json
import re

from .config import SUMMARY_MODEL
from .llm import get_client
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
        client = get_client()
        message = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = message.content[0].text
    except Exception as e:  # noqa: BLE001 — 크레딧 부족, 네트워크 오류 등 예상 밖 오류 포함
        raise LessonPlanError(f"수업계획안 생성에 실패했어요 (Claude API 호출 오류): {e}") from e

    plan = _parse_plan_json(raw_text)
    plan["ncic_references"] = [format_citation(r) for r in ncic_records]
    plan["subject"] = subject
    plan["grade"] = grade
    plan["topic"] = topic
    return plan


def _parse_plan_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LessonPlanError("Claude 응답을 계획안 형식으로 해석하지 못했어요. 다시 시도해주세요.") from e

    missing = [s for s in PLAN_SECTIONS if s not in data]
    if missing:
        raise LessonPlanError(f"응답에 필요한 항목이 빠졌어요: {', '.join(missing)}")
    return {k: data[k] for k in PLAN_SECTIONS}
