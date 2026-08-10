"""llm.py의 provider 분기(complete()) 단위 테스트.

실제 anthropic/openai 클라이언트 대신 _get_clova_client / get_client를
가짜 함수로 바꿔치기해서(수동 monkeypatch, 저장/복원 방식은 다른 테스트 파일과
동일한 스타일) 네트워크 없이 검증한다. LLM_PROVIDER 값도 같은 방식으로
일시적으로 바꿔서 분기를 테스트한다.
"""
from types import SimpleNamespace

import src.llm as llm


def test_complete_uses_anthropic_by_default():
    original_provider = llm.LLM_PROVIDER
    original_get_client = llm.get_client
    llm.LLM_PROVIDER = "anthropic"

    class _FakeMessages:
        def create(self, **kwargs):
            assert kwargs["messages"][0]["content"] == "안녕"
            return SimpleNamespace(content=[SimpleNamespace(text="클로드 응답")])

    class _FakeClient:
        messages = _FakeMessages()

    llm.get_client = lambda: _FakeClient()
    try:
        result = llm.complete("안녕", max_tokens=100)
    finally:
        llm.LLM_PROVIDER = original_provider
        llm.get_client = original_get_client

    assert result == "클로드 응답"


def test_complete_uses_clova_when_provider_is_clova():
    original_provider = llm.LLM_PROVIDER
    original_get_clova_client = llm._get_clova_client
    llm.LLM_PROVIDER = "clova"

    class _FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"]
            assert kwargs["messages"][0]["content"] == "안녕"
            message = SimpleNamespace(content="클로바 응답")
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClovaClient:
        chat = _FakeChat()

    llm._get_clova_client = lambda: _FakeClovaClient()
    try:
        result = llm.complete("안녕", max_tokens=100)
    finally:
        llm.LLM_PROVIDER = original_provider
        llm._get_clova_client = original_get_clova_client

    assert result == "클로바 응답"


def test_get_clova_client_raises_when_key_missing():
    original_key = llm.HCX_API_KEY
    original_client = llm._clova_client
    llm.HCX_API_KEY = ""
    llm._clova_client = None
    try:
        try:
            llm._get_clova_client()
        except RuntimeError as e:
            assert "HCX_API_KEY" in str(e)
        else:
            raise AssertionError("HCX_API_KEY가 없으면 RuntimeError가 발생해야 함")
    finally:
        llm.HCX_API_KEY = original_key
        llm._clova_client = original_client
