"""수정 전파(edit-propagation) 판단 로직 — 종합 프로젝트 핵심 요구사항.

두 가지를 판단한다:
1. `classify_edit_target()` — 채팅으로 들어온 수정 요청이 수업계획안 얘기인지
   학생 활동지 얘기인지 (README 15번에 적어뒀던 한계를 메우는 부분)
2. `worksheet_needs_update()` — 수업계획안이 수정됐을 때 이미 만들어진 학생
   활동지도 같이 고쳐야 하는지

둘 다 LLM을 새로 호출하는 분류 단계를 넣는 대신 규칙/필드 비교로 결정한다.
이 프로젝트 전반의 방침("크레딧 없이도 핵심 로직은 검증 가능해야 한다",
`worksheet_needs_update`가 원래 이렑게 설계된 이유와 동일)과 일관되고,
순수 함수라 네트워크 없이 유닛 테스트로 완전히 검증할 수 있다.
"""
from __future__ import annotations

# worksheet.py의 _build_prompt()가 실제로 읽는 lesson_plan 필드들.
# 이 목록을 벗어난 필드(예: 평가_루브릭, 배경_읽기_자료)만 바뀐 경우는
# 활동지를 다시 만들 필요가 없다.
WORKSHEET_RELEVANT_FIELDS = ["topic", "subject", "grade", "토론_쟁점", "수업_흐름"]

# 메시지에 이 중 하나라도 들어있으면 "활동지 얘기"로 분류한다. 완벽한 NLU가
# 아니라 단순 키워드 매칭이라 "토론 쟁점도 줄이고 활동지 질문도 줄여줘"처럼
# 계획안과 활동지를 한 메시지에서 동시에 언급하는 경우는 활동지 쪽으로만
# 분류되고 계획안 쪽 요청은 반영되지 않는 한계가 있다 (알려진 단순화).
_WORKSHEET_KEYWORDS = ["활동지", "학생 활동", "워크시트", "활동 자료"]


def classify_edit_target(message: str, has_worksheet: bool) -> str:
    """채팅 수정 요청이 "plan"(수업계획안) 얘기인지 "worksheet"(학생 활동지) 얘기인지 분류한다.

    활동지가 아직 없으면(has_worksheet=False) 고칠 대상 자체가 없으니 항상
    "plan"으로 분류한다 — 활동지를 아직 안 만들었는데 활동지 얘기를 하는
    메시지는 여기서 분류할 게 아니라, 호출하는 쪽(chat_app.py)이 "아직
    활동지가 없다"는 안내로 따로 처리한다.
    """
    if has_worksheet and any(kw in message for kw in _WORKSHEET_KEYWORDS):
        return "worksheet"
    return "plan"


def worksheet_needs_update(old_plan: dict, new_plan: dict) -> bool:
    """수업계획안 수정 후, 이미 만들어진 학생 활동지도 다시 만들어야 하는지 판단한다.

    old_plan이 없으면(최초 생성이라 비교 대상이 없으면) 활동지가 아직 없을
    상황이므로 False를 반환한다 — 활동지 최초 생성은 사용자가 명시적으로
    버튼을 눌러 시작하는 별도 흐름(opt-in)이라 여기서 트리거하지 않는다.
    """
    if not old_plan:
        return False
    return any(old_plan.get(field) != new_plan.get(field) for field in WORKSHEET_RELEVANT_FIELDS)
