"""
Test helpers — fakes aur env isolation.

DO ZARURI CHEEZEIN YAHAN HAIN:

1. `clean_env()` — user ki asli .env ko test se door rakhta hai.
   Warna test tere machine pe pass hoga aur doosre pe fail, kyunki
   uske .env mein alag keys/order hain. Ye sabse common test bug hai.

2. `FakeHTTP` — network ko replace karta hai. Test kabhi asli API
   call nahi karega: paisa nahi lagta, rate limit nahi lagti, aur
   internet ke bina bhi test chalta hai (Pillar #3 — purana laptop,
   slow connection).
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

# Project root ko path mein daalo taaki `python -m unittest` kahin se
# bhi chal jaaye
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test output saaf rakho.
#
# Bahut tests jaan-boojh ke failure trigger karte hain (dead provider,
# rate limit). Unke log.warning Python ke lastResort handler se stderr
# pe chhap jaate hain aur test output padhna mushkil ho jaata hai.
# NullHandler + CRITICAL level se wo chup ho jaate hain.
import logging  # noqa: E402

_saarthi_log = logging.getLogger("saarthi")
_saarthi_log.addHandler(logging.NullHandler())
_saarthi_log.setLevel(logging.CRITICAL)


# Ye env vars test ke result ko badal sakte hain — inko hata dete hain
_RISKY_PREFIXES = ("SAARTHI_", "WHISPER_", "TTS_", "PORCUPINE_", "WAKE_", "VOICE_")
_RISKY_SUFFIXES = ("_API_KEY", "_MODEL", "_TOOLS", "_VISION")
_RISKY_EXACT = ("ADB_PATH",)


@contextlib.contextmanager
def clean_env(**overrides):
    """
    Saare SAARTHI env vars hata ke test chalao.

    Use:
        with clean_env(NVIDIA_API_KEY="fake"):
            settings = Settings.load()
    """
    saved = dict(os.environ)
    try:
        for key in list(os.environ):
            if (
                key.startswith(_RISKY_PREFIXES)
                or key.endswith(_RISKY_SUFFIXES)
                or key in _RISKY_EXACT
            ):
                del os.environ[key]
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextlib.contextmanager
def captured_stdout():
    """stdout pakad lo — UI render test ke liye."""
    real = sys.stdout
    buffer = io.StringIO()
    sys.stdout = buffer
    try:
        yield buffer
    finally:
        sys.stdout = real


# ----------------------------------------------------------------------
#  Fake HTTP — asli network kabhi nahi
# ----------------------------------------------------------------------


class FakeResponse:
    """httpx ka response jaisa."""

    def __init__(self, status_code: int = 200, text: str = "", payload=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    def json(self):
        if self._payload is not None:
            return self._payload
        return {
            "choices": [{"message": {"content": "ok", "tool_calls": []}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


class FakeHTTP:
    """
    httpx.AsyncClient ka replacement.

    Use:
        fake = FakeHTTP(lambda url, payload: FakeResponse(200))
        with fake.patch():
            ...
    """

    def __init__(self, handler):
        """
        Args:
            handler: (url, payload) -> FakeResponse
        """
        self.handler = handler
        self.calls: list = []   # (url, payload) ka record

    @contextlib.contextmanager
    def patch(self):
        import httpx

        original = httpx.AsyncClient
        outer = self

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, json=None, headers=None, **kwargs):
                outer.calls.append((url, json))
                return outer.handler(url, json)

            async def get(self, url, headers=None, **kwargs):
                outer.calls.append((url, None))
                return outer.handler(url, None)

        httpx.AsyncClient = _Client
        try:
            yield outer
        finally:
            httpx.AsyncClient = original

    @property
    def urls(self) -> list:
        return [url for url, _ in self.calls]

    def provider_hits(self) -> list:
        """Kaunse provider ko call gaya — URL se pata karo."""
        names = []
        for url, _ in self.calls:
            if "groq" in url:
                names.append("groq")
            elif "nvidia" in url:
                names.append("nvidia-nim")
            elif "bluesminds" in url:
                names.append("bluesminds")
            elif "openrouter" in url:
                names.append("openrouter")
            elif "googleapis" in url:
                names.append("gemini")
            else:
                names.append(url)
        return names


# ----------------------------------------------------------------------
#  Fake page — browser tests bina Playwright
# ----------------------------------------------------------------------


class FakePage:
    """Playwright page jaisa, bas URL rakhne ke liye."""

    def __init__(self, url: str = "about:blank"):
        self.url = url
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    def set_default_timeout(self, ms):
        pass


class SaarthiTestCase(unittest.TestCase):
    """Common base — env isolation default se on."""

    def assertBlocked(self, assessment, msg=""):
        self.assertEqual(assessment.level.value, "blocked", msg)

    def assertSafe(self, assessment, msg=""):
        self.assertEqual(assessment.level.value, "safe", msg)

    def assertNeedsConfirm(self, assessment, msg=""):
        self.assertEqual(assessment.level.value, "confirm", msg)
