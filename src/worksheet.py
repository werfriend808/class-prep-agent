"""토의·토론 학생 활동지 생성 (종합 프로젝트: 수업계획안 → 학생 활동지 확장).

lesson_plan.py가 만든 수업계획안(dict)을 입력으로 받아, 학생이 수업 중 실제로
들고 쓸 수 있는 활동지를 LLM으로 생성한다. 계획안의 '학생_활동지_예시' 섹션은
교사 참고용 한두 줄 요약이라 그대로 Google Docs에 옮기기엔 부족해서, 여기서
계획안의 주제/쟁점/흐름을 참고해 학생이 직접 답을 채워 넣는 질문/빈칸 형태로
새로 확장 생성한다.

lesson_plan.py와 마찬가지로 llm.complete()를 통해 호출하므로 .env의
LLM_PROVIDER 설정을 그대로 따른다.
"""
from __future__ import annotations

import json
import re

from .lesson_plan import _stringify_section
from .llm import complete

WORKSHEET_SECTIONS = [
    "활동_안내",
    "배경_자료_요약",
    "토론_질문",
    "개인_의견_작성란",
    "모둠_토의_기록표",
    "소감_정리",
]

_SECTION_TITLES = {
    "활동_안내": "활동 안내",
    "배경_자료_요약": "배경 자료 요약",
    "토론_질문": "토론 질문",
    "개인_의견_작성란": "개인 의견 작성란",
    "모둠_토의_기록표": "모둠 토의 기록표",
    "소감_정리": "소감 정리",
}


class WorksheetError(RuntimeError):
    """활동지 생성 실패를 UI에 알리기 위한 예외."""


def _build_prompt(plan: dict, revision_request: str | None) -> str:
    sections_desc = ", ".join(WORKSHEET_SECTIONS)
    revision_note = (
        f"\n\n[수정 요청]\n이전 활동지에 대해 다음 피드백을 반영해서 다시 작성해주세요: {revision_request}"
        if revision_request
        else ""
    )
    return (
        f"당신은 고등학교 {plan.get('subject', '')} 교사를 돕는 수업 설계 도우미입니다. "
        f"아래 수업계획안을 바탕으로 {plan.get('grade', '')} 학생들이 수업 중 직접 "
        f"작성하며 사용할 학생 활동지를 만들어주세요. 교사용 설명이 아니라 학생이 "
        f"읽고 빈칸을 채우는 형태여야 합니다.\n\n"
        f"주제: {plan.get('topic', '')}\n"
        f"토론 쟁점: {plan.get('토론_쟁점', '')}\n"
        f"수업 흐름: {plan.get('수업_흐름', '')}\n\n"
        f"다음 {len(WORKSHEET_SECTIONS)}개 항목을 반드시 포함한 JSON 객체로만 답하세요 "
        f"(다른 설명 없이 JSON만): {sections_desc}. '개인_의견_작성란'과 "
        f"'모둠_토의_기록표'는 학생이 직접 쓸 수 있도록 질문과 빈칸 형태로 작성하고, "
        f"각 값은 한국어 문자열(여러 줄 가능)로 작성하세요."
        f"{revision_note}"
    )


def _generate_once(prompt: str) -> dict:
    try:
        raw_text = complete(prompt, max_tokens=1500)
    except Exception as e:  # noqa: BLE001 — 크레딧 부족, 네트워크 오류 등 예상 밖 오류 포함
        raise WorksheetError(f"학생 활동지 생성에 실패했어요 (LLM 호출 오류): {e}") from e
    return _parse_worksheet_json(raw_text)


def generate_worksheet(plan: dict, revision_request: str | None = None) -> dict:
    """수업계획안(dict)을 바탕으로 학생 활동지를 생성한다.

    반환값에는 WORKSHEET_SECTIONS 6개 섹션 + topic/subject/grade가 들어있다.
    revision_request를 넘기면 기존 활동지에 대한 수정 요청으로 취급해 다시
    생성한다 (수정 결과를 어느 doc_id에 반영할지는 이 함수의 책임이 아니고,
    호출하는 쪽에서 google_docs_writer.replace_doc_body로 반영한다).

    실제로 겪은 사례: 클로바(HyperCLOVA X)가 "JSON만 답하라"는 지시를 가끔
    안 지켜서 파싱이 실패하는데, 같은 요청을 그대로 다시 보내면 정상적으로
    나온다 — 간헐적 현상이라 판단해 실패하면 한 번만 자동으로 재시도한다.
    재시도까지 실패하면(계속되는 형식 오류, 크레딧 부족 등) 그때는
    WorksheetError를 그대로 올려서 사용자가 직접 다시 시도하게 한다.
    """
    prompt = _build_prompt(plan, revision_request)

    try:
        worksheet = _generate_once(prompt)
    except WorksheetError:
        worksheet = _generate_once(prompt)

    worksheet["topic"] = plan.get("topic", "")
    worksheet["subject"] = plan.get("subject", "")
    worksheet["grade"] = plan.get("grade", "")
    return worksheet


def _parse_worksheet_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise WorksheetError("LLM 응답을 활동지 형식으로 해석하지 못했어요. 다시 시도해주세요.") from e

    missing = [s for s in WORKSHEET_SECTIONS if s not in data]
    if missing:
        raise WorksheetError(f"응답에 필요한 항목이 빠졌어요: {', '.join(missing)}")
    return {k: _stringify_section(data[k]) for k in WORKSHEET_SECTIONS}


def worksheet_to_text(worksheet: dict) -> str:
    """generate_worksheet()의 결과 dict를 Google Docs 본문용 plain text로 변환.

    notion_writer.plan_to_markdown()과 대칭되는 역할이지만, Google Docs
    batchUpdate의 insertText는 마크다운을 렌더링하지 않는 순수 텍스트라
    "#"/"##" 같은 마크다운 문법 대신 줄바꿈으로만 구분한다.
    """
    lines = [f"{worksheet.get('topic', '')} 학생 활동지", ""]
    lines.append(f"과목: {worksheet.get('subject', '')}  |  대상: {worksheet.get('grade', '')}")
    lines.append("")
    for key in WORKSHEET_SECTIONS:
        lines.append(_SECTION_TITLES.get(key, key))
        lines.append(str(worksheet.get(key, "")))
        lines.append("")
    return "\n".join(lines)
