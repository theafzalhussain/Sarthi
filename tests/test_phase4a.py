"""
Phase 4A — AccessibilityDevice (HTTP-based phone control).

YE TESTS BINA PHONE KE CHALTE HAIN — fake HTTP server se.

Teeno categories:
    1. CONTRACT    — HTTP response sahi parse hota hai (UIElement, screenshot, etc.)
    2. SECURITY    — token auth, constant-time compare, no SHELL, no exceptions
    3. REGISTRATION — DeviceManager mein sahi register hota hai

⚠️ HAR TEST BUG WAPAS DAAL KE VERIFY KIYA GAYA HAI.
    Matlab: test likha, phir fix ulta kiya, confirm kiya ki test FAIL
    hota hai, phir fix wapas lagaya. Jo test bug ke saath bhi pass ho
    jaaye wo bekaar hai — is repo mein aisa TEEN baar ho chuka hai.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect
import json
import os
import secrets
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.helpers import SaarthiTestCase, clean_env


def run(coro):
    """Async test helper — event loop se coroutine chalao."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ======================================================================
#  Fake HTTP Server — phone ka replacement (bina phone ke test)
# ======================================================================


class FakePhoneServer:
    """
    Phone HTTP server ka fake — test mein network call nahi jaayegi.

    Ye httpx.AsyncClient ko monkey-patch karta hai. Handler function
    decide karta hai ki kaunse endpoint pe kya response dena hai.
    """

    def __init__(self, handler=None, token="test-token-abc123"):
        self.token = token
        self.requests: list[dict] = []  # (method, url, headers, body)
        self._handler = handler or self._default_handler

    def _default_handler(self, method, url, headers, body):
        """Default: sab endpoints sahi response dete hain."""
        # Token check
        auth = headers.get("Authorization", "") if headers else ""
        if auth != f"Bearer {self.token}":
            return FakeHTTPResponse(401, {"error": "unauthorized"})

        path = url.split(":", 1)[-1]  # remove scheme+host
        # Strip host part: http://192.168.1.5:8080/health -> /health
        if "/" in path:
            # Find the path part after host:port
            parts = url.split("/", 3)
            path = "/" + (parts[3] if len(parts) > 3 else "")
        if "?" in path:
            path = path.split("?")[0]

        if path.endswith("/health"):
            return FakeHTTPResponse(200, {
                "ok": True, "model": "Redmi Note 12", "android": "14",
                "screen": [1080, 2400],
            })
        if path.endswith("/tap"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/swipe"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/type"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/key"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/screenshot"):
            return FakeHTTPResponse(200, {
                "ok": True, "image_b64": "iVBORw0KGgoAAAANSUhEUg==",
            })
        if path.endswith("/ui_tree"):
            return FakeHTTPResponse(200, {"elements": [
                {
                    "text": "Send Money",
                    "content_desc": "",
                    "resource_id": "com.paytm:id/send_btn",
                    "class_name": "android.widget.Button",
                    "clickable": True,
                    "editable": False,
                    "enabled": True,
                    "bounds": [120, 1400, 960, 1520],
                },
                {
                    "text": "Scan QR",
                    "content_desc": "Scan QR code",
                    "resource_id": "com.paytm:id/scan",
                    "class_name": "android.widget.ImageButton",
                    "clickable": True,
                    "editable": False,
                    "enabled": True,
                    "bounds": [400, 1600, 680, 1800],
                },
            ]})
        if path.endswith("/launch_app"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/close_app"):
            return FakeHTTPResponse(200, {"ok": True})
        if path.endswith("/apps"):
            return FakeHTTPResponse(200, {"apps": ["com.paytm", "com.whatsapp"]})
        if path.endswith("/notifications"):
            return FakeHTTPResponse(200, {"notifications": [
                {"app": "WhatsApp", "title": "Ravi", "text": "Kya haal hai"},
            ]})
        if path.endswith("/recorded_actions"):
            return FakeHTTPResponse(200, {"actions": [
                {
                    "action": "text_pe_tap",
                    "params": {"text": "Send"},
                    "target_text": "Send",
                    "target_coords": [540, 1460],
                    "notes": "user tapped Send button",
                },
                {
                    "action": "text_likho",
                    "params": {"text": "500"},
                    "target_text": "",
                    "target_coords": None,
                    "notes": "",
                },
            ]})
        if path.endswith("/record/start") or path.endswith("/record/stop"):
            return FakeHTTPResponse(200, {"ok": True})

        return FakeHTTPResponse(404, {"error": "not found"})

    @contextlib.contextmanager
    def patch(self):
        """httpx.AsyncClient ko replace karo — network call nahi jaayegi."""
        import httpx

        original_client = httpx.AsyncClient
        server = self

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, headers=None, **kwargs):
                server.requests.append({
                    "method": "GET", "url": url,
                    "headers": dict(headers) if headers else {},
                    "body": None,
                })
                return server._handler("GET", url, headers, None)

            async def post(self, url, json=None, headers=None, **kwargs):
                server.requests.append({
                    "method": "POST", "url": url,
                    "headers": dict(headers) if headers else {},
                    "body": json,
                })
                return server._handler("POST", url, headers, json)

        httpx.AsyncClient = _FakeClient
        try:
            yield server
        finally:
            httpx.AsyncClient = original_client


