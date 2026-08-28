"""
Accessibility Device Adapter — Phone pe HTTP server se baat karo.

YE PHASE 4 KA CORE HAI.

Architecture (samajhna zaroori hai):
    LAPTOP (ye Python code)  ──HTTP──>  PHONE (Kotlin app)
    AccessibilityDevice      POST /tap   HTTP server (localhost:8080)
                             GET /ui_tree     |
                                              v
                                        AccessibilityService
                                          (asli tap karta hai)

Phone = SERVER, Laptop = CLIENT. Ye ADB ka exact mirror hai —
laptop se phone ko command jaati hai. Isliye ye AndroidDevice ka
drop-in replacement hai. Agent, tools, skills — kisi mein ek line
nahi badlegi.

SECURITY (YE SABSE ZARURI HAI):
    1. Shared token auth — har request mein Authorization: Bearer <token>
    2. Token compare CONSTANT-TIME (secrets.compare_digest) — timing attack se bachao
    3. Phone offline / token galat -> clear actionable error, KABHI exception nahi
    4. SHELL capability NAHI hai — AccessibilityService se shell nahi chalti
    5. Password/OTP field ka text phone side pe mask hota hai (ui_tree mein khali aata hai)

Faayde ADB ke mukable:
    - USB cable ki zarurat nahi (WiFi kaafi)
    - adb install nahi karna padta
    - Developer options ON nahi karna padta
    - Sirf Accessibility permission chahiye
    - ui_tree TEZI se milta hai (uiautomator se fast)
    - User ke manual taps BHI record ho sakte hain (ASLI INAAM)
"""

from __future__ import annotations

import logging
import secrets

from .base import ActionResult, Capability, Device, UIElement

log = logging.getLogger("saarthi.devices.accessibility")


