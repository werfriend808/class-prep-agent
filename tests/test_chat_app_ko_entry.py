"""chat_app_ko.py가 새 프로세스에서 한국어(NCIC) 설정으로 앱을 띄우는지 확인한다.

config.py는 import 시점에 LOCALE을 한 번 읽으므로, 이미 다른 테스트가 src.config를
import한 이 pytest 프로세스 안에서는 검증할 수 없다. 그래서 별도 파이썬 프로세스로
진입 파일을 실행한 뒤 설정값과 화면 제목을 확인한다. 영어 앱 secrets를 그대로
복사한 경우(LOCALE=us)도 한국어가 되어야 한다.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r"""
import sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=30).run()
assert not at.exception, at.exception
import src.config as config
print("LOCALE=" + config.LOCALE)
print("PROVIDER=" + config.CURRICULUM_PROVIDER)
print("TITLE=" + at.title[0].value)
"""


def test_korean_entry_point_forces_korean_even_with_us_secrets():
    env = {**os.environ, "LOCALE": "us", "DEMO_MODE": "1"}
    env.pop("NOTION_API_KEY", None)
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(ROOT / "chat_app_ko.py")],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert "LOCALE=ko" in out.stdout
    assert "PROVIDER=ncic" in out.stdout
    assert "AI 수업 활동 에이전트" in out.stdout