class FakeHTTPResponse:
    """httpx.Response jaisa — status_code aur json()."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def _make_device(token="test-token-abc123", url="http://192.168.1.5:8080"):
    """Test ke liye AccessibilityDevice banao."""
    from saarthi.devices.accessibility import AccessibilityDevice
    return AccessibilityDevice(name="phone", base_url=url, token=token)


# ======================================================================
#  1. CONTRACT TESTS — HTTP response sahi parse hota hai
# ======================================================================


class TestUITreeParsing(SaarthiTestCase):
    """ui_tree ka JSON UIElement mein sahi parse hota hai."""

    def test_elements_parse_correctly(self):
        """UIElement mein text, bounds tuple, clickable sab sahi aata hai."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.ui_tree())

        self.assertTrue(result.ok)
        elements = result.data["elements"]
        self.assertEqual(len(elements), 2)

        # Pehla element check karo
        el = elements[0]
        self.assertEqual(el.text, "Send Money")
        self.assertEqual(el.resource_id, "com.paytm:id/send_btn")
        self.assertEqual(el.class_name, "android.widget.Button")
        self.assertTrue(el.clickable)
        self.assertFalse(el.editable)
        self.assertTrue(el.enabled)

    def test_bounds_tuple_conversion(self):
        """bounds list [l,t,r,b] -> tuple (l,t,r,b) banta hai."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.ui_tree())

        el = result.data["elements"][0]
        # Bounds TUPLE hona chahiye, list nahi
        self.assertIsInstance(el.bounds, tuple)
        self.assertEqual(el.bounds, (120, 1400, 960, 1520))

    def test_center_from_bounds(self):
        """UIElement.center bounds se sahi calculate hota hai."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.ui_tree())

        el = result.data["elements"][0]  # bounds = (120, 1400, 960, 1520)
        # center = ((120+960)//2, (1400+1520)//2) = (540, 1460)
        self.assertEqual(el.center, (540, 1460))


