"""Korean entry point (LOCALE=ko) for a second Streamlit Community Cloud app.

Streamlit Community Cloud allows one app per repo + branch + main file, so the
Korean deployment needs its own main file. This file forces LOCALE=ko before
anything from src/ is imported (config.py reads LOCALE once, at import time),
then runs chat_app.py unchanged. Point the Korean app's "Main file path" here.

LOCALE is set unconditionally rather than with setdefault, so the Korean app
stays Korean even if its secrets were copied from the English app.
"""
import os
import runpy
from pathlib import Path

os.environ["LOCALE"] = "ko"

runpy.run_path(str(Path(__file__).with_name("chat_app.py")), run_name="__main__")
