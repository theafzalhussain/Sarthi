"""
Banking lockdown — agent ko paise wale apps se door rakhne ka switch.

KYUN YE BANA:

    User ne poocha: "mera agent bank ka access na le, UPI payment na kar
    sake, card details read na kare — aisa hai na?"

    Jawab NAHI tha. `safety.py` sirf TYPE karne pe rok lagata hai (OTP,
    PIN, CVV, password). App KHOLNE pe koi rok nahi thi. Agent Paytm,
    PhonePe, ICICI, Kotak — sab khol sakta tha aur navigate kar sakta
    tha.

    Ye jaan-boojh ke design tha ("agent screen tak le jaayega, final
    button user dabayega"), par har user ko wo tradeoff nahi chahiye.
    Kisi ko poora block chahiye.

DESIGN — ye ek SWITCH hai, default OFF. Kyun?

    Banking lock ON karne se "paytm kholo" aur "bijli ka bill bhar do"
    KAAM KARNA BAND kar denge. Ye SAARTHI ke sabse common use cases
    hain. Isliye default OFF hai aur user jaan-boojh ke ON karta hai.

    PAR redaction (redact.py) DEFAULT ON hai — kyunki wo feature nahi,
    bug fix hai. Card number cloud API pe bhejna kisi bhi mode mein
    theek nahi.

⚠️ IMAANDAAR LIMITATION — ye jaan lena zaroori hai:

    Ye layer app KHOLNE ko rokti hai. Agar user KHUD banking app khol
    ke agent ko screen padhne bole, to `screen_padho` chalega. Us case
    mein redaction bachati hai (card/OTP/account hat jaate hain), par
    balance jaisa text nikal sakta hai.

    Poora airtight isolation OS-level sandbox se hota hai, ek Python
    layer se nahi. Isliye jhooth nahi bolunga — ye "bahut behtar" hai,
    "100% guaranteed" nahi.
"""

from __future__ import annotations

import os
import re

# Paise wale apps — friendly naam -> package.
#
# Ye list `lang/lexicon.py` ke INDIAN_APPS se nikaali gayi hai. Yahan
# alag rakhi hai kyunki lexicon ka kaam PEHCHANNA hai, iska kaam ROKNA.
# Do alag chinta, do alag jagah.
BANKING_APPS: dict[str, str] = {
    "paytm": "net.one97.paytm",
    "paytm money": "com.paytmmoney",
    "phonepe": "com.phonepe.app",
    "phone pe": "com.phonepe.app",
    "gpay": "com.google.android.apps.nbu.paisa.user",
    "google pay": "com.google.android.apps.nbu.paisa.user",
    "bhim": "in.org.npci.upiapp",
    "upi": "in.org.npci.upiapp",
    "icici": "com.csam.icici.bank.imobile",
    "imobile": "com.csam.icici.bank.imobile",
    "hdfc": "com.snapwork.hdfc",
    "sbi": "com.sbi.lotusintouch",
    "yono": "com.sbi.lotusintouch",
    "axis": "com.axis.mobile",
    "kotak": "com.msf.kbank.mobile",
    "bob": "com.bankofbaroda.mconnect",
    "cred": "com.dreamplug.androidapp",
}


def banking_locked() -> bool:
    """
    Banking lock ON hai?

    DEFAULT OFF — kyunki ON karne se "paytm kholo" band ho jaata hai,
    jo core use case hai. User ka faisla hai.
    """
    raw = os.getenv("SAARTHI_BANKING_LOCK", "false").strip().lower()
    return raw in ("1", "true", "yes", "haan", "on")


