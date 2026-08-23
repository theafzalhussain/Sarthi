"""
Hinglish Lexicon — SAARTHI ka PILLAR #1.

Yahi wo cheez hai jo Gemini/Siri nahi karte.

Research kehti hai: code-mixed queries pe global AI agents ka
task success 20-45% gir jaata hai, aur Indic code-switched speech pe
25-35% word error rate aata hai. 250 million+ log Hinglish bolte hain.

Ye file us gap ko bharti hai — hardcoded Indian knowledge ke saath,
jo koi bahar ka developer nahi likh sakta.
"""

from __future__ import annotations

import re

# ======================================================================
#  INDIAN APPS -> Android package names
#  Ye SAARTHI ka secret weapon hai. Silicon Valley ke agents ko
#  IRCTC ka naam bhi nahi pata.
# ======================================================================

INDIAN_APPS: dict[str, str] = {
    # --- Payments / UPI ---
    "paytm": "net.one97.paytm",
    "phonepe": "com.phonepe.app",
    "phone pe": "com.phonepe.app",
    "gpay": "com.google.android.apps.nbu.paisa.user",
    "google pay": "com.google.android.apps.nbu.paisa.user",
    "bhim": "in.org.npci.upiapp",
    "upi": "in.org.npci.upiapp",
    "cred": "com.dreamplug.androidapp",
    "mobikwik": "com.mobikwik_new",
    "freecharge": "com.freecharge.android",
    # --- Banks ---
    "yono": "com.sbi.lotusintouch",
    "sbi": "com.sbi.lotusintouch",
    "hdfc": "com.snapwork.hdfc",
    "icici": "com.csam.icici.bank.imobile",
    "imobile": "com.csam.icici.bank.imobile",
    "axis": "com.axis.mobile",
    "kotak": "com.msf.kbank.mobile",
    "bob": "com.bankofbaroda.mconnect",
    # --- Travel ---
    "irctc": "cris.org.in.prs.ima",
    "rail connect": "cris.org.in.prs.ima",
    "train": "cris.org.in.prs.ima",
    "makemytrip": "com.makemytrip",
    "mmt": "com.makemytrip",
    "goibibo": "com.goibibo",
    "redbus": "in.redbus.android",
    "ola": "com.olacabs.customer",
    "uber": "com.ubercab",
    "rapido": "com.rapido.passenger",
    "namma yatri": "in.juspay.nammayatri",
    # --- Food / Grocery ---
    "zomato": "com.application.zomato",
    "swiggy": "in.swiggy.android",
    "blinkit": "com.grofers.customerapp",
    "zepto": "com.zepto.consumerapp",
    "bigbasket": "com.bigbasket.mobileapp",
    "instamart": "in.swiggy.android",
    "dunzo": "com.dunzo.user",
    # --- Shopping ---
    "flipkart": "com.flipkart.android",
    "amazon": "in.amazon.mShop.android.shopping",
    "myntra": "com.myntra.android",
    "meesho": "com.meesho.supply",
    "ajio": "com.ril.ajio",
    "nykaa": "com.fsn.nykaa",
    # --- Telecom ---
    "myjio": "com.jio.myjio",
    "jio": "com.jio.myjio",
    "airtel": "com.myairtelapp",
    "vi": "com.mypoc.vodafone",
    "bsnl": "com.bsnl.selfcare",
    # --- Government ---
    "digilocker": "in.gov.digilocker",
    "umang": "in.gov.umang.negd.g2c",
    "mparivahan": "com.nic.mparivahan",
    "aadhaar": "in.gov.uidai.mAadhaarPlus",
    "maadhaar": "in.gov.uidai.mAadhaarPlus",
    "cowin": "in.gov.cowin.aarogyasetu",
    # --- Communication ---
    "whatsapp": "com.whatsapp",
    "wa": "com.whatsapp",
    "telegram": "org.telegram.messenger",
    "signal": "org.thoughtcrime.securesms",
    "gmail": "com.google.android.gm",
    "truecaller": "com.truecaller",
    # --- Social ---
    "instagram": "com.instagram.android",
    "insta": "com.instagram.android",
    "facebook": "com.facebook.katana",
    "fb": "com.facebook.katana",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "linkedin": "com.linkedin.android",
    "snapchat": "com.snapchat.android",
    "snap": "com.snapchat.android",
    "sharechat": "in.mohalla.sharechat",
    # --- Entertainment ---
    "youtube": "com.google.android.youtube",
    "yt": "com.google.android.youtube",
    "hotstar": "in.startv.hotstar",
    "jiocinema": "com.jio.media.ondemand",
    "netflix": "com.netflix.mediaclient",
    "prime": "com.amazon.avod.thirdpartyclient",
    "spotify": "com.spotify.music",
    "gaana": "com.gaana",
    "wynk": "com.bsbportal.music",
    # --- Finance / Investing ---
    "groww": "com.nextbillion.groww",
    "kite": "com.zerodha.kite3",
    "zerodha": "com.zerodha.kite3",
    "upstox": "in.upstox.pro",
    "paytm money": "com.paytmmoney",
    # --- Education ---
    "byjus": "com.byjus.thelearningapp",
    "unacademy": "com.unacademyapp",
    "vedantu": "com.vedantu.app",
    "physicswallah": "xyz.penpencil.physicswallah",
    "pw": "xyz.penpencil.physicswallah",
    # --- System ---
    "settings": "com.android.settings",
    "setting": "com.android.settings",
    "camera": "com.android.camera",
    "gallery": "com.google.android.apps.photos",
    "photos": "com.google.android.apps.photos",
    "chrome": "com.android.chrome",
    "browser": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "map": "com.google.android.apps.maps",
    "calculator": "com.google.android.calculator",
    "clock": "com.google.android.deskclock",
    "alarm": "com.google.android.deskclock",
    "calendar": "com.google.android.calendar",
    "contacts": "com.android.contacts",
    "phone": "com.android.dialer",
    "dialer": "com.android.dialer",
    "messages": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "playstore": "com.android.vending",
    "play store": "com.android.vending",
    "files": "com.google.android.apps.nbu.files",
    "drive": "com.google.android.apps.docs",
}


