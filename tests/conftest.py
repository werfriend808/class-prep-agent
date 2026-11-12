"""테스트 간 공유 상태 초기화: usage.py의 한도 카운터가 테스트 순서에 따라 누적되지 않게."""
import pytest

import src.usage as usage


@pytest.fixture(autouse=True)
def _reset_quota_counters():
    usage._session_calls.clear()
    usage._local_day.update(day=None, count=0)
    usage._db_cache.update(day=None, fetched_at=0.0, count=0, local_at_fetch=0)
    yield
