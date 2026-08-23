"""
SAARTHI Language Layer — PILLAR #1.

Ye wo hissa hai jo SAARTHI ko baaki agents se alag karta hai.

Global agents Hinglish pe struggle karte hain kyunki wo English-first
bane hain. Ye layer code-switched Hinglish ko structured hints mein
badal deti hai, jo LLM ko diye jaate hain — isse accuracy badhti hai.

Use:
    from saarthi.lang import parse, build_system_prompt

    cmd = parse("bhai paytm khol ke 2000 ka bill bhar de")
    print(cmd.intent)   # 'pay'
    print(cmd.amount)   # 2000.0
    print(cmd.risky)    # True
"""

from .lexicon import (
    INDIAN_APPS,
    RISKY_KEYWORDS,
    VERB_INTENTS,
    detect_intent,
    detect_target_device,
    find_app_mentions,
    is_risky,
    resolve_app,
)
from .normalize import (
    ParsedCommand,
    extract_amount,
    has_devanagari,
    parse,
    parse_hindi_number,
    strip_fillers,
    transliterate,
)
from .prompts import (
    build_confirmation_prompt,
    build_system_prompt,
    build_user_message,
)

__all__ = [
    # Parsing
    "parse",
    "ParsedCommand",
    # Lexicon lookups
    "resolve_app",
    "find_app_mentions",
    "detect_intent",
    "detect_target_device",
    "is_risky",
    "INDIAN_APPS",
    "VERB_INTENTS",
    "RISKY_KEYWORDS",
    # Text utilities
    "transliterate",
    "has_devanagari",
    "strip_fillers",
    "parse_hindi_number",
    "extract_amount",
    # Prompts
    "build_system_prompt",
    "build_user_message",
    "build_confirmation_prompt",
]
