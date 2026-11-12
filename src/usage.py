"""익명 사용 지표 기록.

공개 데모가 실제로 쓰이는지(세션 수, 계획안/퀴즈 생성 수)와 호출당 비용(토큰 수)을
측정하기 위한 가벼운 이벤트 로그다. 설계 원칙:

1. **개인정보를 받을 수 있는 필드가 아예 없다.** `log_event()`는 이벤트 이름과
   activity를 미리 정해둔 목록(화이트리스트) 안에서만 받고, 자유 텍스트(주제,
   채팅 내용, 이름)를 넘길 인자 자체가 없다. IP/User-Agent도 기록하지 않는다.
2. **세션 ID는 랜덤 UUID다.** Streamlit 세션(=브라우저 탭) 시작 시 새로 만들고
   다른 어떤 정보와도 연결하지 않는다. 그래서 "세션 수"는 "사용자 수"가 아니다
   (같은 사람이 새로고침하면 새 세션) — 지표를 해석할 때 이 차이를 지켜야 한다.
3. **지표 기록이 앱을 망가뜨리면 안 된다.** 저장은 백그라운드 스레드에서 짧은
   타임아웃으로 하고, 실패는 조용히 버린다. Supabase 설정이 없으면 stdout
   로그로만 남긴다(로컬 개발).

저장소는 Supabase(Postgres)의 REST 엔드포인트(PostgREST)로 직접 쓴다 — 테이블
하나에 INSERT만 하면 돼서 supabase 클라이언트 라이브러리까지는 필요 없고,
anthropic SDK가 이미 의존하는 httpx로 충분하다. 테이블 스키마는 docs/deploy.md.
"""
from __future__ import annotations

import threading
import uuid
from typing import Callable

import httpx

from .config import LOCALE, SUPABASE_KEY, SUPABASE_URL

TABLE = "usage_events"

EVENTS = frozenset(
    {
        "session_start",
        "plan_generated",
        "plan_revised",
        "worksheet_generated",
        "worksheet_revised",
        "quiz_generated",
        "quiz_revised",
        "generation_failed",
        "download",
        "llm_call",
        "quota_blocked",
    }
)
ACTIVITIES = frozenset({"lesson_plan", "worksheet", "quiz"})

_local = threading.local()


def new_session_id() -> str:
    return str(uuid.uuid4())


def bind_session(session_id: str) -> None:
    """현재 스레드(=Streamlit 스크립트 실행 스레드)에 세션 ID를 묶는다.

    llm.complete()처럼 Streamlit을 모르는 모듈도 이벤트를 남길 수 있게, 앱이
    매 실행 시작마다 호출한다.
    """
    _local.session_id = session_id


def current_session_id() -> str | None:
    return getattr(_local, "session_id", None)


def _headers() -> dict[str, str]:
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json", "Prefer": "return=minimal"}
    # 예전 형식(JWT) 키는 Authorization 헤더도 필요하다. 새 형식(sb_secret_...)
    # 키는 JWT가 아니라서 apikey 헤더만 보낸다.
    if not SUPABASE_KEY.startswith("sb_"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


def _post_to_supabase(row: dict) -> None:
    try:
        httpx.post(f"{SUPABASE_URL}/rest/v1/{TABLE}", json=row, headers=_headers(), timeout=3.0)
    except Exception:  # noqa: BLE001 — 지표 저장 실패는 앱 동작과 무관하게 버린다
        pass


def _default_sink(row: dict) -> None:
    if SUPABASE_URL and SUPABASE_KEY:
        threading.Thread(target=_post_to_supabase, args=(row,), daemon=True).start()
    else:
        print(f"[usage] {row}")


# 테스트에서 저장 위치를 바꿔 끼울 수 있게 모듈 변수로 둔다.
sink: Callable[[dict], None] = _default_sink


def log_event(
    event: str,
    *,
    activity: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """이벤트 한 건을 기록한다. 화이트리스트 밖의 값은 ValueError (개발 중에 바로 드러나게)."""
    if event not in EVENTS:
        raise ValueError(f"unknown usage event: {event!r}")
    if activity is not None and activity not in ACTIVITIES:
        raise ValueError(f"unknown activity: {activity!r}")
    row = {
        "session_id": current_session_id(),
        "event": event,
        "locale": LOCALE,
        "activity": activity,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    try:
        sink(row)
    except Exception:  # noqa: BLE001
        pass