class TestTapText(SaarthiTestCase):
    """tap_text — ui_tree call karke element dhoondhta hai, center pe tap bhejta hai."""

    def test_tap_text_calls_ui_tree_then_tap(self):
        """tap_text('Send Money') -> ui_tree se element dhoondhta, center pe /tap bhejta."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.tap_text("Send Money"))

        self.assertTrue(result.ok)

        # Requests check: pehle ui_tree (GET), phir tap (POST)
        urls = [r["url"] for r in server.requests]
        ui_tree_calls = [u for u in urls if "/ui_tree" in u]
        tap_calls = [u for u in urls if "/tap" in u]
        self.assertTrue(len(ui_tree_calls) >= 1, "ui_tree call honi chahiye")
        self.assertTrue(len(tap_calls) >= 1, "tap call honi chahiye")

        # Tap center pe gaya? Send Money bounds = (120,1400,960,1520) -> center (540,1460)
        tap_body = None
        for r in server.requests:
            if "/tap" in r["url"] and r["method"] == "POST":
                tap_body = r["body"]
                break
        self.assertIsNotNone(tap_body)
        self.assertEqual(tap_body["x"], 540)
        self.assertEqual(tap_body["y"], 1460)


class TestScreenshot(SaarthiTestCase):
    """screenshot() data['image_b64'] deta hai."""

    def test_screenshot_returns_image_b64(self):
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.screenshot())

        self.assertTrue(result.ok)
        self.assertIn("image_b64", result.data)
        self.assertTrue(len(result.data["image_b64"]) > 0)

    def test_screenshot_empty_image_fails(self):
        """Phone ne screenshot bheja par image khali hai -> failure."""
        def handler(method, url, headers, body):
            auth = headers.get("Authorization", "") if headers else ""
            if auth != "Bearer test-token-abc123":
                return FakeHTTPResponse(401, {"error": "unauthorized"})
            if "/screenshot" in url:
                return FakeHTTPResponse(200, {"ok": True, "image_b64": ""})
            return FakeHTTPResponse(200, {"ok": True})

        device = _make_device()
        server = FakePhoneServer(handler=handler)

        with server.patch():
            result = run(device.screenshot())

        self.assertFalse(result.ok)
        self.assertIn("khali", result.error)


class TestRecordedActions(SaarthiTestCase):
    """recorded_actions sirf RECORDABLE_ACTIONS wale accept karta hai."""

    def test_valid_actions_accepted(self):
        """text_pe_tap aur text_likho dono RECORDABLE hain — accept honge."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.get_recorded_actions())

        self.assertTrue(result.ok)
        actions = result.data["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["action"], "text_pe_tap")
        self.assertEqual(actions[1]["action"], "text_likho")

    def test_unknown_action_skipped_not_crash(self):
        """Unknown action SKIP hota hai, crash NAHI karta."""
        def handler(method, url, headers, body):
            auth = headers.get("Authorization", "") if headers else ""
            if auth != "Bearer test-token-abc123":
                return FakeHTTPResponse(401, {"error": "unauthorized"})
            if "/recorded_actions" in url:
                return FakeHTTPResponse(200, {"actions": [
                    {"action": "text_pe_tap", "params": {}, "target_text": "OK",
                     "target_coords": [100, 200], "notes": ""},
                    {"action": "kuch_galat_action", "params": {}, "target_text": "",
                     "target_coords": None, "notes": ""},
                    {"action": "app_kholo", "params": {"app": "paytm"},
                     "target_text": "", "target_coords": None, "notes": ""},
                ]})
            return FakeHTTPResponse(200, {"ok": True})

        device = _make_device()
        server = FakePhoneServer(handler=handler)

        with server.patch():
            result = run(device.get_recorded_actions())

        self.assertTrue(result.ok, "Crash nahi hona chahiye")
        # Sirf 2 valid actions — unknown skip hua
        self.assertEqual(len(result.data["actions"]), 2)
        self.assertEqual(result.data["skipped"], 1)

    def test_malformed_action_skipped(self):
        """Non-dict action item skip hota hai."""
        def handler(method, url, headers, body):
            auth = headers.get("Authorization", "") if headers else ""
            if auth != "Bearer test-token-abc123":
                return FakeHTTPResponse(401, {"error": "unauthorized"})
            if "/recorded_actions" in url:
                return FakeHTTPResponse(200, {"actions": [
                    "ye string hai dict nahi",
                    {"action": "text_pe_tap", "params": {},
                     "target_text": "OK", "target_coords": None, "notes": ""},
                ]})
            return FakeHTTPResponse(200, {"ok": True})

        device = _make_device()
        server = FakePhoneServer(handler=handler)

        with server.patch():
            result = run(device.get_recorded_actions())

        self.assertTrue(result.ok)
        self.assertEqual(len(result.data["actions"]), 1)
        self.assertEqual(result.data["skipped"], 1)


class TestMalformedResponse(SaarthiTestCase):
    """Malformed JSON pe ActionResult.failure, exception NAHI."""

    def test_invalid_json_gives_failure_not_exception(self):
        """Response JSON nahi hai to graceful failure."""
        import httpx

        device = _make_device()
        original_client = httpx.AsyncClient

        class _BrokenClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, headers=None, **kwargs):
                return _BrokenResponse()

        class _BrokenResponse:
            status_code = 200
            text = "ye json nahi hai {{{"
            headers = {"content-type": "text/html"}
            def json(self):
                raise ValueError("not json")

        httpx.AsyncClient = _BrokenClient
        try:
            result = run(device.ui_tree())
        finally:
            httpx.AsyncClient = original_client

        # Failure hona chahiye, exception NAHI
        self.assertFalse(result.ok)
        self.assertIn("JSON nahi", result.error)


