"""
SAARTHI — Ek Hinglish-first universal AI agent.

Sarathi (सारथी) = charioteer. Jo rath chalata hai, raasta jaanta hai.
Tera agent bhi wahi karega — tere devices ka rath chalayega.

Architecture:
    brain/    -> LLM providers (Groq, Gemini, OpenRouter) — sochne wala hissa
    lang/     -> Hinglish samajhne ki layer  (PILLAR #1)
    devices/  -> Universal device adapters   (SAB DEVICES ka access)
    tools/    -> Agent ke haath — kaam karne wale functions
    memory/   -> Yaad rakhne wala hissa
    skills/   -> "Dikha Do Mode" — seekhe hue kaam  (KILLER FEATURE)
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
