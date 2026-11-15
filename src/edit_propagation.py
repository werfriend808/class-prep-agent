"""수정 전파(edit-propagation) 판단 로직 — 종합 프로젝트 핵심 요구사항.

`worksheet_needs_update()` — 수업계획안이 수정됐을 때 이미 만들어진 학생
활동지도 같이 고쳐야 하는지 판단한다.

LLM을 새로 호출하는 분류 단계를 넣는 대신 필드 비교로 결정한다. 이 프로젝트
전반의 방침("크레딧 없이도 핵심 로직은 검증 가능해야 한다")과 일관되고, 순수
함수라 네트워크 없이 유닛 테스트로 완전히 검증할 수 있다.

2026-11-14: 예전엔 채팅 수정 요청이 계획안 얘기인지 활동지 얘기인지를 키워드로
추측하는 `classify_edit_target()`도 여기 있었다. "질문을 쉽게 바꿔줘"처럼
'활동지'라는 단어 없이 활동지를 말하면 계획안으로 잘못 보내는 한계가 있어서,
chat_app이 사용자에게 수정 대상을 직접 고르게 바꾸면서 지웠다.
"""
from __future__ import annotations

# worksheet.py의 _build_prompt()가 실제로 읽는 lesson_plan 필드들.
# 이 목록을 벗어난 필드(예: 평가_루브릭, 배경_읽기_자료)만 바뀐 경우는
# 활동지를 다시 만들 필요가 없다.
WORKSHEET_RELEVANT_FIELDS = ["topic", "subject", "grade", "토론_쟁점", "수업_흐름"]
WORKSHEET_RELEVANT_FIELDS_US = ["topic", "subject", "grade", "discussion_issues", "lesson_flow"]

def worksheet_needs_update(old_plan: dict, new_plan: dict, locale: str = "ko") -> bool:
    """수업계획안 수정 후, 이미 만들어진 학생 활동지도 다시 만들어야 하는지 판단한다.

    old_plan이 없으면(최초 생성이라 비교 대상이 없으면) 활동지가 아직 없을
    상황이므로 False를 반환한다 — 활동지 최초 생성은 사용자가 명시적으로
    버튼을 눌러 시작하는 별도 흐름(opt-in)이라 여기서 트리거하지 않는다.
    """
    if not old_plan:
        return False
    fields = WORKSHEET_RELEVANT_FIELDS_US if locale == "us" else WORKSHEET_RELEVANT_FIELDS
    return any(old_plan.get(field) != new_plan.get(field) for field in fields)
