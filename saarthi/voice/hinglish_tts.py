"""
Hinglish TTS — Hindi neural voice ko ROMAN text padhna sikhaaya.

PROBLEM (ye module kyun bana):

    Edge/Microsoft ki Hindi neural voices (hi-IN-MadhurNeural — Jarvis-type
    male voice) DEVANAGARI padhti hain. Lekin SAARTHI ka pura ecosystem
    ROMAN Hinglish mein hai:

        "bhai paytm khol ke dhai hazaar ka bill bhar do"

    English voice (en-GB-RyanNeural) isko padh leti hai, par uchcharan
    angrezi hota hai — "bhai" -> "bay-hi", "kholo" -> "koh-loh". Robot jaisa
    lagta hai. Human touch zero.

SOLUTION — teen step ka pipeline (sab PURE LOGIC, mic ke bina test hota hai):

    1. detect    -> text Hinglish hai ya pure English? (voice choice)
    2. numbers   -> "2500" -> "do hazaar paanch sau" (Hindi voice ke liye)
    3. translit  -> roman shabd -> Devanagari (dict + rules)

        "bhai paytm kholo"  ->  "भाई paytm खोलो"

    Mixed script OUTPUT jaan-boojh ke rakha hai: jo shabd translit ho gaye
    wo Hindi voice ke liye perfect hain, aur brands (paytm, youtube...)
    Latin mein hi theek padhe jaate hain. hi-IN voices mixed script
    naturally handle karti hain.


DESIGN NOTE — transliteration ki imaandaar hadd:

    Ye Google-level transliterator NAHI hai. Do layers hain:

        Layer 1: ~350 sabse common Hinglish shabdon ka DICTIONARY
                 (90%+ kisi bhi bolne wale sentence mein yahi aate hain)
        Layer 2: jo dict mein nahi, uspe CONSERVATIVE rules — jab tak
                 pakka na ho, shabd Latin hi rehne do. Galat Devanagari
                 se accha hai ki voice usko English jaisa hi padhe.

    Naya shabd sikhaana ho to bas HINDI_WORDS mein ek line add karo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ======================================================================
#  1. Script detection — voice choice ka base
# ======================================================================

# Devanagari range
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# English function words — ye dikh gayi to text English-side heavy hai
_ENGLISH_STOPWORDS = {
    "the", "is", "are", "am", "was", "were", "what", "how", "when", "where",
    "who", "why", "which", "please", "can", "could", "would", "should",
    "will", "shall", "do", "does", "did", "and", "or", "of", "for", "with",
    "this", "that", "these", "those", "there", "here", "about", "from",
    "your", "you", "me", "my", "we", "it", "its", "as", "at", "by", "on",
    "in", "to", "be", "have", "has", "had", "not", "no", "yes", "if",
    "then", "than", "so", "just", "now", "also", "some", "any", "all",
}

# Ye shabd Hinglish sentences mein bahut common hain — inhe dekh ke
# lagta hai ki text Hinglish hai (voice = Hindi chahiye)
_HINGLISH_MARKERS = {
    "hai", "hain", "karo", "karo", "kar", "kya", "kyu", "kyun", "bhai",
    "mujhe", "mera", "meri", "kholo", "khol", "batao", "dikhao", "chalo",
    "chalao", "bhejo", "banao", "likho", "padho", "suno", "dekho", "dekho",
    "nahi", "nahin", "haan", "acha", "accha", "theek", "jaldi", "abhi",
    "aaj", "kal", "matlab", "samjha", "bata", "de", "do", "lena", "dena",
    "chahiye", "raha", "rahi", "rahe", "wala", "wali", "wale", "se",
    "ko", "ki", "ka", "ke", "mein", "me", "par", "pe", "bhi", "toh",
    "so", "yaar", "bhaiya", "didi", "bas", "sab", "kuch", "zyada",
}


def detect_script(text: str) -> str:
    """
    Text kis script mein hai?

    Returns: "devanagari" | "latin"

    >>> detect_script("नमस्ते भाई")
    'devanagari'
    >>> detect_script("bhai kholo")
    'latin'
    """
    if not text:
        return "latin"
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "latin"
    devanagari = sum(1 for ch in letters if _DEVANAGARI.match(ch))
    return "devanagari" if devanagari > len(letters) * 0.3 else "latin"


def looks_like_hinglish(text: str) -> bool:
    """
    Latin text hai, par Hinglish bolne ka style hai?

    Dono side ke markers ginte hain: Hinglish markers zyada hain to
    Hinglish maan lo. Pure English sentence mein ye markers kam aate hain.

    >>> looks_like_hinglish("bhai paytm kholo")
    True
    >>> looks_like_hinglish("what is the weather today")
    False
    """
    if not text:
        return False

    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return False

    hinglish_hits = sum(1 for w in words if w in _HINGLISH_MARKERS)
    english_hits = sum(1 for w in words if w in _ENGLISH_STOPWORDS)

    # Hinglish marker kisi bhi 3 words mein se 1 ho to kaafi hai
    return hinglish_hits >= max(1, len(words) // 3) and hinglish_hits >= english_hits * 0.6


def pick_voice_kind(text: str) -> str:
    """
    Is text ke liye kaunsi voice? "hi" ya "en".

    Devanagari dikhi -> Hindi. Latin hai par Hinglish lagti hai -> Hindi.
    Warna English (en-GB-RyanNeural — Jarvis voice).

    >>> pick_voice_kind("bhai paytm kholo")
    'hi'
    >>> pick_voice_kind("open the browser please")
    'en'
    """
    if not text:
        return "en"
    if detect_script(text) == "devanagari":
        return "hi"
    return "hi" if looks_like_hinglish(text) else "en"


# ======================================================================
#  2. Hindi numbers — Indian system (hazaar / lakh / crore)
# ======================================================================

_ONES = [
    "shunya", "ek", "do", "teen", "char", "paanch", "chhah", "saat",
    "aath", "nau", "das", "gyarah", "barah", "terah", "chaudah",
    "pandrah", "solah", "satrah", "atharah", "unnees", "bees",
]

# 21-99 — Hindi ka apna pattern hai (ekkais, baais... nabbe, ikyaanve)
_TENS = {
    20: "bees", 21: "ekkais", 22: "baais", 23: "teiaais", 24: "chaubees",
    25: "pachchees", 26: "chhabbees", 27: "sattaais", 28: "atthaais",
    29: "unattees", 30: "tees", 31: "ittees", 32: "battees", 33: "tentees",
    34: "chauntees", 35: "paintees", 36: "chhattees", 37: "santees",
    38: "adhtees", 39: "untalees", 40: "chaalees", 41: "iktalees",
    42: "bayaalees", 43: "taintaalees", 44: "chavaalees", 45: "paintaalees",
    46: "chhiyaalees", 47: "saintaalees", 48: "adhtaalees", 49: "unchaas",
    50: "pachaas", 51: "ikyaavan", 52: "baavan", 53: "tirpan",
    54: "chauvan", 55: "pachpan", 56: "chhappan", 57: "sattaavan",
    58: "atthaavan", 59: "unsath", 60: "saath", 61: "ikyaasath",
    62: "baasath", 63: "tiresath", 64: "chaunsath", 65: "painsath",
    66: "chhiyaasath", 67: "sadsath", 68: "adsath", 69: "unahattar",
    70: "sattar", 71: "iyahattar", 72: "bahattar", 73: "tihattar",
    74: "chauhattar", 75: "pachahattar", 76: "chhiyahattar",
    77: "sattahattar", 78: "athahattar", 79: "unaasi", 80: "assi",
    81: "ikyaasi", 82: "baraasi", 83: "tiraasi", 84: "chauraasi",
    85: "pachaasi", 86: "chhiyaasi", 87: "sattaasi", 88: "atthaasi",
    89: "navaasi", 90: "nabbe", 91: "ikyaanve", 92: "baanve",
    93: "tiraanve", 94: "churaanve", 95: "paintaaneve", 96: "chhiyaanve",
    97: "sattaanve", 98: "atthaanve", 99: "ninyaanve",
}


def number_to_hindi(n: int) -> str:
    """
    Number -> Hindi words (roman mein), INDIAN system.

    >>> number_to_hindi(2500)
    'do hazaar paanch sau'
    >>> number_to_hindi(150000)
    'ek lakh pachaas hazaar'
    """
    if n < 0:
        return "minus " + number_to_hindi(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n]

    # Indian system: crore(10^7), lakh(10^5), hazaar(10^3), sau(10^2)
    crore, rest = divmod(n, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    hazaar, rest = divmod(rest, 1000)
    sau, last = divmod(rest, 100)

    parts: list[str] = []
    if crore:
        parts.append(number_to_hindi(crore) + " crore")
    if lakh:
        parts.append(number_to_hindi(lakh) + " lakh")
    if hazaar:
        parts.append(number_to_hindi(hazaar) + " hazaar")
    if sau:
        parts.append(number_to_hindi(sau) + " sau")
    if last:
        parts.append(number_to_hindi(last))
    return " ".join(parts)


def number_to_hindi_translated(n: int) -> str:
    """number_to_hindi ka Devanagari version (translit pipeline se)."""
    return roman_word_to_devanagari_slow(number_to_hindi(n))


# Time aur decimal ke patterns
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_DECIMAL_RE = re.compile(r"\b(\d+)\.(\d+)\b")
_NUMBER_RE = re.compile(r"\b\d{1,12}\b")


def digits_to_hindi_words(text: str) -> str:
    """
    Text ke numbers ko Hindi words banao (bolne ke liye).

    Sirf Hindi voice ke liye — English voice numbers khud padh leti hai.

    >>> digits_to_hindi_words("2500 ka bill")
    'do hazaar paanch sau ka bill'
    >>> digits_to_hindi_words("8:30 baje")
    'aath bajke tees baje'
    """
    if not text:
        return text

    # Time: 8:30 -> aath bajke tees
    def _time(match: re.Match) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{number_to_hindi(hour)} bajke {number_to_hindi(minute)}"
        return match.group(0)

    text = _TIME_RE.sub(_time, text)

    # Decimal: 3.5 -> teen point paanch
    def _decimal(match: re.Match) -> str:
        whole, frac = match.group(1), match.group(2)
        return (
            f"{number_to_hindi(int(whole))} point "
            f"{' '.join(_ONES[int(d)] if d != '0' else 'shunya' for d in frac)}"
        )

    text = _DECIMAL_RE.sub(_decimal, text)

    # Plain numbers
    def _plain(match: re.Match) -> str:
        return number_to_hindi(int(match.group(0)))

    return _NUMBER_RE.sub(_plain, text)


# ======================================================================
#  3. Roman -> Devanagari
# ======================================================================

# ----------------------------------------------------------------------
#  Dictionary — sabse common Hinglish shabd. Yahi asli kaam karte hain.
#  Format: roman (lowercase) -> Devanagari
# ----------------------------------------------------------------------
HINDI_WORDS: dict[str, str] = {
    # --- Pronouns / question words ---
    "mai": "मैं", "main": "मैं", "mein": "में", "me": "में", "muje": "मुझे",
    "mujhe": "मुझे", "tu": "तू", "tum": "तुम", "tumhe": "तुम्हें",
    "tumhari": "तुम्हारी", "aap": "आप", "hum": "हम", "hamein": "हमें",
    "ye": "ये", "yeh": "ये", "wo": "वो", "woh": "वो", "vo": "वो", "us": "उस",
    "is": "इस", "iska": "इसका", "uska": "उसका", "uski": "उसकी", "iska": "इसका",
    "mera": "मेरा", "meri": "मेरी", "mere": "मेरे", "tera": "तेरा",
    "apna": "अपना", "apni": "अपनी", "khud": "खुद", "yahan": "यहां",
    "wahan": "वहां", "idhar": "इधर", "udhar": "उधर", "kya": "क्या",
    "kyu": "क्यूं", "kyun": "क्यूं", "kyunki": "क्योंकि", "kab": "कब",
    "kahan": "कहां", "kaise": "कैसे", "kitna": "कितना", "kitne": "कितने",
    "kaun": "कौन", "kis": "किस", "kisi": "किसी", "koi": "कोई",

    # --- Common verbs ---
    "hai": "है", "hain": "हैं", "tha": "था", "thi": "थी", "the": "थे",
    "hoga": "होगा", "hogi": "होगी", "honge": "होंगे", "ho": "हो",
    "hun": "हूं", "hu": "हूं",
    # postpositions — Hinglish mein sabse zyada aane wale shabd
    "ka": "का", "ke": "के", "ki": "की", "ko": "को", "se": "से",
    "par": "पर", "pe": "पे", "tak": "तक",
    "kar": "कर", "karo": "करो", "karna": "करना",
    "karke": "करके", "karta": "करता", "karti": "करती", "karte": "करते",
    "kiya": "किया", "ki": "की", "khol": "खोल", "kholo": "खोलो",
    "kholna": "खोलना", "kholke": "खोलके", "band": "बंद", "bhej": "भेज",
    "bhejo": "भेजो", "bhejna": "भेजना", "bhejke": "भेजके", "bata": "बता",
    "batao": "बताओ", "batana": "बताना", "dikha": "दिखा", "dikhao": "दिखाओ",
    "suna": "सुना", "suno": "सुनो", "sun": "सुन", "dekh": "देख",
    "dekho": "देखो", "dekhna": "देखना", "dekhke": "देखके", "chal": "चल",
    "chalo": "चलो", "chalna": "चलना", "chalega": "चलेगा", "aao": "आओ",
    "aa": "आ", "aana": "आना", "aya": "आया", "aayi": "आई", "aye": "आए",
    "jao": "जाओ", "ja": "जा", "jana": "जाना", "gaya": "गया", "gayi": "गई",
    "ruk": "रुक", "ruko": "रुको", "rukna": "रुकना", "de": "दे", "do": "दो",
    "dena": "देना", "diya": "दिया", "le": "ले", "lo": "लो", "lena": "लेना",
    "liya": "लिया", "lao": "लाओ", "la": "ला", "lana": "लाना", "bol": "बोल",
    "bolo": "बोलो", "bolna": "बोलना", "bola": "बोला", "likh": "लिख",
    "likho": "लिखो", "likhna": "लिखना", "padh": "पढ़", "padho": "पढ़ो",
    "padhna": "पढ़ना", "seekh": "सीख", "seekho": "सीखो", "bana": "बना",
    "banao": "बनाओ", "banana": "बनाना", "banado": "बना दो", "badha": "बढ़ा",
    "badhao": "बढ़ाओ", "rakh": "रख", "rakho": "रखो", "rakhna": "रखना",
    "laga": "लगा", "lagao": "लगाओ", "lagta": "लगता", "lagi": "लगी",
    "chalao": "चलाओ", "chala": "चला", "bhar": "भर", "bharo": "भरो",
    "bharna": "भरना", "bharo": "भरो", "dhoondh": "ढूंढ", "dhundo": "ढूंढो",
    "dhoondo": "ढूंढो", "dhoondna": "ढूंढना", "utha": "उठा", "uthao": "उठाओ",
    "bulao": "बुलाओ", "bhej": "भेज", "maaf": "माफ", "mil": "मिल",
    "mila": "मिला", "mila": "मिला", "milega": "मिलेगा", "mili": "मिली",
    "chahiye": "चाहिए", "chahta": "चाहता", "chahti": "चाहती", "sakta": "सकता",
    "sakte": "सकते", "sakti": "सकती", "shuru": "शुरु", "shuru": "शुरु",
    "khatam": "खत्म", "khtm": "खत्म", "nikal": "निकल", "nikalo": "निकालो",
    "batao": "बताओ", "bhejdo": "भेज दो", "kholdo": "खोल दो",
    "dedo": "दे दो", "dondo": "दो दो", "pakdo": "पकड़ो", "pakad": "पकड़",
    "kaam": "काम", "kam": "कम", "khatm": "खत्म", "hatado": "हटा दो",
    "hatao": "हटाओ", "hata": "हटा", "badlo": "बदलो", "badal": "बदल",
    "badlo": "बदलो", "change": "बदलो", "try": "ट्राई", "help": "मदद",
    "madad": "मदद", "batao": "बताओ", "sunao": "सुनाओ", "dikha": "दिखा",
    "chalu": "चालू", "chaloo": "चालू", "on": "चालू", "off": "बंद",
    "bandkaro": "बंद करो", "rok": "रोक", "roko": "रोको", "tok": "टोक",

    # --- Time ---
    "abhi": "अभी", "ab": "अब", "phir": "फिर", "fir": "फिर", "phirse": "फिर से",
    "jab": "जब", "tab": "तब", "pehle": "पहले", "baad": "बाद", "baadme": "बाद में",
    "aaj": "आज", "kal": "कल", "parso": "परसों", "subah": "सुबह",
    "shaam": "शाम", "raat": "रात", "din": "दिन", "hafte": "हफ्ते",
    "mahine": "महीने", "saal": "साल", "ghanta": "घंटा", "ghante": "घंटे",
    "minute": "मिनट", "second": "सेकंड", "baje": "बजे", "bajke": "बजके",
    "savera": "सवेरा", "dopahar": "दोपहर",
    "roz": "रोज", "roja": "रोज", "daily": "रोज",

    # --- Numbers / quantity ---
    "ek": "एक", "do": "दो", "teen": "तीन", "char": "चार", "chaar": "चार",
    "paanch": "पांच", "panch": "पांच", "chhah": "छह", "cheh": "छह",
    "saat": "सात", "aath": "आठ", "nau": "नौ", "das": "दस", "bis": "बीस",
    "sau": "सौ", "hazaar": "हज़ार", "hazar": "हज़ार", "lakh": "लाख",
    "crore": "करोड़", "rupay": "रुपये", "rupaye": "रुपये", "rupees": "रुपये",
    "rs": "रुपये", "paisa": "पैसा", "paise": "पैसे", "sab": "सब",
    "kuch": "कुछ", "bahut": "बहुत", "bohot": "बहुत", "thoda": "थोड़ा",
    "zyada": "ज़्यादा", "zara": "ज़रा", "thori": "थोड़ी", "pura": "पूरा",
    "puri": "पूरी", "pure": "पूरे", "adha": "आधा", "sade": "साढ़े",
    "dedh": "डेढ़", "dhai": "ढाई", "sirf": "सिर्फ", "har": "हर",
    "sabse": "सबसे", "sabko": "सबको",

    # --- People / relations ---
    "bhai": "भाई", "bhaiya": "भैया", "behen": "बहन", "mummy": "मम्मी",
    "papa": "पापा", "papa": "पापा", "maa": "मां", "ma": "मां",
    "ammi": "अम्मी", "abbu": "अब्बू", "dada": "दादा", "dadi": "दादी",
    "nana": "नाना", "nani": "नानी", "didi": "दीदी", "beta": "बेटा",
    "beti": "बेटी", "dost": "दोस्त", "yaar": "यार", "boss": "बॉस",
    "sir": "सर", "madam": "मैडम", "log": "लोग", "aadmi": "आदमी",
    "insaan": "इंसान", "bachche": "बच्चे", "baccha": "बच्चा",

    # --- Adjectives / adverbs ---
    "haan": "हां", "ha": "हां", "haanji": "हां जी", "nahi": "नहीं",
    "nahin": "नहीं", "na": "ना", "nah": "नह", "ji": "जी", "ok": "ओके",
    "okay": "ओके", "acha": "अच्छा", "accha": "अच्छा", "achha": "अच्छा",
    "achhi": "अच्छी", "acche": "अच्छे", "bura": "बुरा", "buri": "बुरी",
    "bada": "बड़ा", "badi": "बड़ी", "chhota": "छोटा", "chhoti": "छोटी",
    "jaldi": "जल्दी", "dheere": "धीरे", "tez": "तेज", "zor": "ज़ोर",
    "zaroor": "ज़रूर", "zaruri": "ज़रूरी", "bas": "बस", "bhi": "भी",
    "to": "तो", "toh": "तो", "aur": "और", "ya": "या", "lekin": "लेकिन",
    "magar": "मगर", "isliye": "इसलिए", "matlab": "मतलब", "bilkul": "बिल्कुल",
    "pakka": "पक्का", "sach": "सच", "jhooth": "झूठ", "theek": "ठीक",
    "thik": "ठीक", "sahi": "सही", "galat": "गलत", "naya": "नया",
    "nayi": "नई", "purana": "पुराना", "wapas": "वापस", "dobara": "दोबारा",
    "aage": "आगे", "peeche": "पीछे", "upar": "ऊपर", "neeche": "नीचे",
    "andar": "अंदर", "bahar": "बाहर", "saath": "साथ", "bina": "बिना",
    "khali": "खाली", "bhara": "भरा", "chup": "चुप", "shanti": "शांति",
    "asaan": "आसान", "mushkil": "मुश्किल", "aasan": "आसान", "kathin": "कठिन",
    "hara": "हरा", "laal": "लाल", "neela": "नीला", "kala": "काला",
    "safed": "सफेद", "peela": "पीला",

    # --- Daily life nouns ---
    "khana": "खाना", "khaana": "खाना", "pani": "पानी", "paani": "पानी",
    "chai": "चाय", "coffee": "कॉफी", "doodh": "दूध", "nashta": "नाश्ता",
    "ghar": "घर", "school": "स्कूल", "college": "कॉलेज", "office": "ऑफिस",
    "dukaan": "दुकान", "bazaar": "बाज़ार", "sadak": "सड़क",
    "gaadi": "गाड़ी", "gadi": "गाड़ी", "car": "कार", "bus": "बस",
    "train": "ट्रेन", "flight": "फ्लाइट", "bill": "बिल", "bank": "बैंक",
    "account": "अकाउंट", "paisa": "पैसा", "bazaar": "बाज़ार",
    "bijli": "बिजली", "paani": "पानी", "gas": "गैस", "kiraya": "किराया",
    "naam": "नाम", "number": "नंबर", "photo": "फोटो", "tasveer": "तस्वीर",
    "gaana": "गाना", "gana": "गाना", "song": "गाना", "movie": "मूवी",
    "film": "फिल्म", "khel": "खेल", "game": "गेम", "khabar": "खबर",
    "news": "खबर", "mausam": "मौसम", "weather": "मौसम", "garmi": "गर्मी",
    "sardi": "सर्दी", "baarish": "बारिश", "barish": "बारिश", "kaam": "काम",
    "kaam": "काम", "nishchit": "निश्चित", "jarurat": "ज़रूरत",
    "zaroorat": "ज़रूरत", "madad": "मदद", "dua": "दुआ", "khush": "खुश",
    "pareshan": "परेशान", "thak": "थक", "thaka": "थका", "neend": "नींद",

    # --- Greetings / interjections ---
    "namaste": "नमस्ते", "namaskar": "नमस्कार", "salaam": "सलाम",
    "salam": "सलाम", "shukriya": "शुक्रिया", "dhanyavad": "धन्यवाद",
    "thanks": "शुक्रिया", "sorry": "माफ़ कीजिए", "are": "अरे",
    "arre": "अरे", "arey": "अरे", "oye": "ओए", "wah": "वाह",
    "kya baat": "क्या बात", "chalo": "चलो", "dheko": "देखो",
    "helo": "हैलो", "hello": "हैलो", "hi": "हाय", "bye": "बाय",
    "alvida": "अलविदा", "goodbye": "अलविदा", "good": "अच्छा",
    "great": "बढ़िया", "badhiya": "बढ़िया", "mast": "मस्त", "jhakas": "झकास",

    # --- Hinglish grammar glue ---
    "wala": "वाला", "wali": "वाली", "wale": "वाले", "raha": "रहा",
    "rahi": "रही", "rahe": "रहे", "liye": "लिए", "kiye": "किए",
    "hone": "होने", "hokar": "होकर", "waghera": "वगैरह", "adi": "आदि",
    "itna": "इतना", "itni": "इतनी", "jitna": "जितना", "tabhi": "तभी",
    "yahin": "यहीं", "wahin": "वहीं", "isi": "इसी", "usi": "उसी",
    "in": "इन", "un": "उन", "inka": "इनका", "unka": "उनका",
    "iski": "इसकी", "uski": "उसकी", "inhe": "इन्हें", "unhe": "उन्हें",
    "mujhko": "मुझको", "tujhko": "तुझको", "mujhse": "मुझसे",
    "tumse": "तुमसे", "apne": "अपने", "apni": "अपनी", "khudka": "खुदका",

    # --- Device / computer (jo Devanagari mein natural lagte hain) ---
    "screen": "स्क्रीन", "volume": "वॉल्यूम", "battery": "बैटरी",
    "wifi": "वाईफाई", "internet": "इंटरनेट", "network": "नेटवर्क",
    "brightness": "ब्राइटनेस", "screenshot": "स्क्रीनशॉट",
    "system": "सिस्टम", "computer": "कंप्यूटर", "laptop": "लैपटॉप",
    "mobile": "मोबाइल", "phone": "फ़ोन", "charge": "चार्ज",
    "password": "पासवर्ड", "folder": "फोल्डर", "setting": "सेटिंग",
    "settings": "सेटिंग्स", "update": "अपडेट", "install": "इंस्टॉल",
    "download": "डाउनलोड", "message": "मैसेज", "call": "कॉल",
    "notification": "नोटिफिकेशन", "reminder": "रिमाइंडर", "alarm": "अलार्म",
}

# Devanagari output mein ye shabd LATIN hi rehne do — brands / app names.
# hi-IN voice inko waise bhi theek padh leti hai.
KEEP_LATIN: set[str] = {
    "paytm", "google", "youtube", "whatsapp", "instagram", "facebook",
    "chrome", "phonepe", "gpay", "amazon", "flipkart", "netflix",
    "spotify", "telegram", "chatgpt", "gemini", "groq", "openrouter",
    "gmail", "map", "maps", "app", "apps", "excel", "word", "pdf",
    "powerpoint", "ppt", "vs", "code", "python", "java", "linux",
    "windows", "android", "adb", "url", "link", "web", "site",
    "youtube.com", "google.com", "com", "www", "http", "https",
    "ai", "llm", "api", "key", "token", "file", "files", "search",
    "google pay", "pay", "screenshot", "log", "login", "logout",
}

# Consonant -> Devanagari (inherent 'a' ke saath; cluster hote hi halant)
_CONSONANTS: dict[str, str] = {
    "kh": "ख", "gh": "घ", "ch": "च", "chh": "छ", "jh": "झ", "th": "थ",
    "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श", "kh": "ख",
    "k": "क", "g": "ग", "j": "ज", "t": "त", "d": "द", "n": "न",
    "p": "प", "b": "ब", "m": "म", "y": "य", "r": "र", "l": "ल",
    "v": "व", "w": "व", "s": "स", "h": "ह", "f": "फ", "z": "ज़",
    "q": "क", "x": "क्स", "c": "क", "g": "ग",
}

# Matras — vowel ke sign
_MATRAS: dict[str, str] = {
    "aa": "ा", "a": "", "i": "ि", "ee": "ी", "ii": "ी", "u": "ु",
    "oo": "ू", "uu": "ू", "e": "े", "ai": "ै", "o": "ो", "au": "ौ",
}

# Word-start independent vowels
_INDEPENDENT: dict[str, str] = {
    "a": "अ", "aa": "आ", "i": "इ", "ee": "ई", "u": "उ", "oo": "ऊ",
    "e": "ए", "ai": "ऐ", "o": "ओ", "au": "औ",
}

_UNRECOGNIZED = re.compile(r"[^a-zA-Z]")


def _transliterate_word_raw(word: str) -> str | None:
    """
    Rule-based transliteration (dict ke baad wali layer).

    Returns: Devanagari string, ya None (sure nahi — Latin rehne do).
    """
    w = word.lower()
    if not w or _UNRECOGNIZED.search(w):
        return None

    out: list[str] = []
    i = 0
    n = len(w)
    prev_was_consonant = False

    while i < n:
        matched = False

        # Try 3-char, 2-char, then 1-char matches
        for size in (3, 2, 1):
            piece = w[i : i + size]
            if len(piece) < size:
                continue

            if piece in _INDEPENDENT and not prev_was_consonant:
                out.append(_INDEPENDENT[piece])
                i += size
                matched = True
                prev_was_consonant = False
                break

            if piece in _CONSONANTS:
                out.append(_CONSONANTS[piece])
                i += size
                matched = True
                prev_was_consonant = True
                break

            if piece in _MATRAS and prev_was_consonant:
                out.append(_MATRAS[piece])
                i += size
                matched = True
                prev_was_consonant = False
                break
        else:
            return None  # unknown char — Latin rahne do

        if not matched:
            return None

    if not out:
        return None

    result = "".join(out)

    # Word ka aakhri inherent 'a' chhupa hua hai (schwa) — "kamala"
    # jaisa na lage, end ke 'अ' ko 'आ' bana do (gaya -> गया jaisa feel)
    if result.endswith("अ") and len(result) > 2:
        result = result[:-1] + "आ"

    return result


def transliterate_word(word: str) -> str:
    """
    Ek roman shabd -> Devanagari (ya wapas Latin, agar sure nahi).

    >>> transliterate_word("bhai")
    'भाई'
    >>> transliterate_word("paytm")
    'paytm'
    """
    core = word.strip()
    if not core:
        return word

    # Leading/trailing punctuation alag rakho — word dict mein pure shabd
    stripped = core.strip(".,!?;:()[]{}\"'")
    prefix = core[: len(core) - len(core.lstrip(".,!?;:()[]{}\"'"))]
    suffix = core[len(prefix) + len(stripped) :]

    if not stripped:
        return word

    lower = stripped.lower()

    # 1. Brands/tech — Latin hi rehne do
    if lower in KEEP_LATIN:
        return word

    # 2. Dictionary hit
    if lower in HINDI_WORDS:
        return prefix + HINDI_WORDS[lower] + suffix

    # 3. Rule-based — conservative: fail ho to Latin
    converted = _transliterate_word_raw(stripped)
    if converted:
        return prefix + converted + suffix

    return word


def roman_to_devanagari(text: str) -> str:
    """
    Pura roman Hinglish sentence -> mixed Devanagari.

    Jis shabd ka bharosa nahi, wo Latin hi rehta hai. Numbers pehle se
    words mein hone chahiye (digits_to_hindi_words pehle chalao).

    >>> roman_to_devanagari("bhai kholo")
    'भाई खोलो'
    """
    if not text or detect_script(text) == "devanagari":
        return text

    words = text.split(" ")
    converted = [transliterate_word(w) for w in words]
    return " ".join(converted)


# ======================================================================
#  4. Full pipeline — TTS se pehle ye chalta hai
# ======================================================================


def prepare_hinglish_speech(text: str) -> str:
    """
    Bolne se pehle Hinglish text ki taiyari (Hindi voice ke liye):

        1. numbers -> Hindi words  (2500 -> do hazaar paanch sau)
        2. roman -> Devanagari     (dict + conservative rules)

    Input pehle `prepare_text_for_speech()` se saaf hona chahiye
    (markdown/emoji wahin hat'te hain).

    >>> prepare_hinglish_speech("bhai, 2500 ka bill bhar do")
    'भाई, do hazaar paanch sau ka बिल भर दो'
    """
    if not text:
        return ""

    if detect_script(text) == "devanagari":
        return text  # already Hindi — kuch nahi karna

    # Devanagari wale words already ho to unhe chhedo mat
    with_numbers = digits_to_hindi_words(text)
    return roman_to_devanagari(with_numbers)


# ======================================================================
#  5. Sentence splitting — STREAMING TTS ke liye
# ======================================================================

# Strong sentence end — danda (।) bhi — Hindi text ka full stop.
# COMMA yahan NAHI hai: "bhai, suno" ko do tukdon mein kaatna galat hai.
# Comma sirf over-lambe sentences ki emergency split mein use hota hai.
_SENTENCE_END = re.compile(r"(?<=[।.!?])\s+|(?<=\n)")


def split_into_sentences(
    text: str,
    min_chars: int = 30,
    max_chars: int = 220,
) -> list[str]:
    """
    Text ko bolne layak sentences mein kaato.

    Streaming TTS ka dil: LLM ka pehla sentence aate hi bolna shuru —
    poore jawab ka intezaar nahi.

    Rules:
      - bahut chhote tukdon ko aage ke saath jod do (min_chars)
      - bahut lambe sentence ko comma pe tod do (max_chars)

    >>> split_into_sentences("Ho gaya. Ab kya karein? Kuch aur!")
    ['Ho gaya.', 'Ab kya karein?', 'Kuch aur!']
    """
    if not text:
        return []

    text = text.strip()
    if len(text) <= min_chars and len(text) <= max_chars:
        return [text] if text else []

    raw = [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]

    # Chhote tukdo ko aage jodo — "Ho gaya." akela bolna bura lagta hai.
    # Sirf PEECHHE wala tukda chhota ho to merge — warna sab kuch ek
    # hi blob ban jaata tha.
    merged: list[str] = []
    for piece in raw:
        if (
            merged
            and len(merged[-1]) < min_chars
            and len(merged[-1]) + 1 + len(piece) <= max_chars
        ):
            merged[-1] = merged[-1] + " " + piece
        else:
            merged.append(piece)

    # Ab bhi lambe hai to comma pe kaato
    final: list[str] = []
    for sentence in merged:
        while len(sentence) > max_chars and ", " in sentence:
            cut = sentence.rfind(", ", 0, max_chars)
            if cut == -1 or cut < max_chars * 0.4:
                break
            final.append(sentence[: cut + 1].strip())
            sentence = sentence[cut + 1 :].strip()
        if sentence:
            final.append(sentence)

    return final


@dataclass
class SentenceBuffer:
    """
    Token-stream se sentences nikalne wala buffer (PURE LOGIC).

    LLM token-by-token deta hai; ye jodta hai aur jaise hi sentence
    complete hota hai, nikal deta hai. Streaming TTS isko use karta hai.

    Use:
        buf = SentenceBuffer()
        buf.feed("Ho ")
        buf.feed("gaya. Ab ")
        buf.pop_ready()   # -> ['Ho gaya.']
        buf.feed("kya karein?")
        buf.pop_ready()   # -> ['Ab kya karein?']
        buf.flush()       # -> bache hue pieces
    """

    min_chars: int = 30
    max_chars: int = 220
    _pending: str = field(default="")

    # Sentence-end chars jo COMPLETE sentence batate hain (comma nahi!)
    _COMPLETE_END = tuple(".!?।")

    def feed(self, delta: str) -> list[str]:
        """Naya token do, ready sentences wapas lo."""
        if not delta:
            return []

        self._pending += delta
        return self.pop_ready()

    def pop_ready(self) -> list[str]:
        """Ab tak complete hue sentences nikalo (adhoora pending raho)."""
        if len(self._pending) < self.min_chars:
            return []

        tail = self._pending.rstrip()

        # Aakhri char sentence-end hai? To pura pending bhi complete hai
        # ("Ab kya karein?" — '?') — warna sirf pehle ke complete pieces.
        tail_complete = bool(tail) and tail[-1] in self._COMPLETE_END

        parts = [s for s in _SENTENCE_END.split(self._pending) if s and s.strip()]
        if not parts:
            return []

        if tail_complete:
            complete = [s.strip() for s in parts]
            self._pending = ""
            return complete

        complete = [s.strip() for s in parts[:-1]] if len(parts) > 1 else []

        # Pending ko last (adhoora) piece se rebuild karo
        if complete:
            consumed_len = self._pending.rfind(parts[-1])
            self._pending = self._pending[consumed_len:]
            return complete

        # Ek hi lamba piece hai aur max se bada — kaat do (force)
        if len(tail) > self.max_chars:
            forced = tail[: self.max_chars]
            cut = forced.rfind(" ")
            if cut > self.max_chars * 0.5:
                forced = forced[:cut]
            self._pending = self._pending[len(forced) :].lstrip()
            return [forced.strip()]

        return []

    def flush(self) -> str:
        """Bache hue pending ko nikalo (stream khatam hone pe)."""
        rest = self._pending.strip()
        self._pending = ""
        return rest

    def clear(self) -> None:
        """Sab phenk do (naya turn shuru)."""
        self._pending = ""

    @property
    def pending_len(self) -> int:
        return len(self._pending)
