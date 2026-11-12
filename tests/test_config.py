"""config.py: NOTION_API_KEY 없이도 import되고, 그때 DEMO_MODE가 자동으로 켜지는지 확인."""
import importlib
import os

import src.config as config


def _reload_with(env: dict[str, str | None]):
    saved = {k: os.environ.get(k) for k in env}
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return importlib.reload(config)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _restore():
    importlib.reload(config)


def test_import_without_notion_key_enables_demo_mode():
    try:
        cfg = _reload_with({"NOTION_API_KEY": "", "DEMO_MODE": None})
        assert cfg.DEMO_MODE is True
    finally:
        _restore()


def test_notion_key_present_means_not_demo_by_default():
    try:
        cfg = _reload_with({"NOTION_API_KEY": "secret_dummy", "DEMO_MODE": None})
        assert cfg.DEMO_MODE is False
    finally:
        _restore()


def test_demo_mode_can_be_forced_even_with_notion_key():
    try:
        cfg = _reload_with({"NOTION_API_KEY": "secret_dummy", "DEMO_MODE": "1"})
        assert cfg.DEMO_MODE is True
    finally:
        _restore()
