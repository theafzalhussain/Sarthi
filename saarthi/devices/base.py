"""
Universal Device Adapter — SAARTHI ka "SAB DEVICES" wala hissa.

Ye sabse important architectural decision hai.

Idea: Agent ko farak nahi padna chahiye ki wo Android chala raha hai
ya laptop ya browser. Sabka ek jaisa interface hai:

    device.tap(x, y)
    device.type_text("hello")
    device.screenshot()
    device.launch_app("paytm")

Naya device add karna hai (iPad, TV, smartwatch, Raspberry Pi)?
Bas ek nayi class likh jo Device ko extend kare. Agent ka code
ek line bhi nahi badlega.

Isi tarah ek din tere paas 10 devices ka control ho sakta hai.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Capability(str, Enum):
    """
    Ek device kya kar sakta hai.

    Har device sab kuch nahi kar sakta — laptop pe "tap" nahi hota,
    phone pe "shell" limited hota hai. Isliye capabilities declare
    karte hain, aur agent sirf wahi tools dikhata hai jo chal sakte hain.
    """

    TAP = "tap"                    # Screen pe tap/click
    SWIPE = "swipe"                # Swipe / drag
    TYPE = "type"                  # Text likhna
    KEY = "key"                    # Hardware/special keys (back, home, enter)
    SCREENSHOT = "screenshot"      # Screen ki photo
    UI_TREE = "ui_tree"            # Screen ka structure padhna (text se element dhoondhna)
    LAUNCH_APP = "launch_app"      # App kholna
    LIST_APPS = "list_apps"        # Installed apps ki list
    CLOSE_APP = "close_app"        # App band karna
    SHELL = "shell"                # Shell command chalana
    FILES = "files"                # File read/write
    NOTIFICATIONS = "notifications"  # Notifications padhna
    CLIPBOARD = "clipboard"        # Copy/paste
    DEVICE_INFO = "device_info"    # Battery, screen size etc.


@dataclass
class ActionResult:
    """
    Kisi bhi device action ka result.

    Kabhi exception throw nahi karta — agent ko structured result
    milta hai taaki wo samajh ke agla step decide kar sake.
    """

    ok: bool
    output: str = ""
    error: str = ""

    # Extra data (screenshot base64, UI tree, app list etc.)
    data: dict = field(default_factory=dict)

    @classmethod
    def success(cls, output: str = "", **data) -> "ActionResult":
        return cls(ok=True, output=output, data=data)

    @classmethod
    def failure(cls, error: str, **data) -> "ActionResult":
        return cls(ok=False, error=error, data=data)

    def __str__(self) -> str:
        if self.ok:
            return self.output or "ho gaya"
        return f"fail: {self.error}"


@dataclass
class UIElement:
    """
    Screen pe ek element.

    Ye SAARTHI ki reliability ka raaz hai: blind coordinates pe tap
    karna galat hai (screen size badalta hai, UI badalta hai).
    Text se element dhoondh ke tap karna sahi tareeka hai.

    Yahi cheez baad mein "self-healing" enable karegi — UI badla to
    text se dobara dhoondh lenge.
    """

    text: str = ""
    content_desc: str = ""       # Accessibility label
    resource_id: str = ""        # Developer ka diya hua id
    class_name: str = ""         # Button / TextView / EditText etc.
    clickable: bool = False
    editable: bool = False
    enabled: bool = True

    # Bounds: (left, top, right, bottom)
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def center(self) -> tuple[int, int]:
        """Tap karne ke liye beech ka point."""
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    @property
    def label(self) -> str:
        """Element ka best available naam."""
        return self.text or self.content_desc or self.resource_id or self.class_name

    def matches(self, query: str) -> bool:
        """Ye element user ke describe kiye hue se match karta hai?"""
        q = query.lower().strip()
        haystacks = [
            self.text.lower(),
            self.content_desc.lower(),
            self.resource_id.lower(),
        ]
        return any(q in h for h in haystacks if h)

    def __str__(self) -> str:
        tags = []
        if self.clickable:
            tags.append("clickable")
        if self.editable:
            tags.append("editable")
        if not self.enabled:
            tags.append("disabled")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        x, y = self.center
        return f'"{self.label}" at ({x},{y}){tag_str}'


class DeviceError(Exception):
    """Device layer ki problem."""


class Device(ABC):
    """
    Kisi bhi device ka common interface.

    Naya device support karna hai? Isko extend kar, capabilities
    declare kar, aur relevant methods implement kar.
    """

    # Subclass isko override karega
    kind: str = "unknown"
    capabilities: set[Capability] = set()

    def __init__(self, name: str | None = None):
        self.name = name or self.kind

    # ------------------------------------------------------------------
    #  Connection
    # ------------------------------------------------------------------

    @abstractmethod
    async def is_available(self) -> bool:
        """Ye device abhi connected/usable hai?"""
        raise NotImplementedError

    @abstractmethod
    async def info(self) -> ActionResult:
        """Device ke baare mein basic jaankari."""
        raise NotImplementedError

    def can(self, capability: Capability) -> bool:
        """Ye device ye kaam kar sakta hai?"""
        return capability in self.capabilities

    # ------------------------------------------------------------------
    #  Default implementations — "nahi kar sakta" bolte hain.
    #  Subclass jo support karta hai, wahi override karega.
    # ------------------------------------------------------------------

    def _unsupported(self, action: str) -> ActionResult:
        return ActionResult.failure(
            f"'{self.name}' device pe '{action}' support nahi hai"
        )

    async def tap(self, x: int, y: int) -> ActionResult:
        return self._unsupported("tap")

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> ActionResult:
        return self._unsupported("swipe")

    async def type_text(self, text: str) -> ActionResult:
        return self._unsupported("type")

    async def press_key(self, key: str) -> ActionResult:
        return self._unsupported("key")

    async def screenshot(self) -> ActionResult:
        """data['image_b64'] mein PNG milega."""
        return self._unsupported("screenshot")

    async def ui_tree(self) -> ActionResult:
        """data['elements'] mein list[UIElement] milega."""
        return self._unsupported("ui_tree")

    async def launch_app(self, app: str) -> ActionResult:
        return self._unsupported("launch_app")

    async def close_app(self, app: str) -> ActionResult:
        return self._unsupported("close_app")

    async def list_apps(self) -> ActionResult:
        return self._unsupported("list_apps")

    async def run_shell(self, command: str) -> ActionResult:
        return self._unsupported("shell")

    async def read_notifications(self) -> ActionResult:
        return self._unsupported("notifications")

    # ------------------------------------------------------------------
    #  Composed helpers — ye sab devices pe kaam karte hain
    #  agar unke basic capabilities available hain.
    # ------------------------------------------------------------------

    async def find_element(self, query: str) -> UIElement | None:
        """
        Text se screen pe element dhoondo.

        Blind coordinates se behtar hai — UI badle to bhi kaam karta hai.
        """
        if not self.can(Capability.UI_TREE):
            return None

        result = await self.ui_tree()
        if not result.ok:
            return None

        elements: list[UIElement] = result.data.get("elements", [])

        # Exact text match pehle
        for el in elements:
            if el.text.lower().strip() == query.lower().strip():
                return el

        # Phir partial match — clickable ko priority
        partial = [el for el in elements if el.matches(query)]
        if not partial:
            return None

        clickable = [el for el in partial if el.clickable]
        return clickable[0] if clickable else partial[0]

    async def tap_text(self, text: str) -> ActionResult:
        """
        Screen pe likhe text pe tap karo.

        Ye SAARTHI ka preferred tareeka hai — coordinates se zyada
        reliable, kyunki text UI update ke baad bhi mil jaata hai.
        """
        element = await self.find_element(text)
        if element is None:
            return ActionResult.failure(
                f"Screen pe '{text}' nahi mila. Screenshot lekar dekh le "
                f"ki screen pe kya hai."
            )
        x, y = element.center
        result = await self.tap(x, y)
        if result.ok:
            return ActionResult.success(f"'{element.label}' pe tap kiya ({x},{y})")
        return result

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} kind={self.kind!r}>"