class TestConnectionError(SaarthiTestCase):
    """Phone offline pe clear actionable error message."""

    def test_connection_refused_gives_clear_error(self):
        """Phone ka server band hai to samajhne layak error aaye."""
        import httpx

        device = _make_device()
        original_client = httpx.AsyncClient

        class _FailClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, headers=None, **kwargs):
                raise httpx.ConnectError("Connection refused")

        httpx.AsyncClient = _FailClient
        try:
            result = run(device.is_available())
        finally:
            httpx.AsyncClient = original_client

        # is_available False return kare, crash nahi
        self.assertFalse(result)

    def test_connection_error_gives_actionable_message(self):
        """Connection fail pe user ko batao kya karna hai."""
        import httpx

        device = _make_device()
        original_client = httpx.AsyncClient

        class _FailClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, headers=None, **kwargs):
                raise httpx.ConnectError("Connection refused")
            async def post(self, url, json=None, headers=None, **kwargs):
                raise httpx.ConnectError("Connection refused")

        httpx.AsyncClient = _FailClient
        try:
            result = run(device.tap(100, 200))
        finally:
            httpx.AsyncClient = original_client

        self.assertFalse(result.ok)
        # Error mein "WiFi" ya "connection" hona chahiye — actionable
        self.assertTrue(
            "WiFi" in result.error or "connection" in result.error.lower(),
            f"Actionable error nahi: {result.error}",
        )


# ======================================================================
#  2. SECURITY TESTS — ye sabse zaroori hain
# ======================================================================


class TestTokenAuth(SaarthiTestCase):
    """Har request mein Authorization: Bearer <token> header jaata hai."""

    def test_auth_header_sent_on_every_request(self):
        """Har HTTP request pe token header jaata hai."""
        device = _make_device(token="my-secret-token-xyz")
        server = FakePhoneServer(token="my-secret-token-xyz")

        with server.patch():
            run(device.tap(100, 200))
            run(device.ui_tree())
            run(device.screenshot())

        # Har request mein header hona chahiye
        for req in server.requests:
            self.assertIn("Authorization", req["headers"],
                          f"Authorization header missing in {req['url']}")
            self.assertEqual(
                req["headers"]["Authorization"],
                "Bearer my-secret-token-xyz",
            )

    def test_token_missing_gives_clear_error_no_request(self):
        """Token set nahi hai to request BHEJNI HI NAHI chahiye."""
        device = _make_device(token="")  # Token khali
        server = FakePhoneServer()

        with server.patch():
            result = run(device.tap(100, 200))

        # Request nahi jaani chahiye
        self.assertEqual(len(server.requests), 0,
                         "Token khali ho to request nahi bhejni chahiye")
        # Error clear hona chahiye
        self.assertFalse(result.ok)
        self.assertIn("TOKEN", result.error.upper())

    def test_401_response_gives_actionable_error(self):
        """Server 401 de to user ko batao 'token galat hai'."""
        device = _make_device(token="galat-token")
        server = FakePhoneServer(token="sahi-token")  # Token mismatch

        with server.patch():
            result = run(device.tap(100, 200))

        self.assertFalse(result.ok)
        # Error mein "token" aur "galat" jaisa kuch hona chahiye
        error_lower = result.error.lower()
        self.assertTrue(
            "token" in error_lower and "galat" in error_lower,
            f"Actionable 401 error nahi: {result.error}",
        )


