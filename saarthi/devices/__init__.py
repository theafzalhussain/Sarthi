"""
SAARTHI Devices — "SAB DEVICES KA ACCESS" wala hissa.

Architecture ka sabse important faisla: ek universal interface,
neeche kitne bhi devices.

    Device (abstract)
      |-- AndroidDevice   (ADB se phone control)
      |-- DesktopDevice   (laptop: shell, files, mouse/keyboard)
      |-- BrowserDevice   (aane wala hai — saari websites)
      |-- ... jo tu add karna chahe

Naya device add karna:
    1. Device class extend kar
    2. capabilities declare kar
    3. Jo methods support karta hai wo override kar
    4. DeviceManager mein register kar

Agent ka code badalna hi nahi padta. Yahi scale karne ka tareeka hai.

Use:
    from saarthi.devices import DeviceManager

    manager = DeviceManager()
    manager.setup_defaults()

    phone = manager.get("android")
    await phone.launch_app("paytm")
    await phone.tap_text("Recharge")
"""

from .android import AndroidDevice
from .base import (
    ActionResult,
    Capability,
    Device,
    DeviceError,
    UIElement,
)
from .browser import HAS_PLAYWRIGHT, BrowserDevice
from .desktop import HAS_GUI, DesktopDevice
from .manager import DeviceManager

__all__ = [
    # Abstraction
    "Device",
    "Capability",
    "ActionResult",
    "UIElement",
    "DeviceError",
    # Implementations
    "AndroidDevice",
    "DesktopDevice",
    "BrowserDevice",
    "HAS_GUI",
    "HAS_PLAYWRIGHT",
    # Manager
    "DeviceManager",
]
