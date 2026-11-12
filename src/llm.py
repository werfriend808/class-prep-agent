"""LLM 클라이언트 공용 헬퍼.

`complete()`가 프로젝트 전체(실전 1의 summarizer.py/query_router.py + 실전 2의
lesson_plan.py)가 공통으로 쓰는 provider-무관 인터페이스다. `.env`의
`LLM_PROVIDER`가 "clova"면 네이버 클로바 스튜디오(HyperCLOVA X)의 OpenAI 호환
엔드포인트(https://clovastudio.stream.ntruss.com/v1/openai/)로, 그 외(기본값
"anthropic")에는 Claude API로 보낸다. 클로바가 OpenAI 파이썬 SDK와 호환되는
REST API를 제공해서, 커스텀 HTTP 클라이언트를 새로 짤 필요 없이 `openai`
패키지 하나로 붙일 수 있었다 (openai 패키지는 clova 경로를 쓸 때만 필요하도록
함수 안에서 지연 import한다 — 기본 Claude 경로만 쓰는 사람은 설치 안 해도 됨).

`get_client()`는 Claude 전용 저수준 클라이언트로, `complete()`가 내부적으로
쓴다. 과거엔 summarizer.py/query_router.py가 이걸 직접 썼지만, 지금은 모두
`complete()`를 통해 provider 설정을 따르도록 통일했다.
"""
from __future__ import annotations

import anthropic

from . import usage
from .config import ANTHROPIC_API_KEY, CLAUDE_THINKING, DEMO_MODE, HCX_API_KEY, HCX_MODEL, LLM_PROVIDER, LOCALE, SUMMARY_MODEL

_anthropic_client: anthropic.Anthropic | None = None
_clova_client = None  # openai.OpenAI, 지연 import


def get_client() -> anthropic.Anthropic:
    """Claude 클라이언트 (complete()가 Claude provider일 때 내부적으로 씀)."""
    global _anthropic_client
    if _anthropic_client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(".env에 ANTHROPIC_API_KEY를 설정해주세요.")
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_clova_client():
    global _clova_client
    if _clova_client is None:
        if not HCX_API_KEY:
            raise RuntimeError(".env에 HCX_API_KEY를 설정해주세요.")
        from openai import OpenAI  # 지연 import: clova 경로를 쓸 때만 필요

        _clova_client = OpenAI(
            api_key=HCX_API_KEY,
            base_url="https://clovastudio.stream.ntruss.com/v1/openai",
        )
    return _clova_client


def complete(prompt: str, max_tokens: int = 1000) -> str:
    """LLM_PROVIDER 설정에 맞는 provider로 프롬프트를 보내고 텍스트 응답을 반환한다.

    lesson_plan.py가 이 함수만 쓰고 provider를 신경 쓰지 않도록 하기 위한 어댑터.
    """
    usage.check_quota()  # 공개 데모 비용 상한 — 초과면 QuotaExceededError (usage.py)
    try:
        return _complete_raw(prompt, max_tokens)
    except Exception as e:  # noqa: BLE001
        if not DEMO_MODE:
            raise  # 로컬 개발에선 원본 에러를 그대로 보여주는 게 디버깅에 낫다
        # 공개 데모: 원본 에러(request_id, 결제 안내 등)는 서버 로그에만 남기고
        # 사용자에겐 일반 안내만 보여준다. 크레딧 부족 같은 운영 문제가 방문자
        # 화면에 그대로 노출되던 걸 실제로 확인하고(2026-11-12) 바꿨다.
        print(f"[llm] provider error: {type(e).__name__}: {e}")
        raise LLMServiceError(_unavailable_message()) from e


class LLMServiceError(RuntimeError):
    """데모 모드에서 provider 에러를 사용자용 문구로 감싼 예외."""


def _unavailable_message() -> str:
    if LOCALE == "us":
        return "The AI service is temporarily unavailable. Please try again in a few minutes."
    return "AI 서비스를 일시적으로 사용할 수 없어요. 잠시 후 다시 시도해주세요."


def _complete_raw(prompt: str, max_tokens: int) -> str:
    if LLM_PROVIDER == "clova":
        client = _get_clova_client()
        response = client.chat.completions.create(
            model=HCX_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        if getattr(response.choices[0], "finish_reason", None) == "length":
            print(f"[llm] response truncated at max_tokens={max_tokens} (model={HCX_MODEL})")
        u = getattr(response, "usage", None)
        _record_call(HCX_MODEL, getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None))
        return response.choices[0].message.content

    client = get_client()
    extra = {"extra_body": {"thinking": {"type": CLAUDE_THINKING}}} if CLAUDE_THINKING else {}
    message = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )
    u = getattr(message, "usage", None)
    _record_call(SUMMARY_MODEL, getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
    if getattr(message, "stop_reason", None) == "max_tokens":
        # 짧게 끊겨도 되는 호출(질의 분류 20토큰, 요약 300토큰)도 있어서 에러로
        # 만들지는 않고, JSON 파싱 실패의 원인을 바로 알 수 있게 로그만 남긴다.
        print(f"[llm] response truncated at max_tokens={max_tokens} (model={SUMMARY_MODEL})")
    text = _text_from_message(message)
    if not text:
        # 본문이 비면 JSON 파서가 "형식이 깨졌다"는 엉뚱한 에러를 내서 원인을
        # 숨긴다. 출력 한도를 thinking이 다 쓴 경우가 대표적이라 stop_reason을 남긴다.
        raise RuntimeError(f"model returned no text (stop_reason={getattr(message, 'stop_reason', None)})")
    return text


def _record_call(model: str, input_tokens: int | None, output_tokens: int | None) -> None:
    """LLM 호출 1건의 토큰 수를 익명 지표로 남긴다 (실측 호출당 비용 계산용).

    모든 LLM 호출이 complete()를 지나가므로, 기능별 코드(lesson_plan/quiz/
    worksheet)를 건드리지 않고 여기 한 곳에서 비용을 측정할 수 있다.
    """
    usage.log_event("llm_call", model=model, input_tokens=input_tokens, output_tokens=output_tokens)


def _text_from_message(message) -> str:
    """Claude 응답의 text 블록만 이어 붙인다.

    예전엔 `message.content[0].text`를 바로 썼는데, 최신 모델은 응답 앞에
    thinking 블록이 올 수 있어서 첫 블록이 text라는 보장이 없다. 모델을
    secrets로 바꿀 수 있게 하면서 이 가정을 없앴다.
    """
    parts = [
        block.text
        for block in message.content
        if getattr(block, "type", "text") == "text" and getattr(block, "text", None)
    ]
    return "".join(parts)
