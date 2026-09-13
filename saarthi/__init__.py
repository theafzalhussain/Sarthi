"""
SAARTHI — Ek Hinglish-first universal AI agent.

Sarathi (सारथी) = charioteer. Jo rath chalata hai, raasta jaanta hai.
Tera agent bhi wahi karega — tere devices ka rath chalayega.

Architecture:
    brain/    -> LLM providers (streaming, auto-fallback)
    lang/     -> Hinglish samajhne ki layer
    devices/  -> Universal device adapters
    tools/    -> Agent ke haath — parallel execution
    memory/   -> Yaad rakhne wala hissa
    skills/   -> "Dikha Do Mode" — seekhe hue kaam
"""

from . import line_input

__version__ = "2.0.0"
__all__ = ["__version__", "line_input"]