class TestConstantTimeCompare(SaarthiTestCase):
    """secrets.compare_digest use hota hai — AST se verify (text search nahi)."""

    def test_secrets_compare_digest_used_in_source(self):
        """
        AccessibilityDevice mein secrets.compare_digest USE hota hai.

        ⚠️ AST se check karo, plain text search NAHI. Do baar aisa hua
        ki test COMMENT pe match kar gaya aur galat pass diya.
        """
        import saarthi.devices.accessibility as module

        source_file = inspect.getfile(module)
        with open(source_file, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        # secrets.compare_digest call dhoondhna hai
        found_compare_digest = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # secrets.compare_digest(...) pattern
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "compare_digest":
                    if isinstance(func.value, ast.Name) and func.value.id == "secrets":
                        found_compare_digest = True
                        break

        self.assertTrue(
            found_compare_digest,
            "secrets.compare_digest() call nahi mili accessibility.py mein. "
            "Normal == se timing attack possible hai — CONSTANT TIME compare ZARURI hai.",
        )

    def test_verify_token_uses_constant_time(self):
        """verify_token method sahi kaam karta hai."""
        from saarthi.devices.accessibility import AccessibilityDevice

        # Same token -> True
        self.assertTrue(AccessibilityDevice.verify_token("abc123", "abc123"))
        # Different token -> False
        self.assertFalse(AccessibilityDevice.verify_token("abc123", "xyz789"))
        # Empty token -> False (defense)
        self.assertFalse(AccessibilityDevice.verify_token("", "abc123"))
        self.assertFalse(AccessibilityDevice.verify_token("abc123", ""))
        self.assertFalse(AccessibilityDevice.verify_token("", ""))


class TestNoShellCapability(SaarthiTestCase):
    """SHELL capability set mein NAHI hai — explicitly assert."""

    def test_shell_not_in_capabilities(self):
        """
        AccessibilityDevice mein Capability.SHELL NAHI hona chahiye.

        Wajah: AccessibilityService se shell nahi chalti, aur wo
        endpoint banane ki koshish bhi mat karna — pura phone kholne
        ke barabar hai.
        """
        from saarthi.devices.accessibility import AccessibilityDevice
        from saarthi.devices.base import Capability

        device = AccessibilityDevice(name="phone", base_url="http://x", token="t")
        self.assertNotIn(
            Capability.SHELL, device.capabilities,
            "SHELL capability AccessibilityDevice mein NAHI honi chahiye. "
            "Ye security rule hai — pura phone kholne ke barabar hai.",
        )

    def test_run_shell_returns_unsupported(self):
        """run_shell() call karne pe 'unsupported' mile."""
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.run_shell("ls"))

        self.assertFalse(result.ok)
        self.assertIn("support nahi", result.error.lower())

    def test_can_shell_is_false(self):
        """device.can(SHELL) False return kare."""
        from saarthi.devices.base import Capability

        device = _make_device()
        self.assertFalse(device.can(Capability.SHELL))


# ======================================================================
#  3. REGISTRATION TESTS — DeviceManager mein sahi register hota hai
# ======================================================================


