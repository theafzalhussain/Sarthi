"""
Sensitive data redaction — screen ka data LLM tak jaane se PEHLE saaf karo.

⚠️ YE MODULE EK ASLI SECURITY GAP SE BANA HAI.

PROBLEM (jo scan mein mila):

    Agent ka kaam karne ka tareeka hi ye hai:
        screen_padho  ->  screen ka saara text  ->  LLM ko bhejo

    LLM cloud pe hai (NVIDIA / Groq / Gemini). Matlab jab user bola
    "paytm mein balance check karo", to balance, transaction history,
    aur screen pe dikhta card number — SAB third-party server pe
    chala jaata tha.

    Aur `read_notifications()` `dumpsys notification --noredact` chalata
    tha. `--noredact` ka matlab hai "Android, sensitive content chhupao
    MAT". Android by default OTP jaisi cheezein hide karta hai; wo flag
    usse jaan-boojh ke bypass kar raha tha. Nateeja: OTP ka SMS
    notification padha ja sakta tha aur cloud LLM ko bhej diya ja sakta
    tha.

    Ye contradiction tha: ek taraf `safety.py` "OTP type nahi karunga"
    ka hard block lagata hai, doosri taraf hum OTP padh ke bahar bhej
    sakte the.

DESIGN — do baatein zaroori hain:

    1. Redaction sirf LLM-FACING output pe lagti hai (tool ka `output`).
       Device layer ka `ui_tree()` RAW rehta hai.

       Kyun: `tap_text("Send Money")` ko ASLI text chahiye element
       dhoondhne ke liye. Agar device layer pe redact kar dete to
       tapping hi tut jaati. Leak ka raasta LLM tha, device nahi.

    2. Pattern matching AGGRESSIVE nahi honi chahiye.

       "13-19 digit = card number" maan lena galat hai — order ID,
       tracking number, IMEI sab match ho jaate. Isliye card ke liye
       LUHN ALGORITHM use karte hain (asli card numbers Luhn pass karte
       hain). Aur OTP/CVV ke liye CONTEXT dekhte hain, akela number
       nahi.

       False positive ka nuksaan asli hai: agent ko `[REDACTED]` dikhega
       jahan asli text tha, aur wo confuse ho jaayega.
"""

from __future__ import annotations

import os
import re

# Kya-kya mila, uska naam — user ko batane ke liye
FOUND_CARD = "card number"
FOUND_CVV = "CVV"
FOUND_OTP = "OTP"
FOUND_IFSC = "IFSC"
FOUND_ACCOUNT = "account number"

PLACEHOLDER = "[REDACTED]"


# ----------------------------------------------------------------------
#  Card number — LUHN se
# ----------------------------------------------------------------------

# 13-19 digit, beech mein space/dash allowed (4111 1111 1111 1111)
_CARD_CANDIDATE = re.compile(r"(?<![\d])(?:\d[ -]?){12,18}\d(?![\d])")


def _luhn_ok(digits: str) -> bool:
    """
    Luhn checksum — asli card numbers ye pass karte hain.

    Isse random 16-digit number (order ID, tracking number) card samajhne
    se bach jaate hain. Roughly 90% false positive kam ho jaate hain.
    """
    if not digits.isdigit():
        return False

    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


# Card brand ka (prefix pattern, allowed lengths).
#
# ⚠️ SIRF LUHN KAAFI NAHI HAI — YE EK ASLI FALSE POSITIVE SE BANA HAI.
#
# Test mein `IMEI 490154203237518` redact ho gaya. Wajah: IMEI numbers
# BHI Luhn checksum use karte hain (wahi algorithm se unki validity check
# hoti hai). To Luhn akela IMEI ko card se alag nahi kar pata.
#
# Asli card validators BRAND PREFIX (IIN/BIN) + LENGTH dekhte hain.
# Us IMEI ki length 15 hai aur wo "4" se shuru hota hai — Visa "4" se
# shuru hota hai par uski length 13/16/19 hoti hai, 15 nahi. Isliye
# length check usse chhod deta hai.
_CARD_BRANDS: tuple[tuple[str, frozenset], ...] = (
    (r"4", frozenset({13, 16, 19})),                   # Visa
    (r"5[1-5]", frozenset({16})),                      # Mastercard
    (r"2(?:22[1-9]|2[3-9]\d|[3-6]\d\d|7[01]\d|720)", frozenset({16})),  # MC new
    (r"3[47]", frozenset({15})),                       # Amex
    (r"6(?:011|5\d\d|4[4-9]\d)", frozenset({16, 19})),  # Discover
    (r"60|6521|6522|508|353|356", frozenset({16})),    # RuPay (India)
    (r"3(?:0[0-5]|[689])", frozenset({14})),           # Diners
)


