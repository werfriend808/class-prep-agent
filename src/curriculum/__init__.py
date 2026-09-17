"""교육과정 CurriculumProvider 레지스트리 + 선택.

2026-09-17 (Phase 1): 처음엔 NCIC(한국) 하나뿐이라 `get_provider()`가 사실상
`NCICProvider` 고정 반환이었다.

2026-09-17 (Phase 2): 미국 Common Core Math provider(`CommonCoreMathProvider`)를
추가해 `_PROVIDERS`에 등록했다. 기본값(`.env`에 `CURRICULUM_PROVIDER`가 없을
때)은 여전히 "ncic"라 기존 호출부는 동작이 안 바뀐다 — `.env`에
`CURRICULUM_PROVIDER=common_core_math`를 설정해야 새 provider가 쓰인다.
"""
from __future__ import annotations

from ..config import CURRICULUM_PROVIDER
from .base import CurriculumProvider
from .common_core_math_provider import CommonCoreMathProvider
from .ncic_provider import NCICProvider

_PROVIDERS: dict[str, type[CurriculumProvider]] = {
    "ncic": NCICProvider,
    "common_core_math": CommonCoreMathProvider,
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


__all__ = ["CurriculumProvider", "NCICProvider", "CommonCoreMathProvider", "get_provider"]
