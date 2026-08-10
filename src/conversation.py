"""멀티턴 대화 상태 관리.

대화 방식은 README 부록의 "커스터마이징 결정 포인트" 중 "순차 질문 수집 후
초안 생성 → 피드백 반영 수정"(혼합형)으로 정했다. 이유:
  1) 정보 수집 단계(과목/주제)는 규칙 기반으로 처리할 수 있어 Claude API
     크레딧 없이도 대화 흐름 자체는 끝까지 테스트할 수 있다 (실제 수업계획안
     "생성" 한 걸음만 LLM이 필요).
  2) 자유 입력창 하나에 다 적게 하는 것보다, 필요한 정보를 순서대로 물어보는
     쪽이 실전 1의 FILTER 질의처럼 값을 명확하게 얻을 수 있어 이후 NCIC
     매칭(ncic_matcher.py)에 바로 쓰기 좋다.

상태 전이:
    COLLECTING (과목 -> 주제 순으로 질문) -> READY (모두 수집됨, 생성 트리거 대기)
    -> DRAFTED (수업계획안 생성 완료, 사용자에게 보여줌)
    -> REVISING (사용자가 수정 요청) -> DRAFTED (재생성) ... 반복 가능
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    COLLECTING = "collecting"
    READY = "ready"
    DRAFTED = "drafted"
    REVISING = "revising"


# 구체적인 과목명을 먼저 검사해야 "사회"가 "통합사회"/"한국사"를 삼키지 않는다.
_SUBJECT_KEYWORDS = ["통합사회", "한국사", "국어", "수학", "영어", "사회"]
_GRADE_PATTERN_KEYWORDS = {"고1": "고1", "고2": "고2", "고3": "고3", "1학년": "고1", "2학년": "고2", "3학년": "고3"}

DEFAULT_GRADE = "고1"  # 현재 ncic_standards 데이터셋이 고1 공통 과목뿐이라 기본값으로 둔다.

SLOT_QUESTIONS = {
    "subject": "어떤 과목의 토의·토론 수업을 준비할까요? (예: 국어, 수학, 영어, 사회/통합사회/한국사)",
    "topic": "어떤 주제나 소재로 진행하고 싶으신가요? (예: '환경 보전과 개발 중 무엇을 우선해야 하는가')",
}
REQUIRED_SLOTS = ["subject", "topic"]


def extract_subject(text: str) -> str | None:
    for kw in _SUBJECT_KEYWORDS:
        if kw in text:
            return kw
    return None


def extract_grade(text: str) -> str | None:
    for kw, grade in _GRADE_PATTERN_KEYWORDS.items():
        if kw in text:
            return grade
    return None


@dataclass
class ConversationState:
    phase: Phase = Phase.COLLECTING
    slots: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # [{"role": "user"/"assistant", "content": str}]
    draft: dict | None = None  # lesson_plan.generate_lesson_plan()의 결과
    notion_url: str | None = None

    def missing_slots(self) -> list[str]:
        return [s for s in REQUIRED_SLOTS if s not in self.slots]

    def next_question(self) -> str | None:
        missing = self.missing_slots()
        if not missing:
            return None
        return SLOT_QUESTIONS[missing[0]]

    def _record(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def handle_message(self, message: str) -> str:
        """사용자 메시지 하나를 처리하고, 챗봇이 다음에 보여줄 응답 문자열을 반환한다.

        COLLECTING 단계에서는 규칙 기반으로 슬롯을 채우고 다음 질문을 반환한다.
        READY/DRAFTED/REVISING 단계에서 실제로 수업계획안을 만들거나 고치는 것은
        이 클래스의 책임이 아니다 — 그건 lesson_plan.py가 하고, 여기서는 상태
        전이(무엇을 물어야 하는지, 지금 뭘 해야 하는지)만 관리한다. UI(chat_app.py)
        가 READY/REVISING 상태를 보고 lesson_plan.generate_lesson_plan()을 호출한다.
        """
        self._record("user", message)

        if self.phase == Phase.COLLECTING:
            missing = self.missing_slots()
            if not missing:
                self.phase = Phase.READY
                return self._advance_and_get_reply()

            current_slot = missing[0]
            if current_slot == "subject":
                subject = extract_subject(message)
                if subject is None:
                    reply = "죄송해요, 어떤 과목인지 못 알아들었어요. 국어/수학/영어/사회(또는 통합사회, 한국사) 중에서 골라주세요."
                    self._record("assistant", reply)
                    return reply
                self.slots["subject"] = subject
                grade = extract_grade(message)
                self.slots["grade"] = grade or DEFAULT_GRADE
            elif current_slot == "topic":
                topic = message.strip()
                if not topic:
                    reply = "주제를 조금 더 구체적으로 말씀해주시겠어요?"
                    self._record("assistant", reply)
                    return reply
                self.slots["topic"] = topic

            return self._advance_and_get_reply()

        if self.phase in (Phase.DRAFTED,):
            # 초안을 본 뒤 사용자가 뭔가 말하면 "수정 요청"으로 간주하고 REVISING으로 전환.
            # (수락/저장 의사는 chat_app.py에서 별도 버튼으로 받는다 — 자유 텍스트로
            # "괜찮아요/저장해줘" 같은 승낙 문구까지 규칙으로 구분하는 건 오탐이 잦아서
            # 명시적인 버튼 액션으로 분리했다.)
            self.slots["revision_request"] = message.strip()
            self.phase = Phase.REVISING
            reply = "알겠습니다. 말씀하신 내용을 반영해서 다시 만들어볼게요."
            self._record("assistant", reply)
            return reply

        reply = "지금은 다른 처리 중이에요. 잠시만 기다려주세요."
        self._record("assistant", reply)
        return reply

    def _advance_and_get_reply(self) -> str:
        next_q = self.next_question()
        if next_q is not None:
            self._record("assistant", next_q)
            return next_q
        self.phase = Phase.READY
        reply = (
            f"{self.slots['subject']} 과목, '{self.slots['topic']}' 주제로 "
            f"{self.slots.get('grade', DEFAULT_GRADE)} 토의·토론 수업계획안을 만들어볼게요. 잠시만 기다려주세요."
        )
        self._record("assistant", reply)
        return reply

    def apply_draft(self, draft: dict) -> None:
        self.draft = draft
        self.phase = Phase.DRAFTED
        self.slots.pop("revision_request", None)

    def reset(self) -> None:
        self.phase = Phase.COLLECTING
        self.slots = {}
        self.draft = None
        self.notion_url = None
