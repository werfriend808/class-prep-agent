"""Quiz Activity: 퀴즈 문항 생성 (종합 프로젝트).

lesson_plan.py/worksheet.py와 같은 패턴이다: LLM(llm.complete(), .env의
LLM_PROVIDER를 따름)으로 문항 JSON을 생성한다. 실패 시 한 번 자동 재시도하는
것도 동일(worksheet.py에서 실제로 겪은 클로바 간헐적 형식 오류에 대응하기
위해 lesson_plan.py/worksheet.py에 먼저 붙인 패턴을 그대로 가져왔다).

토의·토론/PBL과 달리 Quiz는 산출물이 하나(퀴즈 문항 → Google Forms)뿐이라
edit_propagation.py 같은 "여러 산출물 중 어디를 고칠지" 판단 로직이 필요
없다 — 수정 요청은 항상 문항 전체를 다시 생성하고 같은 Form에 반영한다.

2026-08-26: 원래 NCIC 근거(ncic_matcher)를 붙였는데, 영어 "문법"처럼 2022
개정 교육과정 성취기준 문구에 아예 안 나오는 주제는 키워드 매칭이 전부 0점이
되고, 그러면 match_standards()가 무관한 성취기준(예: 독해 성취기준)을 그대로
반환해서 프롬프트에 "문법 문제를 내라면서 참고자료는 독해"라는 모순된 지시가
섞여 들어갔다. 실사용 중 이상한 문항이 나오는 걸로 발견됐고(Stanley), NCIC
근거 기능 자체를 제거하기로 결정했다(lesson_plan.py도 동일 구조라 같이 제거
— 자세한 배경은 README 18-6-2 참고).

2026-08-26: 실사용 중 정답 표시 자체가 틀리는 문제가 발견됐다(Stanley) —
예를 들어 "축구에서 득점을 올리는 것을 무엇이라고 부르나요?"라는 문항에서
해설(explanation)은 "'골'이라고 부릅니다"로 정확했는데, 실제 Google Forms에
반영된 정답은 "세이브"였다. 원인은 LLM이 correct_index(0-based 정수)를
셀 때 가끔 실수를 한다는 것으로 보인다 — 같은 문항 안에서 해설 문장은 정답을
말로 정확히 서술하면서도, 그 정답이 options 배열의 몇 번째인지 세는
과정에서만 다른 값을 내놓는 비일관성이었다(JSON 자체는 유효해서 기존
검증(0 <= correct_index < len(options))도 이 오류를 걸러내지 못했다). 인덱스를
세는 것보다 정답 문구를 그대로 옮겨 적는 편이 LLM에게 더 쉬운 작업이라고
보고, LLM에게 요구하는 필드를 correct_index(정수)에서 correct_answer(정답
선택지의 텍스트, options 중 하나와 정확히 일치)로 바꿨다. 파싱 단계
(`_parse_quiz_json`)에서 문자열 일치로 correct_index를 역산하고, 일치하는
보기가 없으면 QuizError를 올려 기존 재시도 정책(1회)이 그대로 작동하게
했다 — options/correct_index 기반의 나머지 코드(forms_writer.py,
chat_app.py)는 그대로 correct_index를 쓰므로 이 변경은 생성 단계에만
국한된다.
"""
from __future__ import annotations

import json
import re

from .llm import complete

QUESTION_COUNT = 5
MIN_OPTIONS = 2
MAX_OPTIONS = 6
DEFAULT_OPTION_COUNT = 4


class QuizError(RuntimeError):
    """퀴즈 생성 실패(크레딧 부족, 응답 파싱/검증 실패 등)를 UI에 알리기 위한 예외."""


