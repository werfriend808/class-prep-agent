"""교육과정 CurriculumProvider 레지스트리 + 선택.

2026-09-17 (Phase 1): 지금은 NCIC(한국) 하나뿐이라 `get_provider()`는 사실상
`NCICProvider` 고정 반환이다. Phase 2에서 미국 Common Core Math provider가
추가되면 `_PROVIDERS`에 등록하고 `.env`의 `CURRICULUM_PROVIDER`로 고르게 한다
— 그 전까지는 이 파일을 거치는 모든 호출부가 지금과 똑같이 NCIC 결과를
받는다(동작 변경 없음).
"""
from __future__ import annotations

from ..config import CURRICULUM_PROVIDER
from .base import CurriculumProvider
from .ncic_provider import NCICProvider

_PROVIDERS: dict[str, type[CurriculumProvider]] = {
    "ncic": NCICProvider,
}


def get_provider(name: str | None = None) -> CurriculumProvider:
    """이름으로 CurriculumProvider 인스턴스를 반환한다.

    `name`을 생략하면 `.env`의 `CURRICULUM_PROVIDER`(기본값 "ncic")를 쓴다.
    """
    key = name or CURRICULUM_PROVIDER
    try:
        provider_cls = _PROVIDERS[key]
    except KeyError:
        raise ValueError(
            f"알 수 없는 CURRICULUM_PROVIDER: {key!r} (사용 가능: {', '.join(_PROVIDERS)})"
        ) from None
    return provider_cls()


__all__ = ["CurriculumProvider", "NCICProvider", "get_provider"]
