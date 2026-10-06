"""Safe iPhone/iPad integration through an explicit Shortcuts bridge.

Apple does not expose Android-style remote Accessibility control. This adapter
therefore does NOT pretend to tap arbitrary iOS UI. It calls user-created,
explicitly named Shortcuts through a trusted HTTPS/LAN bridge.

Expected bridge contract:
  GET  /health                 -> {"ok": true, "device": "Afzal iPhone"}
  GET  /shortcuts              -> {"shortcuts": ["Morning Briefing", ...]}
  POST /run {"shortcut": ..., "input": ...} -> {"ok": true, "output": ...}
Authorization: Bearer <token>
"""
from __future__ import annotations

try:
    import httpx
    HAS_HTTPX = True
except ImportError:  # core install normally has it; keep imports graceful
    httpx = None  # type: ignore[assignment]
    HAS_HTTPX = False

from .base import ActionResult, Capability, Device


class IOSShortcutsDevice(Device):
    kind = "ios"
    capabilities = {Capability.LAUNCH_APP, Capability.DEVICE_INFO}

    def __init__(self, name: str = "ios", base_url: str = "", token: str = "", timeout: float = 15.0):
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _request(self, method: str, path: str, **kwargs):
        if not HAS_HTTPX:
            raise RuntimeError("iOS bridge ke liye httpx install karo")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            return await client.request(method, f"{self.base_url}{path}", headers=self._headers, **kwargs)

    async def is_available(self) -> bool:
        if not self.base_url or not self.token or not self.base_url.startswith(("https://", "http://")):
            return False
        try:
            response = await self._request("GET", "/health")
            return response.status_code == 200 and bool(response.json().get("ok"))
        except Exception:  # noqa: BLE001
            return False

    async def info(self) -> ActionResult:
        if not await self.is_available():
            return ActionResult.failure("iOS Shortcuts bridge connected nahi hai.")
        response = await self._request("GET", "/health")
        data = response.json()
        return ActionResult.success(
            f"iOS Shortcuts bridge: {data.get('device', self.name)}",
            device=data.get("device", self.name), verified=True,
            verification_message="Authenticated iOS bridge health check passed",
        )

    async def list_apps(self) -> ActionResult:
        """For iOS the explicit Shortcuts allowlist is the available action list."""
        try:
            response = await self._request("GET", "/shortcuts")
            if response.status_code != 200:
                return ActionResult.failure(f"iOS bridge HTTP {response.status_code}")
            shortcuts = response.json().get("shortcuts", [])
            return ActionResult.success(
                "Allowed iOS Shortcuts:\n" + "\n".join(f"- {x}" for x in shortcuts),
                shortcuts=shortcuts,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"iOS shortcuts nahi mile: {exc}")

    async def run_shortcut(self, shortcut: str, input_text: str = "") -> ActionResult:
        if not shortcut.strip():
            return ActionResult.failure("Shortcut name zaroori hai.")
        try:
            response = await self._request(
                "POST", "/run", json={"shortcut": shortcut.strip(), "input": input_text}
            )
            if response.status_code != 200:
                return ActionResult.failure(f"iOS bridge HTTP {response.status_code}")
            data = response.json()
            if not data.get("ok"):
                return ActionResult.failure(str(data.get("error") or "Shortcut fail hua"))
            return ActionResult.success(
                str(data.get("output") or f"iOS Shortcut '{shortcut}' complete"),
                shortcut=shortcut, verified=True,
                verification_message="Authenticated bridge confirmed Shortcut completion",
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"iOS Shortcut nahi chala: {exc}")

    async def launch_app(self, app: str) -> ActionResult:
        # Explicit convention: bridge can expose “Open <App>” shortcuts.
        return await self.run_shortcut(f"Open {app}")