def _build_prompt(
    subject: str,
    grade: str,
    topic: str,
    revision_request: str | None,
    current_questions: list[dict] | None = None,
) -> str:
    if revision_request and current_questions:
        # 수정 요청이 "1번 문항 보기를 3개로 줄여줘"처럼 특정 문항을 지목할 수 있는데,
        # 기존에는 현재 문항 내용을 프롬프트에 전혀 안 넘기고 매번 백지에서 5개를 새로
        # 만들었다 — "1번 문항"이 뭔지 LLM이 알 방법이 없어 요청과 무관한 다른 문항까지
        # 같이 흔들리는 문제가 실사용 중 발견됐다(2026-08-26). 현재 문항을 그대로 보여주고
        # 그걸 기준으로 고치라고 지시해서 지목형 수정 요청이 안정적으로 반영되게 한다.
        current_text = "\n".join(
            f"{i + 1}. {q['question']}\n"
            + "\n".join(
                f"   {chr(97 + j)}) {opt}" + (" [정답]" if j == q.get("correct_index") else "")
                for j, opt in enumerate(q.get("options", []))
            )
            for i, q in enumerate(current_questions)
        )
        revision_note = (
            f"\n\n[현재 문항]\n{current_text}\n\n"
            f"[수정 요청]\n위 현재 문항을 기준으로 다음 피드백을 반영해서 문항 전체를 "
            f"다시 작성해주세요(요청에서 언급하지 않은 문항이나 보기는 가능한 한 원래 "
            f"내용을 그대로 유지하세요): {revision_request}"
        )
    elif revision_request:
        revision_note = (
            f"\n\n[수정 요청]\n이전 문항에 대해 다음 피드백을 반영해서 다시 작성해주세요: {revision_request}"
        )
    else:
        revision_note = ""
    return (
        f"당신은 {grade} {subject} 교사를 돕는 평가 문항 출제 도우미입니다. "
        f"아래 단원/주제에 대한 이해도를 확인하는 객관식 퀴즈를 만들어주세요.\n\n"
        f"단원/주제: {topic}\n\n"
        f"정확히 {QUESTION_COUNT}개의 문항을 담은 JSON 객체로만 답하세요 (다른 설명 없이 JSON만): "
        '{"questions": [{"question": "문항 텍스트", '
        '"options": ["선택지1", "선택지2", "선택지3", "선택지4"], '
        '"correct_answer": "정답 선택지의 텍스트 (options 중 하나와 완전히 동일한 문자열이어야 함, 인덱스 아님)", '
        '"explanation": "정답 해설"}, ...]}. '
        f"options 개수는 보기를 늘리거나 줄여달라는 별도 요청이 없으면 기본 {DEFAULT_OPTION_COUNT}개로 하고, "
        f"보기 개수 조정을 원한다는 내용이 있으면 그에 맞게 조정하되 "
        f"{MIN_OPTIONS}개 이상 {MAX_OPTIONS}개 이하로만 작성하세요. 각 문항의 options는 "
        f"서로 명확히 구분되게 작성하고, 정답은 하나만 있어야 합니다. correct_answer는 반드시 "
        f"options 목록에 있는 문자열 중 하나를 그대로 옮겨 적으세요(번호나 순서를 세지 말고 "
        f"정답 선택지의 실제 텍스트를 적으세요)."
        f"{revision_note}"
    )


def _generate_once(prompt: str) -> dict:
    try:
        raw_text = complete(prompt, max_tokens=2000)
    except Exception as e:  # noqa: BLE001 — 크레딧 부족, 네트워크 오류 등 예상 밖 오류 포함
        raise QuizError(f"퀴즈 생성에 실패했어요 (LLM 호출 오류): {e}") from e
    return _parse_quiz_json(raw_text)


def generate_quiz(
    subject: str,
    topic: str,
    grade: str = "고1",
    revision_request: str | None = None,
    current_draft: dict | None = None,
) -> dict:
    """단원/주제에 대한 객관식 퀴즈를 생성한다.

    반환값: {"questions": [...], "subject", "grade", "topic"}.
    각 question은 {"question", "options"(기본 4개, 요청에 따라 2~6개), "correct_index", "explanation"}.
    실패 시(크레딧 부족, JSON 파싱/검증 실패 등) QuizError를 올린다. LLM이
    가끔 형식 지시를 안 지키는 간헐적 현상에 대응해 실패하면 한 번만 자동
    재시도하고, 그래도 실패하면 그대로 올린다(lesson_plan.py/worksheet.py와
    동일한 정책).
    """
    current_questions = current_draft.get("questions") if current_draft else None

    prompt = _build_prompt(subject, grade, topic, revision_request, current_questions)

    try:
        result = _generate_once(prompt)
    except QuizError:
        result = _generate_once(prompt)

    result["subject"] = subject
    result["grade"] = grade
    result["topic"] = topic
    return result


def _parse_quiz_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise QuizError("LLM 응답을 퀴즈 형식으로 해석하지 못했어요. 다시 시도해주세요.") from e

    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list) or not questions:
        raise QuizError("LLM 응답에 문항(questions) 목록이 없어요. 다시 시도해주세요.")

    validated: list[dict] = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise QuizError(f"{i + 1}번 문항 형식이 올바르지 않아요.")
        options = q.get("options")
        if not isinstance(options, list) or not (MIN_OPTIONS <= len(options) <= MAX_OPTIONS):
            raise QuizError(
                f"{i + 1}번 문항의 선택지 개수가 올바르지 않아요 "
                f"({MIN_OPTIONS}개 이상 {MAX_OPTIONS}개 이하여야 해요)."
            )
        stripped_options = [str(o).strip() for o in options]
        correct_answer = q.get("correct_answer")
        if not isinstance(correct_answer, str) or not correct_answer.strip():
            raise QuizError(f"{i + 1}번 문항에 정답(correct_answer)이 없어요.")
        correct_answer_stripped = correct_answer.strip()
        if correct_answer_stripped not in stripped_options:
            # LLM이 정답 텍스트를 보기 중 하나와 다르게(오타, 재서술 등) 적은 경우 —
            # 인덱스를 역산할 방법이 없으므로 재시도를 유도한다(quiz.py의 기존
            # 1회 재시도 정책, generate_quiz 참고).
            raise QuizError(f"{i + 1}번 문항의 정답(correct_answer)이 보기 중에 없어요.")
        correct_index = stripped_options.index(correct_answer_stripped)
        question_text = str(q.get("question", "")).strip()
        if not question_text:
            raise QuizError(f"{i + 1}번 문항에 문제 텍스트가 없어요.")
        validated.append(
            {
                "question": question_text,
                "options": stripped_options,
                "correct_index": correct_index,
                "explanation": str(q.get("explanation", "")).strip(),
            }
        )

    return {"questions": validated}