# ======================================================================
#  HINGLISH VERBS -> canonical action
#  Ek hi kaam ke 5-6 tareeke hote hain bolne ke. Sab map karo.
# ======================================================================

VERB_INTENTS: dict[str, list[str]] = {
    "open": [
        "khol", "kholo", "kholna", "open", "chalu kar", "chalao", "start kar",
        "shuru kar", "launch kar", "on kar", "nikaal", "la",
    ],
    "close": [
        "band kar", "bandh kar", "band karo", "close", "off kar", "hatao",
        "quit kar", "exit",
    ],
    "send": [
        "bhej", "bhejo", "bhej de", "bhej dena", "send", "forward kar",
        "daal de", "kar de",
    ],
    "type": [
        "type kar", "likh", "likho", "daal", "dalo", "enter kar", "bhar",
        "bharo", "fill kar",
    ],
    "search": [
        "dhoondh", "dhundo", "khoj", "search kar", "find kar", "pata kar",
        "dekh ke bata", "google kar",
    ],
    "read": [
        "padh", "padho", "read kar", "sunao", "bata", "batao", "dekh ke bata",
        "kya likha hai", "dekho", "dekh", "dekhna", "check kar", "check karo",
        "dikha", "dikhao", "status bata",
    ],
    "call": [
        "call kar", "phone kar", "lagao", "mila", "milao", "ring kar",
        "baat kara",
    ],
    "screenshot": [
        "screenshot le", "screenshot", "photo le", "screen capture",
        "screen ki photo",
    ],
    "scroll": [
        "scroll kar", "neeche jaa", "upar jaa", "neeche karo", "upar karo",
        "aage badho", "peeche jao",
    ],
    "tap": [
        "tap kar", "click kar", "dabao", "daba", "press kar", "touch kar",
        "select kar", "choose kar",
    ],
    "delete": [
        "delete kar", "hata", "hatao", "mita", "mitao", "remove kar",
        "uda de", "saaf kar", "clear kar",
    ],
    "pay": [
        "pay kar", "bhugtan kar", "paise bhej", "paisa bhej", "rupay bhej",
        "bill bhar", "recharge kar", "transfer kar", "payment kar",
    ],
    "install": ["install kar", "download kar", "utaar", "le aa"],
    "uninstall": ["uninstall kar", "nikaal de", "hata de app"],
    "remember": [
        "yaad rakh", "note kar", "likh le", "save kar", "yaad rakhna",
        "bhoolna mat",
    ],
    "forget": ["bhool ja", "bhula de", "hata de yaad se", "forget kar"],
    "repeat": [
        "phir se", "dobara", "wapas kar", "same kar", "wahi kar",
        "repeat kar", "jaise pichli baar",
    ],
    "teach": [
        "dikha", "dikhata hun", "dikha raha hun", "sikha", "sikhata hun",
        "dekh aur seekh", "yaad kar le", "record kar",
    ],
    "stop": ["ruk", "ruko", "stop", "band karo", "rehne do", "cancel kar"],
}


