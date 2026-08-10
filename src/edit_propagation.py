"""수정 전파(edit-propagation) 판단 로직 — 종합 프로젝트 핵심 요구사항.

수업계획안이 수정됐을 때 이미 만들어진 학생 활동지도 같이 고쳐야 하는지를
판단한다. 별도 LLM 분류 단계("이 수정이 활동지에 영향을 주나요?")를 새로
만드는 대신, worksheet.py의 프롬프트(_build_prompt)가 실제로 참고하는
필드 목록과 정확히 같은 필드 집합을 비교해서 판단한다 — "활동지 생성에
쓰이는 입력이 바뀌지 않았으면 활동지도 바뀔 이유가 없다"는 논리라서,
LLM에게 다시 묻는 것보다 결정적이고 테스트하기 쉽다.

두 함수 모두 순수 함수(네트워크 호출 없음)라 chat_app.py의 오케스트레이션
로직(어느 함수를 호출할지)과 분리해서 여기서 단위 테스트한다.
"""
from __future__ import annotations

# worksheet.py의 _build_prompt()가 실제로 읽는 lesson_plan 필드들.
# 이 목록을 벗어난 필드(예: 평가_루브릭, 배경_읽기_자료)만 바뀐 경우는
# 활동지를 다시 만들 필요가 없다.
WORKSHEET_RELEVANT_FIELDS = ["topic", "subject", "grade", "토론_쟁점", "수업_흐름"]


def worksheet_needs_update(old_plan: dict, new_plan: dict) -> bool:
    """수업계획안 수정 후, 이미 만들어진 학생 활동지도 다시 만들어야 하는지 판단한다.

    old_plan이 없으면(최초 생성이라 비교 대상이 없으면) 활동지가 아직 없을
    상황이므로 False를 반환한다 — 활동지 최초 생성은 사용자가 명시적으로
    버튼을 눌러 시작하는 별도 흐름(opt-in)이라 여기서 트리거하지 않는다.
    """
    if not old_plan:
        return False
    return any(old_plan.get(field) != new_plan.get(field) for field in WORKSHEET_RELEVANT_FIELDS)