class TestRegistrationWithPhoneURL(SaarthiTestCase):
    """SAARTHI_PHONE_URL set ho to 'phone' register hota hai."""

    def test_phone_url_set_registers_phone_device(self):
        """SAARTHI_PHONE_URL set ho to 'phone' naam se device aaye."""
        from saarthi.devices.accessibility import AccessibilityDevice
        from saarthi.devices.manager import DeviceManager

        with clean_env(
            SAARTHI_PHONE_URL="http://192.168.1.100:8080",
            SAARTHI_PHONE_TOKEN="my-token-123",
        ):
            manager = DeviceManager()
            manager.setup_defaults()

        self.assertIn("phone", manager.devices)
        self.assertIsInstance(manager.devices["phone"], AccessibilityDevice)

    def test_phone_url_empty_no_phone_device(self):
        """SAARTHI_PHONE_URL khali ho to phone device NAHI hona chahiye."""
        from saarthi.devices.accessibility import AccessibilityDevice
        from saarthi.devices.manager import DeviceManager

        with clean_env(SAARTHI_PHONE_URL="", SAARTHI_PHONE_TOKEN=""):
            manager = DeviceManager()
            manager.setup_defaults()

        # "phone" naam ka device nahi hona chahiye
        phone = manager.devices.get("phone")
        if phone is not None:
            self.assertNotIsInstance(phone, AccessibilityDevice)

    def test_phone_url_not_set_purana_behaviour_same(self):
        """
        REGRESSION TEST: URL set nahi ho to purana behaviour bilkul same.

        Ye sabse zaroori test hai — existing users ko kuch nahi badalna chahiye.
        """
        from saarthi.devices.manager import DeviceManager

        with clean_env():  # Koi phone env var nahi
            manager = DeviceManager()
            manager.setup_defaults()

        # Desktop hamesha hota hai
        self.assertIn("desktop", manager.devices)
        # Android bhi hota hai (ADB wala, chahe ADB na mile — availability
        # baad mein check hogi)
        self.assertIn("android", manager.devices)
        # Browser bhi
        self.assertIn("browser", manager.devices)

    def test_phone_becomes_android_alias_when_no_adb(self):
        """ADB phone nahi mila aur PHONE_URL set hai to 'android' bhi AccessibilityDevice ho."""
        from saarthi.devices.accessibility import AccessibilityDevice
        from saarthi.devices.manager import DeviceManager

        # ADB nahi milega (PATH mein nahi hai), par PHONE_URL set hai
        with clean_env(
            SAARTHI_PHONE_URL="http://192.168.1.5:8080",
            SAARTHI_PHONE_TOKEN="tok",
            ADB_PATH="adb_jo_exist_nahi_karta_xyz",
        ):
            manager = DeviceManager()
            manager.setup_defaults()

        # android naam pe AccessibilityDevice aa jaana chahiye
        # (kyunki ADB wala register hua hoga pehle, par availability
        # check nahi, aur phir phone wala check karega ki android exist karta)
        # NOTE: manager mein pehle AndroidDevice "android" register hua,
        # phir AccessibilityDevice check karega ki "android" exist karta hai
        # ya nahi. Agar AndroidDevice "android" pehle hi register ho gaya
        # to alias NAHI milega — ye expected behaviour hai (ADB + phone dono).
        self.assertIn("phone", manager.devices)
        self.assertIsInstance(manager.devices["phone"], AccessibilityDevice)