def _looks_like_card(digits: str) -> bool:
    """
    Ye digits sach mein card number lagte hain?

    Teen check, teeno zaroori:
      1. Length 13-19
      2. Luhn checksum pass
      3. Kisi asli card brand ka prefix + us brand ki sahi length

    Teesra check IMEI/order-ID jaise Luhn-valid numbers ko chhod deta hai.
    """
    if not (13 <= len(digits) <= 19) or not _luhn_ok(digits):
        return False

    for prefix, lengths in _CARD_BRANDS:
        if len(digits) in lengths and re.match(rf"^(?:{prefix})", digits):
            return True
    return False


def _redact_cards(text: str, found: list[str]) -> str:
    """Card number dhoondho (Luhn + brand verify karke) aur hata do."""

    def replace(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"[ -]", "", raw)

        if not _looks_like_card(digits):
            return raw  # card nahi hai — chhod do

        if FOUND_CARD not in found:
            found.append(FOUND_CARD)
        # Aakhri 4 digit rakhte hain — user pehchaan sake kaunsa card
        return f"{PLACEHOLDER}-{digits[-4:]}"

    return _CARD_CANDIDATE.sub(replace, text)


# ----------------------------------------------------------------------
#  Context-based — OTP, CVV, account, IFSC
# ----------------------------------------------------------------------

# "OTP is 123456", "code: 483920", "verification code 8821"
_OTP_IN_CONTEXT = re.compile(
    r"((?:otp|o\.t\.p|one[\s-]?time[\s-]?(?:password|code|pin)|"
    r"verification\s*code|security\s*code|auth\s*code|"
    r"login\s*code|passcode)"
    r"[^\d\n]{0,24})(\d{4,8})",
    re.IGNORECASE,
)

# "CVV: 123", "cvc 4821"
_CVV_IN_CONTEXT = re.compile(
    r"((?:cvv|cvc|cvv2|card\s*verification)[^\d\n]{0,16})(\d{3,4})",
    re.IGNORECASE,
)

# "A/c no 123456789012", "account number: 98765432101"
_ACCOUNT_IN_CONTEXT = re.compile(
    r"((?:a\s*/\s*c|acct|account)\s*(?:no\.?|number|#)?[^\d\n]{0,16})(\d{9,18})",
    re.IGNORECASE,
)

# IFSC ka format fix hai: 4 letter + 0 + 6 alnum
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")


def _redact_in_context(text: str, found: list[str]) -> str:
    """
    Sirf tab hatao jab aas-paas OTP/CVV jaisa shabd ho.

    Akela 6-digit number redact karna galat hai — PIN code, amount,
    year, quantity sab 4-6 digit ke hote hain. Context zaroori hai.
    """
    for pattern, label in (
        (_OTP_IN_CONTEXT, FOUND_OTP),
        (_CVV_IN_CONTEXT, FOUND_CVV),
        (_ACCOUNT_IN_CONTEXT, FOUND_ACCOUNT),
    ):

        def replace(match: re.Match, _label=label) -> str:
            if _label not in found:
                found.append(_label)
            return f"{match.group(1)}{PLACEHOLDER}"

        text = pattern.sub(replace, text)

    def replace_ifsc(match: re.Match) -> str:
        if FOUND_IFSC not in found:
            found.append(FOUND_IFSC)
        return PLACEHOLDER

    return _IFSC.sub(replace_ifsc, text)


# ----------------------------------------------------------------------
#  Public API
# ----------------------------------------------------------------------


def redaction_enabled() -> bool:
    """
    Redaction ON hai?

    DEFAULT ON — ye feature nahi, BUG FIX hai. Card number third-party
    API pe bhejna kisi bhi haalat mein theek nahi hai. Band karne ke
    liye user ko jaan-boojh ke `SAARTHI_REDACT_SENSITIVE=false` likhna
    padega.
    """
    raw = os.getenv("SAARTHI_REDACT_SENSITIVE", "true").strip().lower()
    return raw not in ("0", "false", "no", "nahi", "off")


def redact_sensitive(text: object) -> tuple[str, list[str]]:
    """
    Sensitive data hatao. Returns (saaf text, kya-kya mila).

    Order matter karta hai: card PEHLE (kyunki wo lamba hai), phir
    context-based chhote numbers.

    `object` accept karta hai (sirf str nahi) — kyunki tool output kabhi
    kabhi non-str hota hai. Redaction type ki wajah se kabhi crash nahi
    honi chahiye, warna wo khud ek outage ban jaayegi.
    """
    if text is None:
        return "", []

    value = text if isinstance(text, str) else str(text)

    if not value or not redaction_enabled():
        return value, []

    found: list[str] = []
    value = _redact_cards(value, found)
    value = _redact_in_context(value, found)
    return value, found


def redaction_note(found: list[str]) -> str:
    """
    LLM ko batao ki kuch hataya gaya hai.

    Chup-chaap hatana galat hai — agent ko lagega text waisa hi tha aur
    wo galat conclusion nikaalega. Saaf batana behtar hai.
    """
    if not found:
        return ""
    return (
        f"\n\n[SECURITY: {', '.join(found)} hata diya gaya — "
        f"ye data LLM ko nahi bheja jaata. User se poochho agar zarurat ho.]"
    )