# ======================================================================
#  RISKY ACTIONS — inse pehle confirmation ZARURI hai
#  Ek galat LLM decision mehnga pad sakta hai.
# ======================================================================

RISKY_KEYWORDS: set[str] = {
    # Paise
    "paise", "paisa", "rupay", "rupees", "rs", "money", "amount",
    "pay", "payment", "bhugtan", "transfer", "send money", "upi",
    "recharge", "bill", "transaction", "wallet", "bank",
    "kharid", "buy", "order", "book", "purchase", "checkout",
    # Data loss
    "delete", "hata", "mita", "remove", "uninstall", "format",
    "reset", "clear", "erase", "wipe", "saaf",
    # Doosron ko contact
    "message bhej", "call kar", "sms bhej", "email bhej", "post kar",
    "share kar", "forward kar", "upload kar",
    # Security
    "password", "otp", "pin", "cvv", "aadhaar", "pan",
    # System
    "shutdown", "restart", "reboot", "factory",
}


# ======================================================================
#  HINDI NUMBERS -> digits
#  "do hazaar paanch sau" -> 2500
# ======================================================================

NUMBER_WORDS: dict[str, float] = {
    "shunya": 0, "zero": 0,
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4,
    "paanch": 5, "panch": 5, "chah": 6, "chhah": 6, "chhe": 6, "che": 6,
    "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "no": 9,
    "das": 10, "dus": 10,
    "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
    "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20,
    "pachees": 25, "tees": 30, "chalees": 40, "pachaas": 50, "pachas": 50,
    "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
}

# Multipliers
NUMBER_MULTIPLIERS: dict[str, int] = {
    "sau": 100,
    "hazaar": 1_000, "hazar": 1_000, "thousand": 1_000, "k": 1_000,
    "lakh": 100_000, "lac": 100_000,
    "crore": 10_000_000, "karod": 10_000_000,
}

# Indian fractions — ye bahut use hote hain
FRACTION_WORDS: dict[str, float] = {
    "aadha": 0.5, "adha": 0.5,
    "dhai": 2.5, "dhaai": 2.5,
    "sava": 1.25, "sawa": 1.25,
    "saadhe": 0.5,   # "saadhe teen" = 3.5 (modifier)
    "sadhe": 0.5,
    "paune": -0.25,  # "paune char" = 3.75 (modifier)
}


# ======================================================================
#  FILLER WORDS — inko hatane se LLM ko clarity milti hai
# ======================================================================

# Dhyan: "dekh"/"dekho" YAHAN NAHI hain — wo asli verb ho sakte hain
# ("screen dekho"). Unko VERB_INTENTS["read"] handle karta hai.
FILLER_WORDS: set[str] = {
    "bhai", "yaar", "bro", "dude", "beta", "arre", "are", "abe",
    "please", "plz", "pls", "zara", "thoda", "jaldi", "achha", "acha",
    "theek hai", "thik hai", "ok", "okay", "haan", "han", "ji",
    "sun", "suno", "matlab", "basically", "actually",
    "ek kaam kar", "ek kaam karo", "kar dena", "na",
}


# ======================================================================
#  TIME EXPRESSIONS
# ======================================================================

TIME_WORDS: dict[str, str] = {
    "abhi": "now",
    "turant": "immediately",
    "aaj": "today",
    "kal": "tomorrow_or_yesterday",  # context se decide hoga
    "parso": "day_after_or_before",
    "subah": "morning",
    "dopahar": "afternoon",
    "shaam": "evening",
    "raat": "night",
    "baad mein": "later",
    "roz": "daily",
    "hafte": "weekly",
    "mahine": "monthly",
}


# ======================================================================
#  DEVICE REFERENCES — user kis device ki baat kar raha hai
# ======================================================================

DEVICE_WORDS: dict[str, str] = {
    "phone": "android", "mobile": "android", "fon": "android",
    "android": "android", "handset": "android",
    "laptop": "desktop", "computer": "desktop", "pc": "desktop",
    "system": "desktop", "machine": "desktop", "desktop": "desktop",
    "browser": "browser", "chrome": "browser", "website": "browser",
    "internet": "browser", "web": "browser",
}


# ======================================================================
#  Lookup helpers
# ======================================================================


