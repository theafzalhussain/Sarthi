"""
Device Manager — saare devices ek jagah.

Ye rakhta hai ki kaunse devices connected hain, aur agent ko
sahi device pe kaam bhejta hai.

Yahi "ek agent, sab devices" wala sapna pura karta hai:
    - Tu bola "phone pe whatsapp khol" -> android device pe jaayega
    - Tu bola "laptop pe file dhoondh" -> desktop pe jaayega
    - Tu kuch nahi bola -> default device use hoga
"""

from __future__ import annotations

import logging

from ..config import Settings, settings as default_settings
from ..lang.lexicon import detect_target_device
from .android import AndroidDevice
from .base import ActionResult, Capability, Device
from .desktop import DesktopDevice

log = logging.getLogger("saarthi.devices")


class DeviceManager:
    """Saare devices ka manager."""

    def __init__(self, config: Settings | None = None):
        self.settings = config or default_settings
        self.devices: dict[str, Device] = {}
        self._availability_cache: dict[str, bool] = {}

    # ------------------------------------------------------------------
    #  Registration
    # ------------------------------------------------------------------

    def register(self, device: Device) -> None:
        """Naya device add karo."""
        self.devices[device.name] = device
        log.debug("Device registered: %s (%s)", device.name, device.kind)

    def setup_defaults(self) -> None:
        """
        Standard devices register karo.

        Desktop hamesha available hai. Android tab jab ADB connected ho —
        par register hum abhi karte hain, availability check baad mein.
        """
        self.register(DesktopDevice(name="desktop"))
        self.register(
            AndroidDevice(name="android", adb_path=self.settings.adb_path)
        )

    # ------------------------------------------------------------------
    #  Lookup
    # ------------------------------------------------------------------

    def get(self, name: str | None = None) -> Device | None:
        """
        Device dhoondo naam se.

        Naam nahi diya to default device.
        """
        if name:
            key = name.strip().lower()
            if key in self.devices:
                return self.devices[key]
            # kind se bhi dhoondo ("android" -> pehla android device)
            for device in self.devices.values():
                if device.kind == key:
                    return device
            return None

        return self.devices.get(self.settings.default_device) or next(
            iter(self.devices.values()), None
        )

    def resolve_from_text(self, text: str) -> Device | None:
        """
        User ke Hinglish command se device pata karo.

        "mere phone pe instagram khol"  -> android
        "laptop pe file dhoondh"        -> desktop

        Ye lang layer ke saath integrate hai — PILLAR #1 ka fayda.
        """
        kind = detect_target_device(text)
        if kind:
            device = self.get(kind)
            if device:
                return device
        return self.get()

    def with_capability(self, capability: Capability) -> list[Device]:
        """Kaunse devices ye kaam kar sakte hain."""
        return [d for d in self.devices.values() if d.can(capability)]

    # ------------------------------------------------------------------
    #  Availability
    # ------------------------------------------------------------------

    async def check_availability(self, use_cache: bool = True) -> dict[str, bool]:
        """
        Kaunse devices abhi sach mein connected hain.

        ADB check slow hota hai, isliye cache karte hain.
        """
        if use_cache and self._availability_cache:
            return self._availability_cache

        status: dict[str, bool] = {}
        for name, device in self.devices.items():
            try:
                status[name] = await device.is_available()
            except Exception as exc:  # noqa: BLE001
                log.debug("%s availability check fail: %s", name, exc)
                status[name] = False

        self._availability_cache = status
        return status

    def invalidate_cache(self) -> None:
        """Phone plug/unplug hua ho to cache clear karo."""
        self._availability_cache = {}

    async def available_devices(self) -> list[Device]:
        """Sirf connected devices."""
        status = await self.check_availability()
        return [d for name, d in self.devices.items() if status.get(name)]

    # ------------------------------------------------------------------
    #  Summary for the LLM
    # ------------------------------------------------------------------

    async def describe(self) -> str:
        """
        System prompt ke liye device summary.

        LLM ko pata hona chahiye kaunse devices available hain aur
        wo kya kar sakte hain — warna wo galat tool chunega.
        """
        status = await self.check_availability()
        lines: list[str] = []

        for name, device in self.devices.items():
            connected = status.get(name, False)
            mark = "connected" if connected else "NOT connected"

            caps = sorted(c.value for c in device.capabilities)
            cap_str = ", ".join(caps) if caps else "kuch nahi"

            lines.append(f"- {name} ({device.kind}): {mark}")
            lines.append(f"    kar sakta hai: {cap_str}")

            if name == "android" and not connected:
                lines.append(
                    "    (ADB connect kar: USB laga + USB Debugging ON, "
                    "phir 'adb devices' check kar)"
                )

        return "\n".join(lines)

    async def info_all(self) -> dict[str, ActionResult]:
        """Sab devices ki detailed info."""
        results: dict[str, ActionResult] = {}
        for name, device in self.devices.items():
            try:
                results[name] = await device.info()
            except Exception as exc:  # noqa: BLE001
                results[name] = ActionResult.failure(str(exc))
        return results

    def __repr__(self) -> str:
        return f"<DeviceManager devices={list(self.devices)}>"
