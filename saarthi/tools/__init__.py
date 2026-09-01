"""
SAARTHI Tools — agent ke haath.

Tool add karna sabse aasaan cheez hai is project mein:

    from saarthi.tools import Tool, ToolContext
    from saarthi.devices import ActionResult

    class MeraTool(Tool):
        name = "mera_kaam"
        description = "Ye kaam karta hai"
        parameters = {"type": "object", "properties": {}}

        async def run(self, ctx: ToolContext) -> ActionResult:
            return ActionResult.success("ho gaya")

    registry.register(MeraTool())

Jitne tools add karega, utna capable agent banega.
"""

from .base import Tool, ToolContext, simple_tool
from .auth_tools import auth_tools
from .creative_tools import creative_tools
from .device_tools import device_tools
from .document_tools import document_tools
from .file_tools import file_tools
from .memory_tools import memory_tools
from .registry import ToolRegistry
from .safety import (
    RiskAssessment,
    RiskLevel,
    check_payment_safety,
    check_shell_safety,
    check_text_safety,
    format_confirmation,
    is_affirmative,
)
from .skill_tools import skill_tools
from .system_tools import system_tools
from .web_tools import web_tools


def default_registry() -> ToolRegistry:
    """
    Saare built-in tools ke saath registry banao.

    Yahi agent ko diya jaata hai.
    """
    registry = ToolRegistry()
    registry.register_all(device_tools())   # phone/laptop control
    registry.register_all(web_tools())      # internet
    registry.register_all(system_tools())   # time, calculator
    registry.register_all(file_tools())     # file likhna/padhna
    registry.register_all(document_tools())  # PDF / Excel / PPT / Word
    registry.register_all(memory_tools())   # yaaddasht
    registry.register_all(skill_tools())    # DIKHA DO MODE
    registry.register_all(creative_tools()) # image + video generation
    registry.register_all(auth_tools())     # website login + credentials
    return registry


__all__ = [
    # Core
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "simple_tool",
    "default_registry",
    # Tool groups
    "creative_tools",
    "device_tools",
    "document_tools",
    "file_tools",
    "web_tools",
    "system_tools",
    "memory_tools",
    "skill_tools",
    "auth_tools",
    # Safety
    "RiskLevel",
    "RiskAssessment",
    "check_text_safety",
    "check_shell_safety",
    "check_payment_safety",
    "format_confirmation",
    "is_affirmative",
]
