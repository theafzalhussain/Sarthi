"""
SAARTHI — Ek Hinglish-first universal AI agent.

Sarathi (सारथी) = charioteer. Jo rath chalata hai, raasta jaanta hai.
Tera agent bhi wahi karega — tere devices ka rath chalayega.

Architecture:
    brain/    -> LLM providers (9 providers, streaming, auto-fallback)
    lang/     -> Hinglish samajhne ki layer  (PILLAR #1)
    devices/  -> Universal device adapters   (SAB DEVICES ka access)
    tools/    -> Agent ke haath — parallel execution, kaam karne wale functions
    memory/   -> Yaad rakhne wala hissa
    skills/   -> "Dikha Do Mode" — seekhe hue kaam  (KILLER FEATURE)

v2.0 FEATURES:
    - Streaming responses (real-time token output)
    - Parallel tool execution (independent tools ek saath)
    - 9 LLM providers with automatic fallback
    - Chain-of-thought reasoning
    - Advanced multi-task handling
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
