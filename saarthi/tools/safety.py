"""
Safety layer — SAARTHI ka brake pedal.

Ye file bahut important hai. Ek AI agent jiske paas device ka pura
access hai, bina brake ke khatarnak hai. Ek galat LLM decision se
paise ja sakte hain ya data delete ho sakta hai.

Do level ki safety:
  1. HARD BLOCK  — ye kaam kabhi nahi honge (chahe user bole)
  2. CONFIRM     — user se puchenge, phir karenge

Design principle: FAIL SAFE.
Doubt ho to ruk jao, mat karo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    """Kitna khatarnak."""

    SAFE = "safe"          # Bina puche kar sakte hain
    CONFIRM = "confirm"    # User se puchna hai
    BLOCKED = "blocked"    # Kabhi nahi karenge


# ======================================================================
#  HARD BLOCKS — ye kabhi nahi honge
# ======================================================================

# Password/OTP/PIN type karna — kabhi nahi.
# Wajah: agent galti kare to account compromise ho jaayega.
# User khud daalega, ye rule negotiable nahi hai.
BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(otp|o\.t\.p)\b",
        "OTP main type nahi karunga — tu khud daal. Ye security rule hai.",
    ),
    (
        r"\b(cvv|cvc)\b",
        "CVV main kabhi type nahi karunga. Tu khud daal.",
    ),
    (
        r"\b(upi\s*pin|atm\s*pin|card\s*pin|mpin)\b",
        "PIN main type nahi karunga. Ye tu khud daalega.",
    ),
    (
        r"\bpassword\s*(hai|is|:)\s*\S+",
        "Password main store/type nahi karta. Tu khud daal.",
    ),
]


# Ye shell commands kabhi nahi chalenge
BLOCKED_SHELL: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/(?:\s|$|\*)", "Pura system delete karne wala command hai"),
    (r"\bmkfs(\.\w+)?\b", "Disk format karne wala command hai"),
    (r"dd\s+if=/dev/(zero|random|urandom)\s+of=/dev/", "Disk wipe karne wala hai"),
    (r":\(\)\{.*\|.*&.*\};:", "Fork bomb hai — system hang ho jaayega"),
    (r"\bchmod\s+-R\s+000\s+/", "System permissions tod dega"),
    (r">\s*/dev/[sh]d[a-z]", "Direct disk pe likh raha hai"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "System band karne wala command hai"),
    (r"curl.*\|\s*(bash|sh)\b", "Internet se code download karke chala raha hai"),
    (r"wget.*\|\s*(bash|sh)\b", "Internet se code download karke chala raha hai"),
]


# ======================================================================
#  Risk assessment
# ======================================================================


@dataclass
class RiskAssessment:
    """Ek action ka safety verdict."""

    level: RiskLevel
    reason: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.level == RiskLevel.BLOCKED

    @property
    def needs_confirmation(self) -> bool:
        return self.level == RiskLevel.CONFIRM


def check_text_safety(text: object) -> RiskAssessment:
    """
    Jo text type hone wala hai, wo safe hai?

    Ye type_text tool ke andar chalta hai — password/OTP rok deta hai.

    Note: `object` accept karta hai (sirf str nahi) — kyunki skill
    placeholders se number aa sakta hai. Safety check kabhi type ki
    wajah se crash nahi hona chahiye.
    """
    text = "" if text is None else str(text)
    lowered = text.lower()

    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            return RiskAssessment(RiskLevel.BLOCKED, reason)

    # 6 digit number jo OTP ho sakta hai
    if re.fullmatch(r"\s*\d{6}\s*", text):
        return RiskAssessment(
            RiskLevel.CONFIRM,
            "Ye 6-digit number OTP lag raha hai. Confirm kar ki ye OTP nahi hai.",
        )

    return RiskAssessment(RiskLevel.SAFE)


def check_shell_safety(command: str) -> RiskAssessment:
    """Shell command safe hai?"""
    normalized = " ".join(command.split())

    for pattern, reason in BLOCKED_SHELL:
        if re.search(pattern, normalized, re.IGNORECASE):
            return RiskAssessment(RiskLevel.BLOCKED, reason)

    # Sudo — confirm karo
    if re.match(r"^\s*sudo\b", normalized):
        return RiskAssessment(
            RiskLevel.CONFIRM, "sudo se chal raha hai — admin permission chahiye"
        )

    # Delete commands — confirm karo
    if re.search(r"\b(rm|rmdir|del|unlink)\b", normalized, re.IGNORECASE):
        return RiskAssessment(RiskLevel.CONFIRM, "Kuch delete ho raha hai")

    # Git ke destructive commands
    if re.search(r"git\s+(push\s+--force|reset\s+--hard|clean\s+-[fd]+)", normalized):
        return RiskAssessment(
            RiskLevel.CONFIRM, "Git ka destructive command hai — kaam ja sakta hai"
        )

    return RiskAssessment(RiskLevel.SAFE)


def check_payment_safety(amount: float | None = None) -> RiskAssessment:
    """
    Payment se related action.

    SAARTHI ka rule: agent payment screen tak le jaa sakta hai,
    par FINAL confirm button user hi dabayega.

    Wajah (ye important hai): banking/UPI apps automation detect karke
    block kar dete hain, aur paise ka galat transfer wapas nahi aata.
    """
    detail = f" (₹{amount:.0f})" if amount else ""
    return RiskAssessment(
        RiskLevel.CONFIRM,
        f"Paise ka maamla hai{detail}. Main screen tak le jaaunga, "
        f"final button tu dabayega.",
    )


# ======================================================================
#  Confirmation formatting
# ======================================================================


def format_confirmation(action: str, details: dict | None = None) -> str:
    """
    User ko dikhane wala confirmation message.

    Saaf saaf batao kya hone wala hai — user ko blind haan nahi bolna
    chahiye.
    """
    lines = ["", "=" * 52, "  RUK JA — confirmation chahiye", "=" * 52]
    lines.append(f"  Kaam: {action}")

    if details:
        lines.append("  Details:")
        for key, value in details.items():
            display = str(value)
            if len(display) > 100:
                display = display[:100] + "..."
            lines.append(f"    {key} = {display}")

    lines.append("=" * 52)
    lines.append("  Karu? (haan / nahi)")
    lines.append("")
    return "\n".join(lines)


def is_affirmative(answer: str) -> bool:
    """
    User ne haan bola?

    Hinglish mein haan bolne ke bahut tareeke hain — sab handle karo.
    Default NAHI hai (fail safe) — samajh na aaye to mana samjho.
    """
    cleaned = answer.strip().lower().strip(".!। ")

    yes_words = {
        "haan", "han", "haa", "ha", "hn", "yes", "y", "yeah", "yep",
        "ok", "okay", "theek", "thik", "theek hai", "thik hai",
        "kar", "kar de", "kar do", "karo", "chalo", "chal",
        "bilkul", "sahi", "confirm", "approve", "go", "yup", "yaa",
    }

    if cleaned in yes_words:
        return True

    # "haan bhai kar de" jaise jawab
    tokens = set(cleaned.split())
    if tokens & {"haan", "han", "yes", "kar", "karo", "confirm", "bilkul"}:
        # Par "nahi" bhi hai to mana samjho: "haan nahi karna"
        if tokens & {"nahi", "na", "no", "mat", "ruk", "cancel"}:
            return False
        return True

    return False
