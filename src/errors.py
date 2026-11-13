"""생성 실패 예외의 공통 구조: 내부 사유와 사용자에게 보여줄 문장을 분리한다 (2026-11-13).

실제 데모에서 Quiz 생성이 실패했을 때, 검수 LLM이 쓴 판단 과정("(4) 문항 4의 정답
'who'에 대한 해설이 없는 것이 아니라, 문항 5는 (2)에 해당합니다: ...")이 에러
메시지로 화면에 그대로 나왔다. 원인은 한 문자열이 두 역할을 하고 있었던 것이다:
  - 재시도 프롬프트에 붙여서 "무엇을 고쳐야 하는지" 모델에게 알려주는 내부 사유
  - st.error()로 사용자에게 보여주는 안내 문장
그래서 둘을 나눈다. `str(e)`/`e.detail`은 지금까지처럼 내부 사유(재시도 프롬프트,
서버 로그, 기존 테스트가 검사하는 값)이고, 화면에는 `e.user_message`만 쓴다.

`kind`는 사용자 문장을 고르는 데 쓴다:
  - "format": 응답 형식/검증 실패 (JSON 깨짐, 정답이 보기에 없음 등)
  - "review": Quiz 검수 LLM이 문항 내용을 문제 삼음
  - "service": LLM 호출 자체가 실패
`retryable=False`면 재시도하지 않는다 — 호출 한도 초과와 서비스 장애(데모 모드)는
다시 불러도 같은 결과라서, 재시도하면 한도 기록만 한 번 더 남는다.
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


class GenerationError(RuntimeError):
    def __init__(
        self,
        detail: str,
        *,
        user_message: str | None = None,
        kind: str = "format",
        retryable: bool = True,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.user_message = user_message or detail
        self.kind = kind
        self.retryable = retryable


# (한국어 목적격 표현, 영어 명사) — 문장 템플릿에 넣는다.
_WHAT = {
    "lesson_plan": ("수업계획안을", "lesson plan"),
    "worksheet": ("학생 활동지를", "student worksheet"),
    "quiz": ("퀴즈 문항을", "quiz"),
}


def final_message(kind: str, what: str, locale: str = "ko") -> str:
    """재시도까지 실패했을 때 화면에 보여줄 문장."""
    ko_obj, en_noun = _WHAT[what]
    if locale == "us":
        if kind == "review":
            return (
                "While checking the questions, some had an answer or premise that wasn't clearly correct. "
                "A second attempt had the same problem, so I stopped. Try a more specific topic "
                "(e.g. 'adding fractions with unlike denominators' instead of 'fractions')."
            )
        if kind == "service":
            return f"Couldn't reach the AI service to create the {en_noun}. Please try again in a moment."
        return (
            f"The generated {en_noun} came back in a broken format, and a second attempt failed too. "
            "Please try again in a moment."
        )
    if kind == "review":
        return (
            "만든 문항을 검토해보니 정답이나 내용이 확실하지 않은 문항이 있었어요. 한 번 더 만들어봤지만 "
            "같은 문제가 있어서 멈췄어요. 주제를 조금 더 구체적으로 적어서 다시 시도해주세요 "
            "(예: '문법' 대신 '관계대명사 who/which')."
        )
    if kind == "service":
        return f"AI 서비스에 연결하지 못해서 {ko_obj} 만들지 못했어요. 잠시 후 다시 시도해주세요."
    return f"AI가 만든 결과의 형식이 맞지 않아 한 번 더 시도했지만 {ko_obj} 만들지 못했어요. 잠시 후 다시 시도해주세요."


def run_with_one_retry(
    attempt: Callable[[GenerationError | None], T],
    error_cls: type[GenerationError],
    what: str,
    locale: str = "ko",
) -> T:
    """attempt(None)을 실행하고, 재시도 가능한 실패면 attempt(첫 실패)로 한 번 더 시도한다.

    재시도까지 실패하면 내부 사유는 그대로 두고 사용자 문장만 `final_message()`로 바꿔서
    올린다. attempt가 첫 실패를 받는 이유: Quiz는 거절 사유를 재시도 프롬프트에 붙인다.
    """
    try:
        return attempt(None)
    except error_cls as first:
        if not first.retryable:
            raise
        try:
            return attempt(first)
        except error_cls as second:
            if not second.retryable:
                raise
            raise error_cls(
                str(second),
                user_message=final_message(second.kind, what, locale),
                kind=second.kind,
                retryable=False,
            ) from second


def unavailable_error(error_cls: type[GenerationError], e: Exception) -> GenerationError:
    """한도 초과/서비스 장애 — 메시지가 이미 사용자용 문장이라 그대로 쓰고 재시도하지 않는다."""
    return error_cls(str(e), kind="service", retryable=False)
