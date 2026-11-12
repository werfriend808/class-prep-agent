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
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import httpx

from .config import DAILY_LLM_CALL_LIMIT, LOCALE, SESSION_LLM_CALL_LIMIT, SUPABASE_KEY, SUPABASE_URL

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
        "feedback_click",
    }
)
ACTIVITIES = frozenset({"lesson_plan", "worksheet", "quiz"})

_local = threading.local()


def new_session_id() -> str:
    return str(uuid.uuid4())


def bind_session(session_id: str, internal: bool = False) -> None:
    """현재 스레드(=Streamlit 스크립트 실행 스레드)에 세션 ID를 묶는다.

    llm.complete()처럼 Streamlit을 모르는 모듈도 이벤트를 남길 수 있게, 앱이
    매 실행 시작마다 호출한다.
    """
    _local.session_id = session_id
    _local.internal = internal


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
        # 개발자 본인 테스트(?internal=1로 접속)는 표시만 해두고 집계에서 뺀다.
        # 이력서/README에 쓰는 숫자가 내 테스트로 부풀려지지 않게 하기 위함.
        "internal": getattr(_local, "internal", False),
    }
    try:
        sink(row)
    except Exception:  # noqa: BLE001
        pass


# ============================================================
# 비용 상한 (LLM 호출 수 기준)
# ============================================================
#
# 두 겹이다:
#   - 세션 한도: 한 탭에서 폭주하는 경우(버그로 인한 재시도 루프 포함)를 막는다.
#     메모리에만 있으므로 새로고침하면 초기화된다 — 그래서 이것만으로는 부족하다.
#   - 전역 일일 한도: 모든 방문자 합계. Supabase의 오늘자 llm_call 이벤트 수로
#     센다(서버가 재시작돼도 유지됨). DB 조회는 60초마다만 하고 그 사이엔 이
#     프로세스의 증가분을 더한다. DB를 못 읽으면 프로세스 내 카운터로라도 막는다.
# 최종 안전장치는 코드 밖에 있다: Anthropic Console의 월 지출 한도(docs/deploy.md).


class QuotaExceededError(RuntimeError):
    """한도 초과. llm.complete()에서 올라가고, 기능 모듈들이 기존 에러 처리로 화면에 보여준다."""


_quota_lock = threading.Lock()
_session_calls: dict[str, int] = {}
_local_day = {"day": None, "count": 0}
_db_cache = {"day": None, "fetched_at": 0.0, "count": 0, "local_at_fetch": 0}
_DB_REFRESH_SECONDS = 60


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _db_count_today(day: str) -> int | None:
    """Supabase에서 오늘(UTC) llm_call 이벤트 수를 센다. 실패하면 None."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            params={"select": "id", "event": "eq.llm_call", "created_at": f"gte.{day}T00:00:00Z"},
            headers={**_headers(), "Prefer": "count=exact", "Range": "0-0"},
            timeout=2.0,
        )
        content_range = response.headers.get("content-range", "")  # 예: "0-0/123", "*/0"
        return int(content_range.rsplit("/", 1)[1])
    except Exception:  # noqa: BLE001
        return None


def _global_count_today(day: str) -> int:
    local = _local_day["count"] if _local_day["day"] == day else 0
    cache = _db_cache
    if cache["day"] != day or time.monotonic() - cache["fetched_at"] > _DB_REFRESH_SECONDS:
        db_count = _db_count_today(day)
        if db_count is not None:
            cache.update(day=day, fetched_at=time.monotonic(), count=db_count, local_at_fetch=local)
    if cache["day"] == day:
        return max(local, cache["count"] + (local - cache["local_at_fetch"]))
    return local


def _quota_message(kind: str) -> str:
    if LOCALE == "us":
        if kind == "daily":
            return "This demo has reached today's usage limit (shared by all visitors). Please try again tomorrow."
        return "You've reached this demo's per-session limit. Please come back later."
    if kind == "daily":
        return "오늘 데모 전체 사용 한도에 도달했어요(모든 방문자 합계). 내일 다시 시도해주세요."
    return "이 세션의 데모 사용 한도에 도달했어요. 잠시 후 다시 이용해주세요."


def check_quota() -> None:
    """LLM 호출 1건을 허용할지 판단하고, 허용하면 카운트를 올린다. 초과면 QuotaExceededError."""
    day = _today()
    session_id = current_session_id() or "-"
    with _quota_lock:
        if _local_day["day"] != day:
            _local_day.update(day=day, count=0)
        if SESSION_LLM_CALL_LIMIT and _session_calls.get(session_id, 0) >= SESSION_LLM_CALL_LIMIT:
            kind = "session"
        elif DAILY_LLM_CALL_LIMIT and _global_count_today(day) >= DAILY_LLM_CALL_LIMIT:
            kind = "daily"
        else:
            _session_calls[session_id] = _session_calls.get(session_id, 0) + 1
            _local_day["count"] += 1
            return
    log_event("quota_blocked")
    raise QuotaExceededError(_quota_message(kind))
