"""Semantic Windows desktop adapter using Microsoft UI Automation.

Optional dependency: ``uiautomation``. Without it the normal DesktopDevice keeps
working; with it JARVIS can read controls and invoke buttons by accessible name
instead of guessing screen coordinates.
"""
from __future__ import annotations

import asyncio
import platform
from typing import Any

from .base import ActionResult, Capability, UIElement
from .desktop import DesktopDevice

try:
    import uiautomation as auto  # type: ignore
    HAS_UIA = True
except Exception:  # noqa: BLE001
    auto = None  # type: ignore
    HAS_UIA = False


class WindowsDevice(DesktopDevice):
    kind = "desktop"
    capabilities = set(DesktopDevice.capabilities) | {Capability.UI_TREE}

    def __init__(self, name: str = "desktop", max_depth: int = 7, max_elements: int = 500):
        super().__init__(name=name)
        self.max_depth = max(1, min(max_depth, 12))
        self.max_elements = max(50, min(max_elements, 2000))

    async def is_available(self) -> bool:
        return platform.system() == "Windows"

    async def info(self) -> ActionResult:
        base = await super().info()
        mode = "semantic UI Automation ready" if HAS_UIA else "coordinate fallback (install uiautomation)"
        return ActionResult.success(f"{base.output}\nWindows control: {mode}", semantic_uia=HAS_UIA)

    @staticmethod
    def _rect(control: Any) -> tuple[int, int, int, int]:
        try:
            rect = control.BoundingRectangle
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:  # noqa: BLE001
            return (0, 0, 0, 0)

    @staticmethod
    def _bool(control: Any, attr: str, default: bool = False) -> bool:
        try:
            return bool(getattr(control, attr))
        except Exception:  # noqa: BLE001
            return default

    def _scan_sync(self) -> tuple[list[UIElement], dict[int, Any]]:
        if not HAS_UIA:
            return [], {}
        root = auto.GetRootControl()
        elements: list[UIElement] = []
        controls: dict[int, Any] = {}
        stack: list[tuple[Any, int]] = [(root, 0)]
        editable_types = {"EditControl", "DocumentControl", "ComboBoxControl"}
        clickable_types = {
            "ButtonControl", "HyperlinkControl", "MenuItemControl", "TabItemControl",
            "ListItemControl", "TreeItemControl", "CheckBoxControl", "RadioButtonControl",
        }
        while stack and len(elements) < self.max_elements:
            control, depth = stack.pop()
            try:
                name = str(getattr(control, "Name", "") or "").strip()
                kind = str(getattr(control, "ControlTypeName", "") or "")
                automation_id = str(getattr(control, "AutomationId", "") or "")
                bounds = self._rect(control)
                if name or automation_id:
                    element = UIElement(
                        text=name, content_desc=name, resource_id=automation_id,
                        class_name=kind, clickable=kind in clickable_types,
                        editable=kind in editable_types,
                        enabled=self._bool(control, "IsEnabled", True), bounds=bounds,
                    )
                    elements.append(element)
                    controls[id(element)] = control
                if depth < self.max_depth:
                    children = list(control.GetChildren() or [])
                    stack.extend((child, depth + 1) for child in reversed(children))
            except Exception:  # noqa: BLE001 — one broken app control must not abort scan
                continue
        return elements, controls

    async def ui_tree(self) -> ActionResult:
        if not HAS_UIA:
            return ActionResult.failure(
                "Windows semantic control ke liye 'pip install uiautomation' chahiye."
            )
        elements, _ = await asyncio.to_thread(self._scan_sync)
        visible = [str(el) for el in elements[:150]]
        return ActionResult.success(
            f"Windows screen pe {len(elements)} accessible controls mile:\n" + "\n".join(visible),
            elements=elements,
            verified=True,
            verification_message="Microsoft UI Automation tree read hua",
        )

    def _find_control_sync(self, query: str) -> tuple[UIElement, Any] | None:
        elements, controls = self._scan_sync()
        q = query.casefold().strip()
        exact = [el for el in elements if el.label.casefold().strip() == q]
        partial = [el for el in elements if el.matches(query)]
        candidates = exact or partial
        if not candidates:
            return None
        enabled = [el for el in candidates if el.enabled]
        clickable = [el for el in enabled if el.clickable]
        chosen = (clickable or enabled or candidates)[0]
        return chosen, controls[id(chosen)]

    async def tap_text(self, text: str) -> ActionResult:
        if not HAS_UIA:
            return await super().tap_text(text)

        def invoke() -> tuple[UIElement, str] | None:
            found = self._find_control_sync(text)
            if found is None:
                return None
            element, control = found
            try:
                control.GetInvokePattern().Invoke()
                return element, "InvokePattern"
            except Exception:  # noqa: BLE001
                try:
                    control.Click(simulateMove=False)
                    return element, "UIA Click"
                except Exception:
                    return None

        invoked = await asyncio.to_thread(invoke)
        if invoked is None:
            return ActionResult.failure(f"Windows UI mein enabled '{text}' control nahi mila/click nahi hua.")
        element, method = invoked
        return ActionResult.success(
            f"Windows control '{element.label}' semantic {method} se activate hua.",
            target=element.label, method=method, verified=True,
            verification_message="Microsoft UI Automation ne control action accept kiya",
        )

    async def fill_field(self, field: str, value: str) -> ActionResult:
        if not HAS_UIA:
            return ActionResult.failure("Semantic field fill ke liye uiautomation install karo.")

        def fill() -> tuple[UIElement, str] | None:
            found = self._find_control_sync(field)
            if found is None:
                return None
            element, control = found
            try:
                control.GetValuePattern().SetValue(value)
                return element, "ValuePattern"
            except Exception:  # noqa: BLE001
                try:
                    control.Click(simulateMove=False)
                    control.SendKeys(value, waitTime=0.01)
                    return element, "focus+keys"
                except Exception:
                    return None

        result = await asyncio.to_thread(fill)
        if result is None:
            return ActionResult.failure(f"Windows field '{field}' fill nahi hua.")
        element, method = result
        return ActionResult.success(
            f"'{element.label}' field semantic {method} se fill hua.",
            target=element.label, method=method, verified=True,
            verification_message="UI Automation field operation completed",
        )
