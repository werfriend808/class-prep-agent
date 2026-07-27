"""Claude API 클라이언트 공용 헬퍼. summarizer.py / query_router.py가 공유."""
from __future__ import annotations

import anthropic

from .config import ANTHROPIC_API_KEY

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(".env에 ANTHROPIC_API_KEY를 설정해주세요.")
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client
