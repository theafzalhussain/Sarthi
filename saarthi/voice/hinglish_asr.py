"""
Hinglish ASR Layer — PILLAR #1, ab voice pe bhi.

PROBLEM:
    Whisper (aur baaki saare ASR models) English-first bane hain.
    Hinglish bolne pe wo galat sunte hain:

        Tu bola              Whisper ne suna
        ------------------   ---------------------
        "paytm kholo"         "pay time cholo"
        "zomato se order"     "tomato se order"
        "do hazaar paise"     "do hazar peace"
        "phonepe se bhej"     "phone pay se beige"
        "irctc pe dekho"      "i r c t c pe dekho"

    Ek galat word = pura command fail. Ye wahi 25-35% word error rate
    hai jo research mein documented hai.

SOLUTION (do hisse):

    1. BIASING (sunne se pehle)
       Whisper ko `initial_prompt` deke batao ki Hinglish aane wali hai,
       aur app naam bhi de do. Isse wo unhi words ki taraf jhukta hai.

    2. CORRECTION (sunne ke baad)
       Jo galat suna, usko theek karo:
         - Devanagari aaya to roman banao
         - Known galtiyan seedha fix karo ("pay time" -> "paytm")
         - Fuzzy match se app naam pakdo ("swiggi" -> "swiggy")

DESIGN RULE (bahut important):
    Correction se NAYI galti nahi honi chahiye.
    Jaise "call" ko "khol" mat banao — user sach mein "call kar"
    bol sakta hai. Isliye:
      - sirf distinctive galtiyan fix karo
      - risky wale sirf context ke saath
      - fuzzy match pe high threshold rakho
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from ..lang.lexicon import INDIAN_APPS, VERB_INTENTS
from ..lang.normalize import has_devanagari, transliterate

# ======================================================================
#  1. BIASING — Whisper ko pehle se batao
# ======================================================================

# ⚠️⚠️ YE SENTENCES AB PROMPT MEIN NAHI JAATE — HALLUCINATION KARATE THE.
#
# ASLI BUG (user ki machine pe mila):
#     User ne bola : "paytm kholo"
#     Whisper suna : "Open YouTube and play Theravins on."
#
#     Audio quality PERFECT thi (peak 17790). Problem ye thi ki
#     `initial_prompt` mein "Laptop pe chrome khol ke YouTube chala do"
#     jaisa POORA SENTENCE tha — aur Whisper ne usko COPY kar diya.
#
# WAJAH: Whisper ka `initial_prompt` "pichla context" ki tarah kaam
# karta hai, keyword hint ki tarah nahi. Usme prose daalo to model
# usi prose ko AAGE BADHATA hai — khaas kar jab audio chhota ya
# halka ho. Ye Whisper ki jaani-maani kamzori hai.
#
# SAHI TAREEKA: sirf VOCABULARY (comma-separated shabd), sentences NAHI.
#
# Ye list yahan REFERENCE ke liye rakhi hai — taaki koi dobara
# "biasing badhane" ke chakkar mein inhe wapas prompt mein na daal de.
_HALLUCINATION_TRAP_EXAMPLES = [
    "Bhai paytm kholo aur bijli ka bill bhar do.",
    "WhatsApp pe mummy ko message bhej do ki late aaunga.",
    "Swiggy se khana order kar do, do hazaar tak ka.",
    "Laptop pe chrome khol ke YouTube chala do.",
]

# Hinglish ke aam SHABD (sentences nahi!). Ye Whisper ko batate hain ki
# roman-script Hinglish expected hai, bina koi sentence pattern diye.
HINGLISH_VOCAB_HINTS = [
    "kholo", "chalao", "bhejo", "dikhao", "batao", "padho",
    "bijli", "bill", "recharge", "paise", "rupay", "hazaar", "lakh",
    "mummy", "papa", "bhai", "message", "screenshot", "notification",
]

# In apps ko prompt mein daalna sabse zyada faayda deta hai —
# ye distinctive naam hain jo Whisper aksar galat sunta hai.
PRIORITY_APPS = [
    "Paytm", "PhonePe", "GPay", "Zomato", "Swiggy", "IRCTC",
    "Flipkart", "Myntra", "Blinkit", "Zepto", "MyJio", "Airtel",
    "DigiLocker", "WhatsApp", "Instagram", "YouTube", "Groww",
    "Hotstar", "Ola", "Uber", "Rapido", "BigBasket",
]


def build_initial_prompt(
    extra_words: list[str] | None = None,
    max_chars: int = 900,
) -> str:
    """
    Whisper ke liye `initial_prompt` banao.

    Ye model ko Hinglish ki taraf jhukata hai. Bilkul free hai —
    koi training nahi, koi extra compute nahi. Sirf ek string.

    Args:
        extra_words: Extra vocabulary — contact naam, seekhi hui
                     skills ke naam, ya jo bhi tu boost karna chahta hai
        max_chars: Whisper ka prompt limited hota hai (~224 tokens),
                   isliye lamba prompt kaat dete hain

    Returns:
        Prompt string jo Whisper ko diya jaata hai
    """
    # SIRF VOCABULARY — koi sentence nahi.
    #
    # Sentences hallucination karate hain (upar
    # _HALLUCINATION_TRAP_EXAMPLES ka comment padh). Comma-separated
    # word list se biasing milti hai par model ko "aage likho" ka
    # pattern nahi milta.
    words: list[str] = list(PRIORITY_APPS)

    # User ka apna vocabulary (contacts, skill naam) — sabse zyada
    # faayda isi ka hai, isliye app naam ke baad turant
    if extra_words:
        for word in extra_words[:30]:
            if word and word.strip():
                words.append(word.strip())

    words.extend(HINGLISH_VOCAB_HINTS)

    # Duplicate hatao, order bacha ke
    seen = set()
    unique: list[str] = []
    for word in words:
        key = word.lower()
        if key not in seen:
            seen.add(key)
            unique.append(word)

    prompt = ", ".join(unique)

    # Whisper ka prompt ~224 tokens tak hi maanta hai. Aur CHHOTA
    # prompt = kam hallucination, isliye default bhi kam rakha hai.
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars].rsplit(",", 1)[0]

    return prompt


def looks_like_prompt_echo(text: str, prompt: str, threshold: float = 0.55) -> bool:
    """
    Whisper ne prompt ko hi wapas ugal diya?

    Ye HALLUCINATION GUARD hai. Chahe prompt se sentences hata diye
    hon, phir bhi kabhi-kabhi model prompt ke shabd copy kar deta hai
    (khaas kar jab audio bahut chhota ya halka ho).

    Tareeka: output ke kitne shabd prompt mein maujood hain. Zyadatar
    shabd prompt se aaye = model ne suna nahi, copy kiya.

    >>> looks_like_prompt_echo("Paytm PhonePe GPay Zomato", "Paytm, PhonePe, GPay, Zomato")
    True
    >>> looks_like_prompt_echo("mera naam afzal hai", "Paytm, PhonePe, GPay")
    False
    """
    import re

    words = re.findall(r"[a-z]+", (text or "").lower())
    if len(words) < 3:
        return False

    prompt_words = set(re.findall(r"[a-z]+", (prompt or "").lower()))
    if not prompt_words:
        return False

    overlap = sum(1 for word in words if word in prompt_words)
    return (overlap / len(words)) >= threshold


# ======================================================================
#  2. CORRECTION — sunne ke baad theek karo
# ======================================================================

# Ye galtiyan SAFE hain fix karne ke liye, kyunki ye phrases Hinglish
# mein koi doosra matlab nahi rakhte.
#
# Format: regex pattern -> replacement
# Sab word-boundary ke saath, case-insensitive.
SAFE_CORRECTIONS: list[tuple[str, str]] = [
    # --- Paytm (sabse zyada galat suna jaata hai) ---
    (r"\bpay\s*t\s*m\b", "paytm"),
    (r"\bpay\s*time\b", "paytm"),
    (r"\bpaytime\b", "paytm"),
    (r"\bpay\s*tim\b", "paytm"),
    (r"\bpete\s*m\b", "paytm"),
    (r"\bpaitm\b", "paytm"),
    # --- PhonePe ---
    (r"\bphone\s*pay\b", "phonepe"),
    (r"\bfone\s*pe\b", "phonepe"),
    (r"\bfone\s*pay\b", "phonepe"),
    (r"\bphone\s*pe\b", "phonepe"),
    # --- Google Pay ---
    (r"\bg\s*pay\b", "gpay"),
    (r"\bgee\s*pay\b", "gpay"),
    (r"\bjee\s*pay\b", "gpay"),
    # --- Zomato ("tomato" classic galti hai) ---
    (r"\bjomato\b", "zomato"),
    (r"\bzomatto\b", "zomato"),
    (r"\bzomata\b", "zomato"),
    # --- Swiggy ---
    (r"\bswiggi\b", "swiggy"),
    (r"\bswigi\b", "swiggy"),
    (r"\bsweegy\b", "swiggy"),
    (r"\bswiggy'?s\b", "swiggy"),
    # --- IRCTC (letter by letter suna jaata hai) ---
    (r"\bi\s*r\s*c\s*t\s*c\b", "irctc"),
    (r"\birctse\b", "irctc"),
    (r"\bircts\b", "irctc"),
    # --- WhatsApp ---
    (r"\bwhats\s*app\b", "whatsapp"),
    (r"\bwhat'?s\s*app\b", "whatsapp"),
    (r"\bwatsapp\b", "whatsapp"),
    (r"\bwats\s*app\b", "whatsapp"),
    # --- Others ---
    (r"\bblink\s*it\b", "blinkit"),
    (r"\bbig\s*basket\b", "bigbasket"),
    (r"\bmy\s*jio\b", "myjio"),
    (r"\bdigi\s*locker\b", "digilocker"),
    (r"\bgrow\b(?=\s|$)", "groww"),
    (r"\bhot\s*star\b", "hotstar"),
    (r"\bmake\s*my\s*trip\b", "makemytrip"),
    (r"\bphysics\s*wallah\b", "physicswallah"),
    # --- Hinglish money words ---
    # "paise" -> "peace" ek classic galti hai
    (r"\bpeace\b(?=\s+(bhej|transfer|de|do|kar))", "paise"),
    (r"\bpaisa\s*e\b", "paise"),
    (r"\bhajar\b", "hazaar"),
    (r"\bhazar\b", "hazaar"),
    (r"\bhazzar\b", "hazaar"),
    (r"\brupee\s*(?=bhej|de|do|transfer)", "rupay "),
    (r"\broopay\b", "rupay"),
    (r"\brupay?e\b", "rupay"),
    (r"\blak\b", "lakh"),
    (r"\black\b(?=\s+(rupay|rupee|ka|tak))", "lakh"),
    # --- Hinglish numbers ---
    (r"\bdie\s+hazaar\b", "dhai hazaar"),
    (r"\bthe\s+hazaar\b", "dhai hazaar"),
    (r"\bdai\s+hazaar\b", "dhai hazaar"),
    (r"\bsadhe\b", "saadhe"),
    (r"\bsadde\b", "saadhe"),
    (r"\bpone\b(?=\s+(char|teen|do|paanch))", "paune"),
    (r"\bpanch\b", "paanch"),
    # --- Hinglish verbs (sirf safe wale) ---
    (r"\bcholo\b", "kholo"),
    (r"\bkolo\b", "kholo"),
    (r"\bkhol\s*o\b", "kholo"),
    (r"\bbhaij\b", "bhej"),
    (r"\bbeige\b", "bhej"),
    (r"\bbhaje\b", "bhej"),
    (r"\bdhundo\b", "dhoondho"),
    (r"\bdhundho\b", "dhoondho"),
    (r"\byaad\s*rakho\b", "yaad rakho"),
    (r"\byard\s+rakh\b", "yaad rakh"),
    # --- Confirmation words ---
    (r"\bhaa+n?\b", "haan"),
    (r"\bnahin\b", "nahi"),
    (r"\bnai\b(?=\s|$)", "nahi"),
]


# Ye corrections KHATARNAK hain — sirf context ke saath karo.
#
# Do tarah ke signals hain:
#   ENABLERS — inme se koi ek ho to fix karo
#   BLOCKERS — inme se koi ek ho to fix MAT karo (enabler ho tab bhi)
#
# Blockers kyun zaroori hain (asli bug se seekha):
#     "tomato khareedo sabzi mandi se"
#   Isme "se" tha, jo enabler list mein tha, to "tomato" -> "zomato"
#   ban gaya. Galat! Banda sabzi khareed raha tha, app nahi khol raha.
#   Isliye "se"/"pe" jaise common words enabler nahi ho sakte, aur
#   "sabzi"/"khareedo"/"mandi" blockers hone chahiye.
#
# SEEKH: enabler DISTINCTIVE hona chahiye, common nahi.


@dataclass(frozen=True)
class ContextRule:
    """Ek context-dependent correction."""

    wrong: str
    right: str
    enablers: tuple[str, ...]          # koi ek ho to fix
    blockers: tuple[str, ...] = ()     # koi ek ho to fix nahi


CONTEXT_CORRECTIONS: list[ContextRule] = [
    # "coal"/"kol" -> "khol" — sirf jab app ka naam paas ho.
    # Warna "coal mine" bhi badal jaayega.
    ContextRule(
        wrong="coal",
        right="khol",
        enablers=(
            "paytm", "whatsapp", "app", "phonepe", "chrome", "youtube",
            "instagram", "swiggy", "zomato", "settings", "camera",
        ),
        blockers=("mine", "mining", "india", "power", "plant", "coal-fired"),
    ),
    ContextRule(
        wrong="kol",
        right="khol",
        enablers=(
            "paytm", "whatsapp", "app", "phonepe", "chrome", "youtube",
            "instagram", "swiggy", "zomato", "settings", "camera",
        ),
        blockers=("kolkata", "kolhapur"),
    ),
    # "tomato" -> "zomato" — sirf food-DELIVERY ke context mein.
    # Enablers distinctive hain. Sabzi khareedne wale words blockers hain.
    ContextRule(
        wrong="tomato",
        right="zomato",
        enablers=("order", "app", "kholo", "khol", "delivery", "restaurant", "swiggy"),
        blockers=(
            "khareedo", "khareed", "sabzi", "mandi", "kilo", "bhaav",
            "daam", "price", "vegetable", "tamatar", "salad", "recipe",
            "grocery", "buy",
        ),
    ),
    # "bar" -> "bhar" — sirf bill/payment context mein
    ContextRule(
        wrong="bar",
        right="bhar",
        enablers=("bill", "recharge", "paise", "amount", "bijli"),
        blockers=("baar", "restaurant", "pub", "chocolate", "bar chart"),
    ),
    # "bell" / "bil" -> "bill"
    ContextRule(
        wrong="bell",
        right="bill",
        enablers=("bhar", "bijli", "paytm", "pay", "electricity", "recharge"),
        blockers=("ring", "doorbell", "school", "bajao"),
    ),
    ContextRule(
        wrong="bil",
        right="bill",
        enablers=("bhar", "bijli", "pay", "electricity", "recharge"),
    ),
]


@dataclass
class CorrectionResult:
    """Transcript correction ka result — transparency ke liye."""

    original: str
    corrected: str

    # Kya kya badla (debug aur trust ke liye)
    changes: list[tuple[str, str]] = field(default_factory=list)
    had_devanagari: bool = False

    @property
    def was_changed(self) -> bool:
        return self.original.strip() != self.corrected.strip()

    def explain(self) -> str:
        """User/debug ko dikhane ke liye."""
        if not self.was_changed:
            return "(koi correction nahi)"

        lines = [f'"{self.original}" -> "{self.corrected}"']
        if self.had_devanagari:
            lines.append("  Devanagari se roman kiya")
        for before, after in self.changes:
            lines.append(f"  '{before}' -> '{after}'")
        return "\n".join(lines)


# ----------------------------------------------------------------------
#  Fuzzy app-name matching
# ----------------------------------------------------------------------

# Ye words kabhi app naam samajh ke fuzzy-fix nahi karne. Common English/
# Hinglish words hain — inko app banane se bahut galtiyan hongi.
_FUZZY_STOPWORDS: set[str] = {
    "map", "maps", "call", "phone", "mobile", "system", "browser", "files",
    "file", "photo", "photos", "camera", "clock", "alarm", "calendar",
    "contacts", "messages", "sms", "settings", "setting", "drive", "prime",
    "train", "x", "vi", "bob", "sbi", "pw", "wa", "yt", "fb", "insta",
    "snap", "kite", "cred", "jio", "grow", "groww", "axis", "kotak",
    "chrome", "gmail", "amazon", "uber", "ola",
}

# Sirf inhi apps ke against fuzzy match karenge — distinctive naam
_FUZZY_TARGETS: list[str] = sorted(
    name
    for name in INDIAN_APPS
    if " " not in name and len(name) >= 5 and name not in _FUZZY_STOPWORDS
)

# Hinglish ke common words — inko app naam nahi samjhna
_KNOWN_WORDS: set[str] = set()
for _phrases in VERB_INTENTS.values():
    for _p in _phrases:
        _KNOWN_WORDS.update(_p.split())


def _fuzzy_fix_apps(
    text: str, threshold: float = 0.86
) -> tuple[str, list[tuple[str, str]]]:
    """
    Jo word app naam jaisa lag raha hai usko theek karo.

    Ye SAFE_CORRECTIONS ke baad chalta hai — jo galtiyan list mein
    nahi hain, unko pakadta hai.

    High threshold (0.86) jaan-boojh ke — kam rakhne se normal words
    bhi app ban jaate hain, jo bahut buri baat hai.
    """
    changes: list[tuple[str, str]] = []
    tokens = text.split()
    out: list[str] = []

    for token in tokens:
        # Punctuation alag rakho, wapas laga denge
        prefix = ""
        suffix = ""
        core = token
        while core and not core[0].isalnum():
            prefix += core[0]
            core = core[1:]
        while core and not core[-1].isalnum():
            suffix = core[-1] + suffix
            core = core[:-1]

        lowered = core.lower()

        # Chhote words, known words, already-correct apps — chhod do
        if (
            len(lowered) < 5
            or lowered in INDIAN_APPS
            or lowered in _KNOWN_WORDS
            or lowered in _FUZZY_STOPWORDS
            or not lowered.isalpha()
        ):
            out.append(token)
            continue

        matches = difflib.get_close_matches(
            lowered, _FUZZY_TARGETS, n=1, cutoff=threshold
        )
        if matches and matches[0] != lowered:
            changes.append((core, matches[0]))
            out.append(prefix + matches[0] + suffix)
        else:
            out.append(token)

    return " ".join(out), changes


# ----------------------------------------------------------------------
#  Main correction pipeline
# ----------------------------------------------------------------------


def correct_transcript(text: str, use_fuzzy: bool = True) -> CorrectionResult:
    """
    ASR ka transcript theek karo.

    Pipeline:
        1. Whitespace saaf
        2. Devanagari -> roman (lexicon roman mein hai)
        3. Safe corrections (known galtiyan)
        4. Context corrections (khatarnak wale, context ke saath)
        5. Fuzzy app-name fix (jo bacha)

    >>> correct_transcript("pay time cholo").corrected
    'paytm kholo'
    >>> correct_transcript("do hazar peace bhej do").corrected
    'do hazaar paise bhej do'
    """
    original = text
    working = re.sub(r"\s+", " ", text).strip()

    if not working:
        return CorrectionResult(original=original, corrected="")

    changes: list[tuple[str, str]] = []

    # --- 2. Devanagari -> roman ---
    had_dev = has_devanagari(working)
    if had_dev:
        working = transliterate(working)

    # --- 3. Safe corrections ---
    for pattern, replacement in SAFE_CORRECTIONS:
        match = re.search(pattern, working, flags=re.IGNORECASE)
        if match:
            before = match.group(0)
            working = re.sub(pattern, replacement, working, flags=re.IGNORECASE)
            if before.strip().lower() != replacement.strip().lower():
                changes.append((before.strip(), replacement.strip()))

    # --- 4. Context corrections (enablers + blockers) ---
    lowered = working.lower()

    def _has_word(word: str, haystack: str) -> bool:
        return bool(re.search(rf"\b{re.escape(word)}\b", haystack))

    for rule in CONTEXT_CORRECTIONS:
        if not _has_word(rule.wrong, lowered):
            continue

        # Blocker hai to bilkul haath mat lagao
        if any(_has_word(b, lowered) for b in rule.blockers):
            continue

        # Enabler hona zaroori hai
        if not any(_has_word(e, lowered) for e in rule.enablers):
            continue

        working = re.sub(
            rf"\b{re.escape(rule.wrong)}\b",
            rule.right,
            working,
            flags=re.IGNORECASE,
        )
        changes.append((rule.wrong, rule.right))
        lowered = working.lower()

    # --- 5. Fuzzy app fix ---
    if use_fuzzy:
        working, fuzzy_changes = _fuzzy_fix_apps(working)
        changes.extend(fuzzy_changes)

    working = re.sub(r"\s+", " ", working).strip()

    return CorrectionResult(
        original=original,
        corrected=working,
        changes=changes,
        had_devanagari=had_dev,
    )


# ----------------------------------------------------------------------
#  Quality check
# ----------------------------------------------------------------------


def looks_like_garbage(text: str, min_length: int = 2) -> bool:
    """
    Transcript bekaar hai? (background noise, khaali awaaz)

    Whisper silence pe bhi kuch na kuch nikaal deta hai — jaise
    "Thank you." ya "[BLANK_AUDIO]". Unko agent tak nahi bhejna,
    warna wo bekaar ka kaam karega aur free-tier tokens jalega.
    """
    cleaned = text.strip().strip(".,!?-—…\"' ")

    if len(cleaned) < min_length:
        return True

    # Whisper ke known hallucinations jab audio khali ho
    noise_outputs = {
        "thank you", "thanks", "thank you.", "you", "yeah", "okay", "ok",
        "hmm", "mm", "uh", "um", "ah", "oh", "so", "bye", "the",
        "[blank_audio]", "(silence)", "[silence]", "[music]", "(music)",
        "subscribe", "thanks for watching", "please subscribe",
    }
    if cleaned.lower() in noise_outputs:
        return True

    # Sirf punctuation/numbers
    if not any(ch.isalpha() for ch in cleaned):
        return True

    return False
