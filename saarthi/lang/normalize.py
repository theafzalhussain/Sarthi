"""
Hinglish Normalizer.

Kaam: gandi, mili-juli, bolchaal wali Hinglish ko saaf structured
information mein badalna — TAAKI LLM ko clarity mile.

Kyun zaroori hai:
    Input : "arre bhai zara paytm khol ke do hazaar paanch sau ka
             bijli ka bill bhar dena, jaldi"
    Output: intent=pay, app=paytm(net.one97.paytm), amount=2500,
            risky=True, clean="paytm khol ke 2500 ka bijli ka bill bhar dena"

Isse LLM ko guess nahi karna padta — usse ready-made hints milte hain.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .lexicon import (
    FILLER_WORDS,
    FRACTION_WORDS,
    NUMBER_MULTIPLIERS,
    NUMBER_WORDS,
    detect_intent,
    detect_target_device,
    find_app_mentions,
    is_risky,
)

# ======================================================================
#  Devanagari -> Roman (basic transliteration)
#  User kabhi "पेटीएम खोलो" bhi likh sakta hai. Handle karna hai.
# ======================================================================

DEVANAGARI_MAP: dict[str, str] = {
    # Vowels
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri",
    # Consonants
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    # Nukta variants
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r",
    "ढ़": "rh", "फ़": "f",
    # Matras
    "ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
    "ं": "n", "ः": "h", "ँ": "n", "़": "", "्": "",
    # Digits
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}


def has_devanagari(text: str) -> bool:
    """Text mein Hindi script hai?"""
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def transliterate(text: str) -> str:
    """
    Devanagari ko roman mein badlo.

    Perfect nahi hai — par LLM ke liye kaafi hai, aur ye
    lexicon matching enable karta hai.

    >>> transliterate("पेटीएम")
    'peteeem'
    """
    return "".join(DEVANAGARI_MAP.get(ch, ch) for ch in text)


# ======================================================================
#  Number parsing — Hindi words se digits
# ======================================================================


def parse_hindi_number(text: str) -> float | None:
    """
    Hindi number words -> actual number.

    >>> parse_hindi_number("do hazaar paanch sau")
    2500.0
    >>> parse_hindi_number("dhai hazaar")
    2500.0
    >>> parse_hindi_number("saadhe teen")
    3.5
    """
    tokens = text.lower().split()
    if not tokens:
        return None

    total = 0.0       # Poora jama kiya hua
    current = 0.0     # Abhi ka group
    modifier = 0.0    # saadhe / paune ka effect
    found_any = False

    for token in tokens:
        token = token.strip(",.!?")

        # "saadhe" / "paune" — agle number ko modify karte hain
        if token in ("saadhe", "sadhe"):
            modifier = 0.5
            found_any = True
            continue
        if token == "paune":
            modifier = -0.25
            found_any = True
            continue

        # Standalone fractions: dhai, sava, aadha
        if token in FRACTION_WORDS and token not in ("saadhe", "sadhe", "paune"):
            current += FRACTION_WORDS[token]
            found_any = True
            continue

        # Basic numbers
        if token in NUMBER_WORDS:
            current += NUMBER_WORDS[token] + modifier
            modifier = 0.0
            found_any = True
            continue

        # Digits ("2000", "2.5")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            current += float(token) + modifier
            modifier = 0.0
            found_any = True
            continue

        # Multipliers: sau, hazaar, lakh, crore
        if token in NUMBER_MULTIPLIERS:
            mult = NUMBER_MULTIPLIERS[token]
            if current == 0:
                current = 1.0
            # "lakh"/"crore" pe pura total multiply hota hai
            if mult >= 100_000:
                total = (total + current) * mult
                current = 0.0
            else:
                current *= mult
                total += current
                current = 0.0
            found_any = True
            continue

    if not found_any:
        return None

    return total + current


# ======================================================================
#  LANGUAGE DETECTION
#
#  Kaam: user ne English mein likha ya Hinglish mein? Uske hisaab se
#  agent usi bhasha mein jawab dega.
#
#  DESIGN SABAK (BUG#4 se seekha): marker words DISTINCTIVE hone
#  chahiye, common nahi. "me", "do", "is", "us", "main", "the", "par"
#  — ye Hinglish mein bhi hain aur English mein bhi. Inko marker
#  banaya to "play a song for me" bhi Hinglish detect ho jaayega.
#
#  Isliye neeche sirf wo words hain jo ENGLISH MEIN NAHI hote.
# ======================================================================

_HINGLISH_MARKERS: set[str] = {
    # Verbs / actions
    "kar", "karo", "karna", "kardo", "kro", "karke", "karunga", "karenge",
    "kholo", "khol", "kholna", "chalao", "chala", "chalu", "chalana",
    "bhejo", "bhej", "bhejna", "daal", "daalo", "daalna",
    "likho", "likh", "likhna", "bata", "batao", "batana",
    "dekh", "dekho", "dekhna", "dikha", "dikhao", "sun", "suno",
    "laga", "lagao", "hata", "hatao", "band", "bandh", "ruk", "ruko",
    "de", "dena", "dedo", "lo", "lena", "milega", "chahiye", "chahta",
    # Hona / होना
    "hai", "hain", "ho", "hoga", "hogi", "hona", "hua", "hui", "thi", "tha",
    "raha", "rahe", "rahi", "gaya", "gayi", "diya", "liya",
    # Sawaal
    "kya", "kyun", "kyu", "kaise", "kaisa", "kaisi", "kahan", "kaun",
    "kaunsa", "kaunsi", "kitna", "kitne", "kitni", "kab",
    # Sarvnaam / possessive
    "mera", "meri", "mere", "tera", "teri", "tere", "tumhara", "tumhari",
    "apna", "apni", "mujhe", "tujhe", "usko", "isko", "unko", "inko",
    "hum", "hamara", "tum", "tu", "aap", "uska", "iska",
    # Haan / naa
    "nahi", "nhi", "naa", "mat", "haan", "han", "haa", "bilkul",
    # Connectors (English mein nahi hote)
    "aur", "lekin", "magar", "matlab", "warna", "phir", "toh", "kyunki",
    "agar", "jab", "tab", "abhi", "thoda", "zara", "jara", "bas", "bhi",
    # Vishesan
    "accha", "achha", "acchi", "theek", "thik", "sahi", "galat",
    "bada", "chhota", "jaldi", "dheere", "purana", "naya",
    # Aam shabd
    "bhai", "yaar", "yaad", "baat", "kaam", "cheez", "wala", "wali",
    "sab", "kuch", "koi", "waqt", "paise", "paisa", "gaana", "gana",
    "khana", "pani", "ghar", "aaj", "kal", "subah", "shaam", "raat",
    # Particles
    "ke", "ka", "ki", "ko", "se", "mein", "pe", "ye", "yeh", "wo", "woh",
    "isse", "usse", "jo", "hi",
}

# Ye Hinglish mein bhi common hain par ENGLISH WORD bhi hain —
# jaan-boojh ke marker nahi banaya. Yahan reference ke liye rakhe hain
# taaki koi baad mein galti se add na kar de.
_AMBIGUOUS_NOT_MARKERS: set[str] = {
    "me", "do", "is", "us", "main", "the", "par", "so", "to", "no",
    "on", "in", "at", "an", "as", "he", "we", "be", "or", "and", "a",
    "hum",  # "hum" English mein bhi hai (humming)
}


def detect_language(text: str) -> str:
    """
    User ne kis bhasha mein likha? "hinglish" ya "english".

    Ye interface aur jawab ki bhasha decide karta hai:
        User English mein likhe  -> agent English mein jawab de
        User Hinglish mein likhe -> agent Hinglish mein jawab de

    Doubt ho to "hinglish" — kyunki ye project Hinglish-first hai
    (Pillar #1), aur Hinglish user ko English jawab dena zyada
    kharaab lagta hai ulte se.

    >>> detect_language("open youtube and play a song")
    'english'
    >>> detect_language("youtube pe gaana chala do")
    'hinglish'
    >>> detect_language("bhai ek song play kar dena")
    'hinglish'
    """
    if not text or not text.strip():
        return "hinglish"

    # Devanagari hai to pakka Hindi
    if has_devanagari(text):
        return "hinglish"

    tokens = re.findall(r"[a-z]+", text.lower())
    if not tokens:
        return "hinglish"

    hits = sum(1 for token in tokens if token in _HINGLISH_MARKERS)

    if hits == 0:
        return "english"

    # Ek-do marker aur baaki sab English? Chhoti line mein ek marker
    # kaafi hai ("play song bhai"), par lambi English line mein ek
    # marker ittefaq ho sakta hai.
    if len(tokens) >= 8 and hits == 1:
        return "english"

    return "hinglish"


def extract_amount(text: str) -> float | None:
    """
    Text se paison ka amount nikaalo.

    >>> extract_amount("2000 rupay bhej do")
    2000.0
    >>> extract_amount("dhai hazaar ka recharge")
    2500.0
    """
    lowered = text.lower()

    # Pehle: "₹2000", "Rs 2000", "2000 rupay"
    patterns = [
        r"₹\s*(\d+(?:,\d+)*(?:\.\d+)?)",
        r"\brs\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
        r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rupay|rupee|rupees|rs\b|₹)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1).replace(",", ""))

    # Phir: Hindi words wale numbers, agar paison ka context hai
    money_context = any(
        word in lowered
        for word in ("rupay", "rupee", "paise", "paisa", "₹", "rs",
                     "bill", "recharge", "pay", "transfer", "bhej")
    )
    if money_context:
        # Number-related tokens ka group dhoondo
        number_tokens = (
            set(NUMBER_WORDS)
            | set(NUMBER_MULTIPLIERS)
            | set(FRACTION_WORDS)
        )
        tokens = lowered.split()
        chunk: list[str] = []
        for token in tokens:
            clean = token.strip(",.!?₹")
            if clean in number_tokens or re.fullmatch(r"\d+(?:\.\d+)?", clean):
                chunk.append(clean)
            elif chunk:
                break  # Group toot gaya
        if chunk:
            return parse_hindi_number(" ".join(chunk))

    return None


# ======================================================================
#  Text cleaning
# ======================================================================


def strip_fillers(text: str) -> str:
    """
    Bekaar ke words hatao — "bhai", "zara", "please" etc.

    Dhyan: sirf tab hataate hain jab kaafi text bacha rahe.
    Warna "bhai" hi pura message ho to khali string reh jaayegi.
    """
    tokens = text.split()
    # Multi-word fillers pehle hatao
    working = " ".join(tokens)
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        if " " in filler:
            working = re.sub(
                rf"\b{re.escape(filler)}\b", " ", working, flags=re.IGNORECASE
            )

    kept = [
        tok
        for tok in working.split()
        if tok.strip(",.!?").lower() not in FILLER_WORDS
    ]

    # Sab hat gaya to original hi return kar do
    if not kept:
        return text.strip()

    return " ".join(kept)


def normalize_whitespace(text: str) -> str:
    """Extra spaces aur weird unicode saaf karo."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


# ======================================================================
#  Main result type
# ======================================================================


@dataclass
class ParsedCommand:
    """
    Hinglish command ka structured roop.

    Ye LLM ko hint ke roop mein diya jaata hai — isse wo galti
    kam karta hai aur tools sahi chunta hai.
    """

    original: str
    clean: str

    intent: str | None = None
    target_device: str | None = None

    apps: list[tuple[str, str]] = field(default_factory=list)
    amount: float | None = None

    risky: bool = False
    risky_reasons: list[str] = field(default_factory=list)

    had_devanagari: bool = False

    # --- Helpers ---

    @property
    def primary_app(self) -> tuple[str, str] | None:
        """Sabse pehla mentioned app."""
        return self.apps[0] if self.apps else None

    def to_hint(self) -> str:
        """
        LLM ke liye readable hint banao.

        Ye system prompt ke saath jaata hai — LLM ko guess nahi
        karna padta ki user ka matlab kya tha.
        """
        parts: list[str] = []

        if self.intent:
            parts.append(f"Lagta hai user ye chahta hai: {self.intent}")

        if self.apps:
            app_list = ", ".join(f"{name} ({pkg})" for name, pkg in self.apps)
            parts.append(f"Mentioned apps: {app_list}")

        if self.target_device:
            parts.append(f"Target device: {self.target_device}")

        if self.amount is not None:
            # Poora number ho to decimal na dikhao
            amount_str = (
                f"{self.amount:.0f}"
                if self.amount == int(self.amount)
                else f"{self.amount}"
            )
            parts.append(f"Amount detected: {amount_str}")

        if self.risky:
            parts.append(
                f"RISKY COMMAND — confirmation lena zaroori hai. "
                f"Wajah: {', '.join(self.risky_reasons[:5])}"
            )

        if self.had_devanagari:
            parts.append("User ne Devanagari script use ki thi")

        if not parts:
            return ""

        return "[Hinglish analysis]\n" + "\n".join(f"- {p}" for p in parts)


# ======================================================================
#  Entry point
# ======================================================================


def parse(text: str) -> ParsedCommand:
    """
    Hinglish command ko samjho.

    Ye SAARTHI ka pehla step hai — har user input isse guzarta hai.

    >>> result = parse("bhai paytm khol ke 2000 ka bill bhar de")
    >>> result.intent
    'pay'
    >>> result.amount
    2000.0
    >>> result.risky
    True
    """
    original = text
    working = normalize_whitespace(text)

    # Devanagari ho to roman banao (lexicon matching ke liye)
    had_dev = has_devanagari(working)
    if had_dev:
        working = transliterate(working)

    lowered_for_match = working.lower()

    risky, reasons = is_risky(lowered_for_match)

    return ParsedCommand(
        original=original,
        clean=strip_fillers(working),
        intent=detect_intent(lowered_for_match),
        target_device=detect_target_device(lowered_for_match),
        apps=find_app_mentions(lowered_for_match),
        amount=extract_amount(lowered_for_match),
        risky=risky,
        risky_reasons=reasons,
        had_devanagari=had_dev,
    )
