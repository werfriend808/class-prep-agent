"""usage.py: 화이트리스트 밖 값 거부, 개인정보 필드 없음, 실패해도 예외 안 남."""
from types import SimpleNamespace

import pytest

import src.llm as llm
import src.usage as usage


@pytest.fixture
def captured():
    rows = []
    original = usage.sink
    usage.sink = rows.append
    usage.bind_session("test-session")
    try:
        yield rows
    finally:
        usage.sink = original


def test_log_event_row_has_only_anonymous_fields(captured):
    usage.log_event("plan_generated", activity="lesson_plan")
    assert captured == [
        {
            "session_id": "test-session",
            "event": "plan_generated",
            "locale": usage.LOCALE,
            "activity": "lesson_plan",
            "model": None,
            "input_tokens": None,
            "output_tokens": None,
            "internal": False,
        }
    ]


def test_internal_flag_is_recorded(captured):
    usage.bind_session("dev-session", internal=True)
    usage.log_event("session_start")
    assert captured[-1]["internal"] is True


def test_unknown_event_or_activity_rejected(captured):
    with pytest.raises(ValueError):
        usage.log_event("typed_topic: fractions")
    with pytest.raises(ValueError):
        usage.log_event("download", activity="anything else")
    assert captured == []


def test_sink_failure_is_swallowed():
    original = usage.sink

    def broken(_row):
        raise RuntimeError("supabase down")

    usage.sink = broken
    try:
        usage.log_event("session_start")  # 예외가 밖으로 나오면 안 됨
    finally:
        usage.sink = original


def test_complete_records_token_usage(captured):
    original_provider, original_get_client = llm.LLM_PROVIDER, llm.get_client
    llm.LLM_PROVIDER = "anthropic"

    class _FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                usage=SimpleNamespace(input_tokens=123, output_tokens=45),
            )

    llm.get_client = lambda: SimpleNamespace(messages=_FakeMessages())
    try:
        assert llm.complete("x", max_tokens=10) == "ok"
    finally:
        llm.LLM_PROVIDER, llm.get_client = original_provider, original_get_client

    assert captured[-1]["event"] == "llm_call"
    assert (captured[-1]["input_tokens"], captured[-1]["output_tokens"]) == (123, 45)