class AccessibilityDevice(Device):
    """
    Android phone jo AccessibilityService + HTTP server chala raha hai.

    Ye AndroidDevice jaisa hi kaam karta hai — bas ADB ke jagah HTTP.
    Agent ko farak nahi padta, wahi Device interface hai.

    SHELL capability JAAN-BOOJH KE nahi hai — AccessibilityService se
    shell nahi chalti, aur wo endpoint banane ki koshish bhi nahi karni
    chahiye (pura phone kholne ke barabar hai).
    """

    kind = "android"  # ADB wala bhi "android" hai — jaan-boojh ke same
    capabilities = {
        Capability.TAP,
        Capability.SWIPE,
        Capability.TYPE,
        Capability.KEY,
        Capability.SCREENSHOT,
        Capability.UI_TREE,
        Capability.LAUNCH_APP,
        Capability.CLOSE_APP,
        Capability.LIST_APPS,
        Capability.NOTIFICATIONS,
        Capability.DEVICE_INFO,
    }
    # ⚠️ SHELL capability NAHI — ye important hai. Agent ko command_chalao
    # phone pe offer hi nahi hoga.

    def __init__(
        self,
        name: str = "phone",
        base_url: str = "http://192.168.1.5:8080",
        token: str = "",
    ):
        super().__init__(name)
        self._base_url = base_url.rstrip("/")
        self._token = token

    # ------------------------------------------------------------------
    #  HTTP plumbing — har request yahan se jaati hai
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        timeout: float = 10.0,
    ) -> ActionResult:
        """
        Phone ko HTTP request bhejo.

        KABHI exception nahi throw karega — structured ActionResult dega.
        Token missing ho to request hi nahi jaayegi.

        Security:
        - Har request mein Authorization: Bearer <token> header
        - Token missing -> clear error, request nahi jaayegi
        - 401 -> actionable error (token galat hai)
        - Connection error -> actionable error (phone offline?)
        """
        import httpx

        # Token MUST hai — bina token request bhejna allowed nahi
        if not self._token:
            return ActionResult.failure(
                "SAARTHI_PHONE_TOKEN set nahi hai. App mein dikhne wala "
                "token .env mein daalo. Bina token phone ko command nahi "
                "bhej sakte — ye security rule hai."
            )

        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"{self._base_url}{path}"

        try:
            async with httpx.AsyncClient() as client:
                if method.upper() == "GET":
                    response = await client.get(
                        url, headers=headers, timeout=timeout
                    )
                else:
                    response = await client.post(
                        url, json=json_body, headers=headers, timeout=timeout
                    )
        except httpx.ConnectError:
            return ActionResult.failure(
                "Phone se connection nahi hua. Check kar:\n"
                "  1. Phone app mein server ON hai?\n"
                "  2. Phone aur laptop SAME WiFi pe hain?\n"
                "  3. SAARTHI_PHONE_URL sahi hai? (app mein IP dikhta hai)"
            )
        except httpx.TimeoutException:
            return ActionResult.failure(
                f"Phone ne {timeout}s mein jawab nahi diya. "
                "App hang ho gaya ya network slow hai."
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Phone request fail: {exc}")

        # 401 = token galat hai
        if response.status_code == 401:
            return ActionResult.failure(
                "Token galat hai — phone app mein dikhne wala token copy "
                "karke .env mein SAARTHI_PHONE_TOKEN mein daalo. Dono "
                "EXACT same hone chahiye."
            )

        # Koi aur HTTP error
        if response.status_code != 200:
            return ActionResult.failure(
                f"Phone ne error diya (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )

        # JSON parse karo
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            return ActionResult.failure(
                "Phone ka jawab JSON nahi hai — app mein kuch galat hai. "
                f"Response: {response.text[:200]}"
            )

        # Phone side pe bhi ok/error check hota hai
        if isinstance(data, dict) and data.get("ok") is False:
            error_msg = data.get("error", "phone ne error bataya (detail nahi)")
            return ActionResult.failure(error_msg)

        return ActionResult.success("", **data)

    async def _get(self, path: str, timeout: float = 10.0) -> ActionResult:
        """GET request shorthand."""
        return await self._request("GET", path, timeout=timeout)

    async def _post(
        self, path: str, body: dict | None = None, timeout: float = 10.0
    ) -> ActionResult:
        """POST request shorthand."""
        return await self._request("POST", path, json_body=body, timeout=timeout)

    # ------------------------------------------------------------------
    #  Connection
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Phone ka server ON hai aur token sahi hai?"""
        result = await self._get("/health", timeout=5.0)
        return result.ok

    async def info(self) -> ActionResult:
        """Phone ki jaankari — model, Android version, screen size."""
        result = await self._get("/health", timeout=5.0)
        if not result.ok:
            return result

        data = result.data
        model = data.get("model", "unknown")
        android = data.get("android", "?")
        screen = data.get("screen", [0, 0])

        summary = f"model={model}, android={android}, screen={screen[0]}x{screen[1]}"
        return ActionResult.success(summary, **data)

    async def current_app(self) -> ActionResult:
        """
        Abhi kaunsa app saamne khula hai?

        ⚠️ YE METHOD EK CHUP-CHAAP FAIL SE BANA HAI.

        `AndroidDevice` (ADB) pe `current_app()` hai, par yahan nahi tha.
        Banking screenshot lock (`tools/banking.py`) ise aise call karta
        hai:

            get_current = getattr(dev, "current_app", None)
            if get_current is not None: ...

        Method na hone pe wo chup-chaap `None` maan leta tha, `current`
        khali reh jaata tha, aur `screenshot_allowed("")` ALLOW kar deta
        tha. Matlab: banking lock ON hone ke baad bhi PHONE pe screenshot
        block nahi hota tha — bilkul chup-chaap, koi error nahi.

        Yahi sabse khatarnak kism ki security failure hai: dikhta hai ki
        protection lagi hui hai, par lagi nahi hoti.

        Contract: `GET /health` ke response mein `current_app` field aani
        chahiye (AccessibilityService ko `rootInActiveWindow.packageName`
        se ye pata hota hai — sasta hai).
        """
        result = await self._get("/health", timeout=5.0)
        if not result.ok:
            return result

        package = (result.data.get("current_app") or "").strip()
        if not package:
            # App purana ho aur ye field na bheje — imaandaari se batao,
            # jhoothi success mat do
            return ActionResult.failure(
                "Phone app ne current_app nahi bheja (purana version?). "
                "Banking screenshot lock is device pe kaam nahi karega."
            )

        return ActionResult.success(package, package=package)

    # ------------------------------------------------------------------
    #  Input actions
    # ------------------------------------------------------------------

    async def tap(self, x: int, y: int) -> ActionResult:
        result = await self._post("/tap", {"x": int(x), "y": int(y)})
        if result.ok:
            return ActionResult.success(f"tap kiya ({x},{y})")
        return result

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> ActionResult:
        result = await self._post("/swipe", {
            "x1": int(x1), "y1": int(y1),
            "x2": int(x2), "y2": int(y2),
            "duration_ms": int(duration_ms),
        })
        if result.ok:
            return ActionResult.success(f"swipe kiya ({x1},{y1}) -> ({x2},{y2})")
        return result

    async def type_text(self, text: str) -> ActionResult:
        """
        Text type karo — phone side pe BHI safety check hota hai.

        Laptop pe safety.py check karta hai (tools layer mein), aur phone
        app mein BHI same block hai. Do jagah defense — belt aur suspender.
        """
        if not text:
            return ActionResult.failure("Khali text type nahi kar sakte")

        result = await self._post("/type", {"text": str(text)})
        if result.ok:
            return ActionResult.success(f"type kiya: {text[:60]}")
        return result

    async def press_key(self, key: str) -> ActionResult:
        result = await self._post("/key", {"key": str(key).lower().strip()})
        if result.ok:
            return ActionResult.success(f"{key} press kiya")
        return result

    # ------------------------------------------------------------------
    #  Screen reading
    # ------------------------------------------------------------------

    async def screenshot(self) -> ActionResult:
        """
        Screenshot lo — phone se base64 PNG aata hai.

        Timeout 20s rakha hai kyunki screenshot bada hota hai aur slow
        network pe time lagta hai.
        """
        result = await self._get("/screenshot", timeout=20.0)
        if not result.ok:
            return result

        image_b64 = result.data.get("image_b64", "")
        if not image_b64:
            return ActionResult.failure("Phone ne screenshot bheja par image khali hai")

        return ActionResult.success(
            f"Screenshot liya ({len(image_b64) * 3 // 4 // 1024} KB)",
            image_b64=image_b64,
            image_mime="image/png",
        )

    async def ui_tree(self) -> ActionResult:
        """
        Screen ka structure padho — elements ki list.

        Phone se JSON array aata hai, hum UIElement mein convert karte hain.
        Password/OTP fields ka text phone side pe hi mask ho jaata hai
        (khali string aati hai) — ye security design hai.
        """
        result = await self._get("/ui_tree", timeout=10.0)
        if not result.ok:
            return result

        raw_elements = result.data.get("elements", [])
        elements: list[UIElement] = []

        for item in raw_elements:
            if not isinstance(item, dict):
                continue

            # bounds = [left, top, right, bottom] -> tuple
            raw_bounds = item.get("bounds", [0, 0, 0, 0])
            if isinstance(raw_bounds, (list, tuple)) and len(raw_bounds) >= 4:
                bounds = (
                    int(raw_bounds[0]),
                    int(raw_bounds[1]),
                    int(raw_bounds[2]),
                    int(raw_bounds[3]),
                )
            else:
                bounds = (0, 0, 0, 0)

            elements.append(UIElement(
                text=str(item.get("text", "")),
                content_desc=str(item.get("content_desc", "")),
                resource_id=str(item.get("resource_id", "")),
                class_name=str(item.get("class_name", "")),
                clickable=bool(item.get("clickable", False)),
                editable=bool(item.get("editable", False)),
                enabled=bool(item.get("enabled", True)),
                bounds=bounds,
            ))

        interactive = [el for el in elements if el.clickable or el.editable]

        summary_lines = [f"Screen pe {len(elements)} elements mile"]
        if interactive:
            summary_lines.append("Interactive elements:")
            for el in interactive[:25]:
                summary_lines.append(f"  - {el}")

        return ActionResult.success(
            "\n".join(summary_lines),
            elements=elements,
            interactive=interactive,
        )

    # ------------------------------------------------------------------
    #  App management
    # ------------------------------------------------------------------

    async def launch_app(self, app: str) -> ActionResult:
        """App kholo — Hinglish naam ya package name dono chalega."""
        from ..lang.lexicon import resolve_app

        package = app if "." in app else (resolve_app(app) or app)
        result = await self._post("/launch_app", {"app": package})
        if result.ok:
            return ActionResult.success(f"{app} khol diya", package=package)
        return result

    async def close_app(self, app: str) -> ActionResult:
        """App band karo (best-effort).

        LIMITATION: AccessibilityService se force-stop NAHI hota. Ye sirf
        home button dabata hai — app background mein reh sakti hai. Ye
        Android ki limitation hai, bug nahi. Full force-stop ke liye root
        ya ADB chahiye jo yahan available nahi hai.
        """
        from ..lang.lexicon import resolve_app

        package = app if "." in app else (resolve_app(app) or app)
        result = await self._post("/close_app", {"app": package})
        if result.ok:
            return ActionResult.success(f"{app} band kar diya", package=package)
        return result

    async def list_apps(self) -> ActionResult:
        """Installed apps ki list."""
        result = await self._get("/apps", timeout=15.0)
        if not result.ok:
            return result

        packages = result.data.get("apps", [])
        return ActionResult.success(
            f"{len(packages)} apps installed hain",
            packages=packages,
        )

    # ------------------------------------------------------------------
    #  Notifications
    # ------------------------------------------------------------------

    async def read_notifications(self) -> ActionResult:
        """Notifications padho — NotificationListenerService se aate hain."""
        result = await self._get("/notifications", timeout=10.0)
        if not result.ok:
            return result

        notifications = result.data.get("notifications", [])
        if not notifications:
            return ActionResult.success("Koi notification nahi hai")

        lines = [f"{len(notifications)} notifications:"]
        for notif in notifications[:20]:
            app = notif.get("app", "?")
            title = notif.get("title", "")
            text = notif.get("text", "")
            lines.append(f"  [{app}] {title}: {text}")

        return ActionResult.success("\n".join(lines), notifications=notifications)

    # ------------------------------------------------------------------
    #  Recording — phone se recorded actions laana (Phase 4 ka ASLI INAAM)
    # ------------------------------------------------------------------

    async def start_recording(self) -> ActionResult:
        """Phone pe recording shuru karo — user ke manual taps record honge."""
        return await self._post("/record/start")

    async def stop_recording(self) -> ActionResult:
        """Phone pe recording band karo."""
        return await self._post("/record/stop")

    async def get_recorded_actions(self) -> ActionResult:
        """
        Phone se recorded actions laao.

        Ye SkillStep format mein aate hain. Sirf RECORDABLE_ACTIONS
        wale accept honge — baaki skip ho jaayenge (crash nahi karenge).
        """
        from ..skills.recorder import RECORDABLE_ACTIONS

        result = await self._get("/recorded_actions", timeout=10.0)
        if not result.ok:
            return result

        raw_actions = result.data.get("actions", [])
        valid_actions: list[dict] = []
        skipped = 0

        for action in raw_actions:
            if not isinstance(action, dict):
                skipped += 1
                continue

            action_name = action.get("action", "")
            if action_name not in RECORDABLE_ACTIONS:
                log.warning(
                    "Phone se unknown action skip kiya: %s (RECORDABLE_ACTIONS mein nahi)",
                    action_name,
                )
                skipped += 1
                continue

            valid_actions.append(action)

        output = f"{len(valid_actions)} actions record hue"
        if skipped:
            output += f" ({skipped} skip — unknown/invalid)"

        return ActionResult.success(
            output,
            actions=valid_actions,
            skipped=skipped,
        )

    # ------------------------------------------------------------------
    #  Shell — DELIBERATELY NOT IMPLEMENTED
    # ------------------------------------------------------------------

    async def run_shell(self, command: str) -> ActionResult:
        """
        SHELL SUPPORT NAHI HAI — ye jaan-boojh ke hai.

        AccessibilityService se shell nahi chalti. Aur ye endpoint
        banana bhi MANA hai — wo pura phone kholne ke barabar hai.
        """
        return self._unsupported("shell")

    # ------------------------------------------------------------------
    #  Token validation helper (Python side pe use hota hai)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_token(provided: str, expected: str) -> bool:
        """
        Constant-time token comparison — timing attack se bachao.

        Ye Python side pe use hota hai jab kabhi token validate karna ho.
        secrets.compare_digest ZARURI hai — normal == se timing attack
        possible hai (attacker ek ek character guess kar sakta hai).
        """
        if not provided or not expected:
            return False
        return secrets.compare_digest(provided.encode(), expected.encode())
