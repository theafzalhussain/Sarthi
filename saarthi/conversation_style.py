"""Deterministic conversation-style adaptation for human-friendly replies.

This does not guess identity or emotion as fact. It derives a per-turn delivery
hint from the user's words and combines it with explicit saved preferences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .lang.normalize import detect_language


@dataclass(frozen=True)
class ConversationStyle:
    language: str
    tone: str
    length: str
    urgency: bool = False
    frustrated: bool = False

    def directive(self) -> str:
        language_rule = {
            "english": "Reply in natural English.",
            "hindi": "Reply in natural Hindi (Devanagari unless the user uses Roman Hindi).",
            "hinglish": "Reply in natural friendly Hinglish, matching the user's Roman/Devanagari script.",
        }.get(self.language, "Match the user's language naturally.")
        tone_rule = {
            "casual": "Be warm and conversational; 'bhai' is okay only if the user uses it.",
            "formal": "Be polite and professional; do not use slang.",
            "neutral": "Be friendly, clear, and natural without forced slang.",
        }[self.tone]
        length_rule = {
            "short": "Keep the response concise; give the result first.",
            "detailed": "Give useful detail with clear steps, without repetition.",
            "adaptive": "Use only as much detail as the task needs.",
        }[self.length]
        extras = []
        if self.urgency:
            extras.append("The user sounds urgent: act first, avoid unnecessary preamble.")
        if self.frustrated:
            extras.append("The user may be frustrated: acknowledge briefly, do not argue, and focus on fixing the issue.")
        return " ".join([language_rule, tone_rule, length_rule, *extras])


_CASUAL = re.compile(r"\b(bhai|bro|yaar|dost|buddy|pls|please yaar|kar do|kar de)\b", re.I)
_FORMAL = re.compile(r"\b(please|kindly|could you|would you|kripya|कृपया|aap|आप)\b", re.I)
_SHORT = re.compile(r"\b(short|brief|concise|seedha|bas answer|one line|jaldi)\b", re.I)
_DETAILED = re.compile(r"\b(detail|explain|step by step|poora samjha|deep|thorough)\b", re.I)
_URGENT = re.compile(r"\b(urgent|asap|abhi|immediately|jaldi|right now|तुरंत|अभी)\b", re.I)
_FRUSTRATED = re.compile(r"\b(again|baar baar|kaam nahi|not working|bekaar|galat|wrong|frustrat|परेशान)\b", re.I)


def infer_style(text: str, language_setting: str = "auto", preferred_length: str = "") -> ConversationStyle:
    detected = detect_language(text)
    language = detected if language_setting == "auto" else language_setting
    if language not in {"english", "hindi", "hinglish"}:
        language = "hinglish" if detected == "hinglish" else "english"

    casual = bool(_CASUAL.search(text))
    formal = bool(_FORMAL.search(text))
    tone = "casual" if casual else "formal" if formal else "neutral"

    preference = preferred_length.strip().lower()
    if preference in {"short", "concise", "brief"}:
        length = "short"
    elif preference in {"detailed", "detail", "long"}:
        length = "detailed"
    elif _SHORT.search(text):
        length = "short"
    elif _DETAILED.search(text):
        length = "detailed"
    else:
        length = "adaptive"

    return ConversationStyle(
        language=language,
        tone=tone,
        length=length,
        urgency=bool(_URGENT.search(text)),
        frustrated=bool(_FRUSTRATED.search(text)),
    )


def preferred_reply_length(personal_store) -> str:
    """Read only an explicit stored user preference; never infer permanently."""
    if personal_store is None:
        return ""
    for key in ("reply_length", "response_length", "reply_style"):
        item = personal_store.get("preference", "user", key)
        if item:
            value = item.value.lower()
            if any(word in value for word in ("short", "brief", "concise")):
                return "short"
            if any(word in value for word in ("detail", "long", "thorough")):
                return "detailed"
    return ""