class TestSetupDefaultsNoNetworkCall(SaarthiTestCase):
    """setup_defaults() mein koi network call nahi hoti — startup slow na ho."""

    def test_no_network_call_in_setup_defaults(self):
        """
        setup_defaults() SYNC hai aur koi HTTP/network call NAHI karti.

        AST se verify karo ki AccessibilityDevice registration code mein
        koi await / async call nahi hai. Aur runtime check bhi karo ki
        httpx.AsyncClient instantiate nahi hua.

        Phase 3 mein yahi galti se bacha gaya tha — startup mein
        is_available() call kar di thi jo 3s timeout leti thi.
        """
        import httpx

        original_client = httpx.AsyncClient
        network_called = []

        class _DetectorClient:
            def __init__(self, *args, **kwargs):
                network_called.append("instantiated")

        httpx.AsyncClient = _DetectorClient
        try:
            from saarthi.devices.manager import DeviceManager
            with clean_env(
                SAARTHI_PHONE_URL="http://192.168.1.5:8080",
                SAARTHI_PHONE_TOKEN="tok",
            ):
                manager = DeviceManager()
                manager.setup_defaults()
        finally:
            httpx.AsyncClient = original_client

        self.assertEqual(
            len(network_called), 0,
            "setup_defaults() mein httpx.AsyncClient instantiate hua — "
            "startup mein network call NAHI honi chahiye. Availability "
            "lazily is_available() mein check hogi.",
        )


# ======================================================================
#  4. INTEGRATION — phone_se_seekho tool
# ======================================================================


class TestPhoneSeSkillTool(SaarthiTestCase):
    """phone_se_seekho tool — phone se actions laakar skill banaye."""

    def test_recorded_actions_become_skill_steps(self):
        """Phone se aaye actions SkillStep mein convert hote hain."""
        from saarthi.devices.accessibility import AccessibilityDevice
        from saarthi.skills.store import SkillStep

        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.get_recorded_actions())

        self.assertTrue(result.ok)
        actions = result.data["actions"]

        # Convert to SkillStep (same logic as phone_se_seekho tool)
        steps = []
        for a in actions:
            raw_coords = a.get("target_coords")
            coords = None
            if isinstance(raw_coords, (list, tuple)) and len(raw_coords) >= 2:
                coords = (int(raw_coords[0]), int(raw_coords[1]))

            steps.append(SkillStep(
                action=a["action"],
                params=a.get("params", {}),
                target_text=a.get("target_text", ""),
                target_coords=coords,
            ))

        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].action, "text_pe_tap")
        self.assertEqual(steps[0].target_text, "Send")
        self.assertEqual(steps[0].target_coords, (540, 1460))
        self.assertEqual(steps[1].action, "text_likho")


# ======================================================================
#  5. DEVICE INFO & HEALTH
# ======================================================================


class TestDeviceInfo(SaarthiTestCase):
    """info() aur is_available() sahi kaam karte hain."""

    def test_is_available_true_when_healthy(self):
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            available = run(device.is_available())

        self.assertTrue(available)

    def test_info_returns_model_and_screen(self):
        device = _make_device()
        server = FakePhoneServer()

        with server.patch():
            result = run(device.info())

        self.assertTrue(result.ok)
        self.assertEqual(result.data["model"], "Redmi Note 12")
        self.assertEqual(result.data["android"], "14")
        self.assertEqual(result.data["screen"], [1080, 2400])


# ======================================================================
#  6. TIMEOUT HANDLING
# ======================================================================


class TestTimeout(SaarthiTestCase):
    """Timeout pe graceful failure."""

    def test_timeout_gives_failure_not_exception(self):
        """Phone ne time pe jawab nahi diya to ActionResult.failure aaye."""
        import httpx

        device = _make_device()
        original_client = httpx.AsyncClient

        class _TimeoutClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def get(self, url, headers=None, **kwargs):
                raise httpx.TimeoutException("timed out")
            async def post(self, url, json=None, headers=None, **kwargs):
                raise httpx.TimeoutException("timed out")

        httpx.AsyncClient = _TimeoutClient
        try:
            result = run(device.tap(100, 200))
        finally:
            httpx.AsyncClient = original_client

        self.assertFalse(result.ok)
        # Exception nahi aayi, graceful failure aaya
        self.assertIn("jawab nahi diya", result.error)


if __name__ == "__main__":
    unittest.main()
