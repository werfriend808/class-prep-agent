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

from .config import ANTHROPIC_API_KEY, HCX_API_KEY, HCX_MODEL, LLM_PROVIDER, SUMMARY_MODEL

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
    if LLM_PROVIDER == "clova":
        client = _get_clova_client()
        response = client.chat.completions.create(
            model=HCX_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    client = get_client()
    message = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