def resolve_app(name: str) -> str | None:
    """
    App ka naam -> Android package name.

    >>> resolve_app("paytm")
    'net.one97.paytm'
    >>> resolve_app("Phone Pe")
    'com.phonepe.app'
    """
    if not name:
        return None
    key = name.strip().lower()
    if key in INDIAN_APPS:
        return INDIAN_APPS[key]
    # Space hata ke try karo: "phone pe" -> "phonepe"
    compact = key.replace(" ", "")
    for app_name, package in INDIAN_APPS.items():
        if app_name.replace(" ", "") == compact:
            return package
    return None


# App names jo device words se takraate hain.
# "mere phone me" = device, par "phone khol" = dialer app.
# Inko possessive ke baad app nahi maana jaayega.
AMBIGUOUS_APP_NAMES: set[str] = {
    "phone", "mobile", "browser", "chrome", "system", "x", "map",
}

# Possessive / demonstrative words — inke baad device ki baat hoti hai
POSSESSIVES: set[str] = {
    "mere", "mera", "meri", "apne", "apna", "apni",
    "is", "us", "iss", "uss", "isi", "usi",
    "my", "this", "that", "the",
}


def find_app_mentions(text: str) -> list[tuple[str, str]]:
    """
    Text mein kaunse apps mention hue.

    Word boundary use karta hai — isse "paytm" ke andar "yt" (youtube)
    ya "wahi" ke andar "wa" (whatsapp) galti se match nahi hote.

    Lambe naam pehle match hote hain, aur overlap block karte hain:
    "google pay" match hua to uske andar ka "pay" phir nahi matchega.

    Returns: [(app_name, package_name), ...]
    """
    lowered = text.lower()
    tokens = lowered.split()

    found: list[tuple[int, str, str]] = []  # (position, name, package)
    seen_packages: set[str] = set()
    consumed: list[tuple[int, int]] = []  # matched character spans

    def overlaps(start: int, end: int) -> bool:
        return any(start < c_end and end > c_start for c_start, c_end in consumed)

    # Lambe naam pehle ("google pay" before "pay")
    for app_name in sorted(INDIAN_APPS, key=len, reverse=True):
        package = INDIAN_APPS[app_name]
        if package in seen_packages:
            continue

        # \b = word boundary. Isse substring match nahi hota.
        pattern = rf"\b{re.escape(app_name)}\b"

        for match in re.finditer(pattern, lowered):
            start, end = match.span()

            # Lambe match ne ye jagah le li hai
            if overlaps(start, end):
                continue

            # Ambiguous naam: possessive ke baad ho to device hai, app nahi
            if app_name in AMBIGUOUS_APP_NAMES:
                before = lowered[:start].split()
                if before and before[-1] in POSSESSIVES:
                    continue

            found.append((start, app_name, package))
            seen_packages.add(package)
            consumed.append((start, end))
            break  # Ek app ek hi baar

    # Jis order mein text mein aaye, usi order mein return karo
    found.sort()
    return [(name, package) for _, name, package in found]


def detect_intent(text: str) -> str | None:
    """
    Hinglish text se main action pata karo.

    >>> detect_intent("bhai paytm khol do")
    'open'
    >>> detect_intent("bijli ka bill bhar de")
    'pay'
    """
    lowered = text.lower()

    # Lambe phrases pehle — zyada specific hote hain.
    # Word boundary se "pay" ko "paytm" ke andar match hone se rokte hain.
    matches: list[tuple[int, str]] = []
    for intent, phrases in VERB_INTENTS.items():
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                matches.append((len(phrase), intent))

    if not matches:
        return None

    # Sabse lamba (sabse specific) match jeetega
    matches.sort(key=lambda m: m[0], reverse=True)
    return matches[0][1]


def detect_target_device(text: str) -> str | None:
    """
    User kis device ki baat kar raha hai?

    >>> detect_target_device("mere phone pe whatsapp khol")
    'android'
    """
    lowered = text.lower()

    # Word boundary zaroori hai — warna "phonepe" ke andar ka "phone"
    # match ho jaayega aur galat device chun liya jaayega.
    for word, device in sorted(DEVICE_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return device
    return None


def is_risky(text: str) -> tuple[bool, list[str]]:
    """
    Ye command khatarnak hai? Confirmation chahiye?

    Returns: (risky?, kaunse words se laga)

    >>> is_risky("2000 rupay bhej do")
    (True, [...])
    """
    lowered = text.lower()

    # Word boundary — warna "paytm" ke andar ka "pay" risky flag kar dega,
    # jabki app kholna bilkul risky nahi hai.
    hits = [
        kw
        for kw in RISKY_KEYWORDS
        if re.search(rf"\b{re.escape(kw)}\b", lowered)
    ]
    return (len(hits) > 0, sorted(hits))
