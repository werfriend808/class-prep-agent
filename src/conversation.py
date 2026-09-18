"""멀티턴 대화 상태 관리.

대화 방식은 README 부록의 "커스터마이징 결정 포인트" 중 "순차 질문 수집 후
초안 생성 → 피드백 반영 수정"(혼합형)으로 정했다. 이유:
  1) 정보 수집 단계(과목/주제)는 규칙 기반으로 처리할 수 있어 LLM 크레딧
     없이도 대화 흐름 자체는 끝까지 테스트할 수 있다 (실제 수업계획안
     "생성" 한 걸음만 LLM이 필요).
  2) 자유 입력창 하나에 다 적게 하는 것보다, 필요한 정보를 순서대로 물어보는
     쪽이 실전 1의 FILTER 질의처럼 값을 명확하게 얻을 수 있어 이후 NCIC
     매칭(ncic_matcher.py)에 바로 쓰기 좋다.

상태 전이:
    COLLECTING (과목 -> 학년 -> 주제 순으로 질문) -> READY (모두 수집됨, 생성 트리거 대기)
    -> DRAFTED (수업계획안 생성 완료, 사용자에게 보여줌)
    -> REVISING (사용자가 수정 요청) -> DRAFTED (재생성) ... 반복 가능

2026-09-17 (Phase 3, 영어/미국 버전 첫 단계): ConversationState에 `locale`
필드를 추가해 "us"일 때는 영어 슬롯 질문/응답(`extract_subject_us`,
`extract_grade_us`, `SLOT_QUESTIONS_US`)을 쓰도록 분기했다. 기존 한국어
경로(`locale` 기본값 "ko")는 이 파일의 다른 함수/상수를 하나도 안 바꿔서
동작이 그대로다. QuizConversationState는 이번 범위 밖이라(오늘은 토의·토론
흐름만 영어로 만들기로 함) 그대로 한국어 전용 extract_subject/extract_grade를
쓴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .curriculum import get_provider


class Phase(str, Enum):
    COLLECTING = "collecting"
    READY = "ready"
    DRAFTED = "drafted"
    REVISING = "revising"


# 구체적인 과목명을 먼저 검사해야 "사회"가 "통합사회"/"한국사"를 삼키지 않는다.
# ncic_standards/achievement_standards.json(전체 학년/과목, 4,199건)에 있는
# 16개 과목 전부를 인식하도록 확장했다 (과제 스펙의 "대상 학년/과목: 전체
# 제한 없음" 요구사항 반영 — 예전엔 고1 공통 과목 5개만 지원했었다).
_SUBJECT_KEYWORDS = [
    "통합사회", "한국사", "국어", "수학", "영어", "사회",
    "도덕", "과학", "음악", "미술", "체육", "한문", "제2외국어",
    "교양", "정보", "기술가정", "실과",
]

# "초3", "중2", "고1"처럼 데이터셋(ncic_matcher.grade_bands_for)이 바로 알아듣는
# 표기로 정규화한다. 학교급 없이 "3학년"만 말하면 어느 학교급인지 알 수 없어
# 인식하지 못한 것으로 처리하고 재질문한다(학년을 학교급 없이 잘못 넘기면
# ncic_matcher가 엉뚱한 학년군을 찾게 된다).
_GRADE_PATTERN = re.compile(
    r"(초등학교|초등|초)\s*([1-6])\s*학년|(중학교|중)\s*([1-3])\s*학년|(고등학교|고)\s*([1-3])\s*학년"
    r"|(초)([1-6])(?!\d)|(중)([1-3])(?!\d)|(고)([1-3])(?!\d)"
)
_LEVEL_MAP = {"초등학교": "초", "초등": "초", "초": "초", "중학교": "중", "중": "중", "고등학교": "고", "고": "고"}

DEFAULT_GRADE = "고1"  # 학년을 끝내 못 알아들었을 때만 쓰는 최후 폴백.

SLOT_QUESTIONS = {
    "subject": "어떤 과목의 토의·토론 수업을 준비할까요? (예: 국어, 수학, 영어, 사회, 과학, 도덕, 음악, 미술, 체육 등)",
    "grade": "몇 학년 대상인가요? (예: 초등학교 3학년, 중학교 2학년, 고등학교 1학년)",
    "topic": "어떤 주제나 소재로 진행하고 싶으신가요? (예: '환경 보전과 개발 중 무엇을 우선해야 하는가')",
}
REQUIRED_SLOTS = ["subject", "grade", "topic"]

SLOT_QUESTIONS_US = {
    "subject": "What subject would you like to prepare a discussion lesson for? (Math is currently supported.)",
    "grade": "What grade level is this for? (e.g. Kindergarten, Grade 3, 9th grade / freshman)",
    "topic": "What topic or issue would you like to focus on? "
    "(e.g. 'Should we prioritize environmental protection or economic development?')",
}


def extract_subject(text: str) -> str | None:
    for kw in _SUBJECT_KEYWORDS:
        if kw in text:
            return kw
    return None


def extract_grade(text: str) -> str | None:
    m = _GRADE_PATTERN.search(text)
    if not m:
        return None
    groups = m.groups()
    # 세 가지 하위 패턴(학교급+"N학년" / 학교급+숫자) 중 어느 것이 매칭됐는지 순서대로 확인
    for level_idx, num_idx in ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11)):
        level_raw, num = groups[level_idx], groups[num_idx]
        if level_raw and num:
            return f"{_LEVEL_MAP[level_raw]}{num}"
    return None


# --- 영어/미국(Common Core Math) 버전 슬롯 추출 -----------------------------
# 과목은 하드코딩하지 않고 현재 활성화된 CurriculumProvider(LOCALE=us면
# CommonCoreMathProvider)의 subjects()를 그대로 쓴다 — Phase 2 README가 밝힌
# 대로 나중에 Math 외 과목이 추가돼도 이 함수를 안 고쳐도 되게 하려는 것이다.
def extract_subject_us(text: str) -> str | None:
    # 명시적으로 "common_core_math"를 지정한다(그냥 get_provider()가 아니라) —
    # LOCALE=us를 안 걸어놔도(예: 테스트, 또는 서버 기본값이 여전히 "ko"인 채로
    # 이 함수만 호출되는 경우) 이 함수는 항상 미국 과목 목록을 기준으로 판단해야
    # 하기 때문이다. config.CURRICULUM_PROVIDER의 LOCALE 연동은 편의 기본값일
    # 뿐, "us" 코드 경로의 정확성이 거기 의존하면 안 된다.
    text_lower = text.lower()
    for subject in get_provider("common_core_math").subjects():
        if subject.lower() in text_lower:
            return subject
    return None


DEFAULT_GRADE_US = "8"  # 학년을 끝내 못 알아들었을 때만 쓰는 최후 폴백.

# common_core_math_matcher.grade_groups_for()가 바로 알아듣는 표기("K", "1"~"12")
# 로 정규화한다. 고등학교는 학년이 아니라 도메인 단위로 조직돼 있어("High
# School" 하나로 묶임, common_core_standards/README.md 참고) 9~12학년 중
# 어느 걸 골라도 매칭 결과가 같으므로, "high school"만 단독으로 말하면
# 대표값 "9"를 쓴다.
_GRADE_WORD_MAP_US: dict[str, str] = {
    "kindergarten": "K", "kinder": "K", "k": "K",
    "freshman": "9", "sophomore": "10", "junior": "11", "senior": "12",
}
_GRADE_PATTERN_US = re.compile(
    r"\bgrade\s*(k|[0-9]{1,2})\b"
    r"|\b([0-9]{1,2})\s*(?:st|nd|rd|th)\s*grade\b"
    r"|\b(kindergarten|kinder|freshman|sophomore|junior|senior)\b"
    r"|\bhigh school\b",
    re.IGNORECASE,
)


def _clamp_grade_us(digit: str) -> str | None:
    n = int(digit)
    return str(n) if 0 <= n <= 12 else None


def extract_grade_us(text: str) -> str | None:
    stripped = text.strip()
    if stripped.upper() in ("K", "KG"):
        return "K"

    m = _GRADE_PATTERN_US.search(text)
    if not m:
        return None
    grade_or_k, digit_ordinal, word = m.groups()

    if grade_or_k is not None:
        return "K" if grade_or_k.lower() == "k" else _clamp_grade_us(grade_or_k)
    if digit_ordinal is not None:
        return _clamp_grade_us(digit_ordinal)
    if word:
        return _GRADE_WORD_MAP_US[word.lower()]
    return "9"  # "high school" 단독 언급.


@dataclass
class ConversationState:
    locale: str = "ko"  # "ko"(기본, NCIC) | "us"(Common Core Math, Phase 3)
    phase: Phase = Phase.COLLECTING
    slots: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # [{"role": "user"/"assistant", "content": str}]
    draft: dict | None = None  # lesson_plan.generate_lesson_plan()의 결과
    notion_url: str | None = None
    # 종합 프로젝트: 수정-전파를 위해 page_id를 따로 들고 있어야 한다 (URL만으로는
    # "같은 페이지를 업데이트"할 수 없고, Notion 쓰기 tool은 page_id를 요구한다).
    notion_page_id: str | None = None
    # 학생 활동지(worksheet.py의 결과, Google Docs writer의 결과). 활동지는
    # 계획안과 달리 사용자가 명시적으로 "만들기" 버튼을 눌러야 처음 생성되는
    # opt-in 흐름이라, 생성 전에는 전부 None으로 둔다.
    worksheet: dict | None = None
    worksheet_doc_id: str | None = None
    worksheet_url: str | None = None

    def missing_slots(self) -> list[str]:
        return [s for s in REQUIRED_SLOTS if s not in self.slots]

    def next_question(self) -> str | None:
        missing = self.missing_slots()
        if not missing:
            return None
        questions = SLOT_QUESTIONS_US if self.locale == "us" else SLOT_QUESTIONS
        return questions[missing[0]]

    def _record(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def handle_message(self, message: str) -> str:
        """사용자 메시지 하나를 처리하고, 챗봇이 다음에 보여줄 응답 문자열을 반환한다.

        COLLECTING 단계에서는 규칙 기반으로 슬롯을 채우고 다음 질문을 반환한다.
        READY/DRAFTED/REVISING 단계에서 실제로 수업계획안을 만들거나 고치는 것은
        이 클래스의 책임이 아니다 — 그건 lesson_plan.py가 하고, 여기서는 상태
        전이(무엇을 물어야 하는지, 지금 뭘 해야 하는지)만 관리한다. UI(chat_app.py)
        가 READY/REVISING 상태를 보고 lesson_plan.generate_lesson_plan()을 호출한다.

        2026-09-17: `self.locale`에 따라 슬롯 추출 함수/응답 문구만 영어·한국어로
        갈라진다 — 상태 전이 로직 자체는 언어와 무관해서 하나만 둔다.
        """
        self._record("user", message)
        is_us = self.locale == "us"

        if self.phase == Phase.COLLECTING:
            missing = self.missing_slots()
            if not missing:
                self.phase = Phase.READY
                return self._advance_and_get_reply()

            current_slot = missing[0]
            if current_slot == "subject":
                subject = extract_subject_us(message) if is_us else extract_subject(message)
                if subject is None:
                    reply = (
                        f"Sorry, I couldn't recognize the subject. Currently supported: "
                        f"{', '.join(get_provider('common_core_math').subjects())}."
                        if is_us
                        else "죄송해요, 어떤 과목인지 못 알아들었어요. 국어/수학/영어/사회/과학/도덕/음악/미술/체육 등 중에서 골라주세요."
                    )
                    self._record("assistant", reply)
                    return reply
                self.slots["subject"] = subject
            elif current_slot == "grade":
                grade = extract_grade_us(message) if is_us else extract_grade(message)
                if grade is None:
                    reply = (
                        "Sorry, I couldn't understand the grade level. Please specify it clearly "
                        "(e.g. Kindergarten, Grade 3, 9th grade)."
                        if is_us
                        else "죄송해요, 학년을 못 알아들었어요. 학교급을 포함해서 말씀해주세요 (예: 초등학교 3학년, 중학교 2학년, 고등학교 1학년)."
                    )
                    self._record("assistant", reply)
                    return reply
                self.slots["grade"] = grade
            elif current_slot == "topic":
                topic = message.strip()
                if not topic:
                    reply = (
                        "Could you be a bit more specific about the topic?"
                        if is_us
                        else "주제를 조금 더 구체적으로 말씀해주시겠어요?"
                    )
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
            reply = (
                "Got it — I'll revise it based on your feedback."
                if is_us
                else "알겠습니다. 말씀하신 내용을 반영해서 다시 만들어볼게요."
            )
            self._record("assistant", reply)
            return reply

        reply = (
            "I'm currently processing something else. Please wait a moment."
            if is_us
            else "지금은 다른 처리 중이에요. 잠시만 기다려주세요."
        )
        self._record("assistant", reply)
        return reply

    def _advance_and_get_reply(self) -> str:
        next_q = self.next_question()
        if next_q is not None:
            self._record("assistant", next_q)
            return next_q
        self.phase = Phase.READY
        if self.locale == "us":
            reply = (
                f"I'll put together a Grade {self.slots.get('grade', DEFAULT_GRADE_US)} discussion lesson "
                f"plan on '{self.slots['topic']}' for {self.slots['subject']}. One moment please."
            )
        else:
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
        self.notion_page_id = None
        self.worksheet = None
        self.worksheet_doc_id = None
        self.worksheet_url = None


QUIZ_SLOT_QUESTIONS = {
    "subject": "어떤 과목의 퀴즈를 만들까요? (예: 국어, 수학, 영어, 사회, 과학, 도덕, 음악, 미술, 체육 등)",
    "grade": "몇 학년 대상인가요? (예: 초등학교 3학년, 중학교 2학년, 고등학교 1학년)",
    "topic": "어떤 단원이나 주제를 확인하는 퀴즈로 만들까요? (예: '삼각형의 내각', '광합성')",
}
QUIZ_REQUIRED_SLOTS = ["subject", "grade", "topic"]


@dataclass
class QuizConversationState:
    """Quiz Activity 전용 멀티턴 상태.

    ConversationState(토의·토론)와 상태 전이 구조(COLLECTING -> READY ->
    DRAFTED -> REVISING)는 같아서 extract_subject/extract_grade 같은 슬롯
    추출 헬퍼는 그대로 재사용하지만, 클래스 자체는 따로 둔다 — 산출물이
    퀴즈 문항 하나뿐이라(Notion+Google Docs 두 산출물을 다루는 토의·토론과
    달리 Google Forms 하나에만 반영) 필드 구성이 다르고, lesson_plan.py/
    worksheet.py/quiz.py가 이미 비슷한 패턴을 각자 파일로 중복해서 갖고
    있는 것과 같은 이유로 억지로 공통 베이스 클래스를 만들기보다 이미 실제
    사용 중이고 테스트가 다 통과하는 ConversationState를 건드리지 않는
    쪽을 택했다.
    """

    phase: Phase = Phase.COLLECTING
    slots: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    draft: dict | None = None  # quiz.generate_quiz()의 결과
    form_id: str | None = None
    edit_url: str | None = None
    responder_url: str | None = None

    def missing_slots(self) -> list[str]:
        return [s for s in QUIZ_REQUIRED_SLOTS if s not in self.slots]

    def next_question(self) -> str | None:
        missing = self.missing_slots()
        if not missing:
            return None
        return QUIZ_SLOT_QUESTIONS[missing[0]]

    def _record(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def handle_message(self, message: str) -> str:
        """ConversationState.handle_message()와 동일한 구조 — 자세한 설명은 그쪽 docstring 참고."""
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
                    reply = "죄송해요, 어떤 과목인지 못 알아들었어요. 국어/수학/영어/사회/과학/도덕/음악/미술/체육 등 중에서 골라주세요."
                    self._record("assistant", reply)
                    return reply
                self.slots["subject"] = subject
            elif current_slot == "grade":
                grade = extract_grade(message)
                if grade is None:
                    reply = "죄송해요, 학년을 못 알아들었어요. 학교급을 포함해서 말씀해주세요 (예: 초등학교 3학년, 중학교 2학년, 고등학교 1학년)."
                    self._record("assistant", reply)
                    return reply
                self.slots["grade"] = grade
            elif current_slot == "topic":
                topic = message.strip()
                if not topic:
                    reply = "단원이나 주제를 조금 더 구체적으로 말씀해주시겠어요?"
                    self._record("assistant", reply)
                    return reply
                self.slots["topic"] = topic

            return self._advance_and_get_reply()

        if self.phase == Phase.DRAFTED:
            # 문항을 본 뒤 사용자가 뭔가 말하면 "수정 요청"으로 간주 — 퀴즈는
            # 산출물이 하나뿐이라 ConversationState처럼 "어느 산출물을
            # 겨냥한 건지" 분류할 필요가 없다.
            self.slots["revision_request"] = message.strip()
            self.phase = Phase.REVISING
            reply = "알겠습니다. 말씀하신 내용을 반영해서 문항을 다시 만들어볼게요."
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
            f"{self.slots['subject']} 과목, '{self.slots['topic']}' 단원으로 "
            f"{self.slots.get('grade', DEFAULT_GRADE)} 대상 퀴즈를 만들어볼게요. 잠시만 기다려주세요."
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
        self.form_id = None
        self.edit_url = None
        self.responder_url = None