def extra_blocked_apps() -> set[str]:
    """
    `SAARTHI_BLOCKED_APPS` se user ke apne blocked apps.

    Comma separated: SAARTHI_BLOCKED_APPS=whatsapp,gallery,tinder
    Banking lock se alag — ye hamesha lagta hai.
    """
    raw = os.getenv("SAARTHI_BLOCKED_APPS", "").strip()
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_banking_app(app: object) -> bool:
    """
    Ye banking/payment app hai?

    ⚠️ WORD BOUNDARY se match karte hain, SUBSTRING se NAHI.

    Ye BUG#1 ka sabak hai: substring matching se "paytm" ke andar ka
    "pay" match ho jaata tha, aur "wahi" ke andar "wa" se WhatsApp.
    Yahan wahi galti dohrane ka khatra hai — "sbi" substring "sbi_notes"
    mein hai, "upi" "upiwala" mein. Bina boundary ke ye layer galat
    apps block karne lagegi aur user ka bharosa jaayega.
    """
    if app is None:
        return False

    text = str(app).strip().lower()
    if not text:
        return False

    # Package name ka exact match (com.phonepe.app)
    if text in set(BANKING_APPS.values()):
        return True

    # --- Package name (com.xyz.abc) — SUBSTRING match, jaan-boojh ke ---
    #
    # Yahan word boundary NAHI use karte. Wajah:
    #
    #   "com.icicibank.imobile" mein "bank" ek alag shabd nahi hai —
    #   "icicibank" ek token hai. Word boundary se ye MISS ho jaata, aur
    #   agent bank app khol deta chahe lock ON ho.
    #
    # Ye SECURITY CONTROL hai, isliye FAIL-CLOSED hona chahiye:
    #   false positive = agent ek app nahi kholega (irritating, SAFE)
    #   false negative = agent bank app khol dega (SECURITY FAIL)
    #
    # Package names namespaced hote hain (com.company.app), isliye
    # substring ka risk free text se bahut kam hai.
    if "." in text:
        for keyword in ("bank", "upi", "npci", "paytm", "phonepe", "paisa",
                        "wallet", "payment", "finance"):
            if keyword in text:
                return True

    # --- Friendly naam — WORD BOUNDARY se ---
    #
    # Yahan boundary ZARURI hai. Ye BUG#1 ka sabak hai: substring se
    # "paytm" ke andar ka "pay" match hota tha aur "wahi" mein "wa" se
    # WhatsApp. User "paytm notes" jaisa kuch likhe to usse block karna
    # confusing hoga — friendly naam user khud type karta hai, wo precise
    # hota hai.
    for name in BANKING_APPS:
        if re.search(rf"\b{re.escape(name)}\b", text):
            return True

    return False


def check_app_allowed(app: object) -> tuple[bool, str]:
    """
    Ye app kholne ki ijaazat hai? Returns (allowed, wajah).

    Wajah user ko dikhayi jaati hai, isliye actionable honi chahiye —
    sirf "blocked" likhna bekaar hai, user ko pata hona chahiye kyun
    aur kaise badle.
    """
    if app is None:
        return True, ""

    text = str(app).strip().lower()
    if not text:
        return True, ""

    # User ka apna blocklist — word boundary se
    for blocked in extra_blocked_apps():
        if re.search(rf"\b{re.escape(blocked)}\b", text):
            return False, (
                f"'{app}' SAARTHI_BLOCKED_APPS mein hai — main ise nahi "
                f"kholunga. Hatana ho to .env se nikaal do."
            )

    if banking_locked() and is_banking_app(text):
        return False, (
            f"BANKING LOCK ON hai — '{app}' paise wala app hai, main ise "
            f"nahi kholunga. Tu khud khol le.\n"
            f"    Ye lock hatane ke liye .env mein: SAARTHI_BANKING_LOCK=false"
        )

    return True, ""


def screenshot_allowed(current_app: object) -> tuple[bool, str]:
    """
    Screenshot lena theek hai?

    Banking lock ON ho aur banking app SAAMNE ho to screenshot BLOCK.

    Kyun khaas taur pe screenshot: redaction TEXT pe lagti hai, IMAGE pe
    nahi lag sakti. Screenshot mein card number, balance, sab dikhta hai
    aur wo seedha vision-model ko chala jaata hai. Text redact karke
    image bhej dena bekaar hai.

    `current_app` pata na chale (None/khali) to ALLOW karte hain. Ye
    jaan-boojh ke hai: block karne se banking lock ON karte hi saare
    screenshot band ho jaate (browser, desktop bhi) aur agent bekaar ho
    jaata. Ye trade-off documented hai, chhupa nahi.
    """
    if not banking_locked():
        return True, ""

    if not current_app:
        return True, ""

    if is_banking_app(current_app):
        return False, (
            f"BANKING LOCK ON hai aur saamne '{current_app}' khula hai — "
            f"screenshot nahi lunga (image mein card/balance dikh jaata hai "
            f"aur redaction image pe nahi lag sakti).\n"
            f"    screen_padho use kar — usme sensitive data hat jaata hai."
        )

    return True, ""
