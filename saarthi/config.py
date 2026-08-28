"""
SAARTHI — Configuration

Ek hi jagah se saari settings. .env file se padhta hai.
Koi key nahi hai to bhi crash nahi hoga — offline mode mein chalega.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv install nahi hua to bhi chalega
    pass


# ======================================================================
#  DEFAULT MODELS
#
#  DHYAN: Model naam BADALTE REHTE HAIN. Providers purane models band
#  kar dete hain. Jab "model_not_found" ya HTTP 404 aaye, matlab model
#  deprecate ho gaya hai — teri galti nahi hai.
#
#  Aisa ho to CLI mein chala:
#       /models
#  Wo teri API key se LIVE pata karega ki kaunse models available hain.
#  Phir .env mein naam update kar de.
#
#  Last updated: August 2026
# ======================================================================

DEFAULT_MODELS: dict[str, str] = {
    # Groq ne June 2026 mein llama-3.1-8b-instant aur
    # llama-3.3-70b-versatile deprecate kar diye. Ab gpt-oss family hai.
    "groq": "openai/gpt-oss-20b",

    # NVIDIA NIM — Nemotron 3 Ultra (550B total / 55B active).
    # Ye model LONG-RUNNING AGENTS ke liye banaya gaya hai, aur tool
    # calling support karta hai. SAARTHI ke liye bahut accha fit.
    # Free key: https://build.nvidia.com
    "nvidia": "nvidia/nemotron-3-ultra-550b-a55b",

    # Gemini 2.0-flash band ho gaya (API khud 3.6-flash suggest karta hai)
    "gemini": "gemini-3.6-flash",

    # "openrouter/free" ek ROUTER hai — ye khud available free model
    # chun leta hai. Isliye jab koi ek free model delist hota hai to
    # ye TOOTTA NAHI. Specific model naam se behtar hai.
    "openrouter": "openrouter/free",

    # Bluesminds — multi-model gateway. Ek key se GPT-5.6, GPT-4o,
    # GLM-5.2 sab chal jaate hain. Model select karna chahiye to
    # .env mein BLUESMINDS_MODEL set kar.
    "bluesminds": "gpt-4o",

    # OpenCode Zen — curated coding agent models. Laguna S 2.1 Free
    # (Stealth/Poolside) 256K context, 32K output. FREE, tool calling
    # support karta hai. Coding agents ke liye optimized.
    # Key: https://opencode.ai/zen -> API Keys
    "opencode": "laguna-s-2.1-free",

    # ------------------------------------------------------------------
    #  Neeche ke teeno bhi NVIDIA ke SAME endpoint pe chalte hain
    #  (integrate.api.nvidia.com) aur SAME NVIDIA_API_KEY use karte
    #  hain. Alag "provider" isliye banaye hain taaki:
    #    - ek model 404 de to agla automatic try ho
    #    - user SAARTHI_PROVIDER_ORDER se apna pasandeeda model
    #      pehle rakh sake
    #    - /models sabke liye alag se kaam kare
    # ------------------------------------------------------------------

    # DeepSeek V4 Pro — 1.6T total / 49B active MoE, 1M token context.
    # Reasoning + coding + AGENTIC kaam ke liye banaya gaya hai, tool
    # calling support karta hai. Sabse smart option.
    # NOTE: deepseek-v4-pro EOL 2026-08-07, ab -0813 version hai.
    "deepseek": "deepseek-ai/deepseek-v4-pro-0813",

    # Meta Muse Glimmer 30B — multimodal (text + IMAGE), NATIVE tool
    # calling, reasoning alag field mein aata hai. 131K context.
    # Ye SAARTHI ke liye khaas accha hai: screenshot DEKH sakta hai
    # AUR tools bhi chala sakta hai — Gemini ka behtar backup.
    "muse": "meta/muse-glimmer-30b",

    # Google DiffusionGemma 26B — block-diffusion model, 262K context,
    # text + image + video input.
    # DHYAN: ye diffusion model hai, iska tool calling bharosemand
    # nahi hai. Isliye default mein tools OFF hain (neeche dekh).
    "gemma": "google/diffusiongemma-26b-a4b-it",
}


# Kaunse providers NVIDIA ke endpoint + NVIDIA_API_KEY share karte hain
NVIDIA_HOSTED: tuple = ("nvidia", "deepseek", "muse", "gemma")


# ======================================================================
#  PROVIDER ORDER
#
#  Kis order mein try karna hai. Pehla = pehli choice, fail ho to agla.
#
#  Default sochke rakha hai:
#    groq       -> sabse TEZ (chhote kaam ke liye best)
#    nvidia     -> sabse SMART (Nemotron Ultra, agentic kaam ke liye)
#    openrouter -> backup
#    gemini     -> aankh (screenshot dekhne ke liye) — vision wala kaam
#                  isko automatically milta hai, order se farak nahi
#
#  Badalna hai? .env mein: SAARTHI_PROVIDER_ORDER=nvidia,groq,gemini
# ======================================================================

#  Naye models kahan fit hote hain:
#    deepseek -> nemotron ke baad. Sabse smart hai par bada/dheema hai.
#    muse     -> vision + tools dono, isliye gemini se PEHLE. Screenshot
#                wala kaam isko milega, aur ye tools bhi chala sakta hai
#                (Gemini se ek step bachta hai).
#    gemma    -> SABSE AAKHIR, kyunki tool calling bharosemand nahi hai.
#                Vision aur simple sawaal ke liye theek hai.
#
#  Dhyan: nvidia/deepseek/muse/gemma SAARE ek hi NVIDIA key pe chalte
#  hain. Isliye groq (alag key) pehle rakha hai — load bant jaata hai.
#  BEST PEHLE. Pehle groq (tez) pehle tha, par user ne bola "jo best
#  ho wo pehle rakho" — kyunki smart model ek hi prompt mein pura kaam
#  kar deta hai, jabki tez-par-kamzor model 3-4 baar galti karta hai.
#  Aakhir mein wahi dheema pad jaata hai.
# Jinke free tier mein TIGHT rate limit hai — ye PRIMARY nahi ban sakte.
#
# ⚠️ YE EK ASLI SABAK HAI, TASTE NAHI.
#
# Groq ko "sabse tez" dekh ke primary bana diya gaya tha (1.3s response).
# Par uske free tier mein 8000 TPM (tokens per minute) ka limit hai, aur
# hamara system prompt hi ~5000 token ka hai. Nateeja: 1-2 message ke baad
# HAR BAAR rate limit. Speed ka koi fayda nahi jab request hi fail ho.
#
# Ye dict isliye hai ki agla banda (ya AI) dobara wahi galti na kare.
# Test check karta hai ki inme se koi PEHLE na ho.
TIGHT_RATE_LIMIT_PROVIDERS: dict[str, str] = {
    "groq": "8000 TPM free tier — system prompt hi ~5000 token hai",
}


DEFAULT_PROVIDER_ORDER: list[str] = [
    "muse",        # FASTEST (0.6s) + vision + tools, no tight TPM limit
    "opencode",    # Laguna S 2.1 Free — 256K context, coding optimized
    "bluesminds",  # gateway (gpt-4o/gpt-5.6/glm) — fast + vision
    "nvidia",      # nemotron ultra — smart, agentic
    "groq",        # Very fast BUT 8000 TPM free limit (short queries only)
    "deepseek",    # 1.6T MoE, 1M context — SABSE SMART par slow (backup)
    "openrouter",  # free models ka router
    "gemini",      # aankh (screenshot)
    "gemma",       # SABSE AAKHIR — tool calling bharosemand nahi
]


# Project ka root folder (jahan ye repo hai)
ROOT_DIR = Path(__file__).resolve().parent.parent

# Data folder — memory DB, screenshots, skills sab yahan
DATA_DIR = ROOT_DIR / "data"


def _env_bool(key: str, default: bool = False) -> bool:
    """.env se true/false padho. '1', 'yes', 'true' sab chalega."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "haan"}


def _env_int(key: str, default: int) -> int:
    """.env se number padho. Galat value pe default use karo."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool_or_none(key: str):
    """
    .env se true/false padho, PAR set na ho to None.

    Tri-state chahiye hota hai: "true", "false", aur "user ne kuch
    bola hi nahi". Teesre case mein hum provider ko field bhejte hi
    nahi — uska apna default chalne dete hain.
    """
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return None
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "haan"}


def _env_float_or_none(key: str):
    """.env se decimal padho. Set na ho ya galat ho to None."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_int_or_none(key: str):
    """.env se number padho. Set na ho ya galat ho to None."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _provider_tuning(name: str, base_extra: dict | None = None) -> dict:
    """
    Ek provider ke generation settings .env se padho.

    Ye function isliye bana ki user ne apni .env mein ye likha tha:
        NVIDIA_ENABLE_THINKING=true
        NVIDIA_MAX_TOKENS=16384
        NVIDIA_TOP_P=0.95

    ...aur teeno KUCH NAHI KAR RAHE THE — code mein wo env vars hi
    nahi the. User ko lagta raha ki setting kaam kar rahi hai.

    Ab har provider ke liye ye chalte hain:
        {NAME}_MAX_TOKENS        jawab ki max length
        {NAME}_TOP_P             sampling
        {NAME}_ENABLE_THINKING   reasoning on/off

    Returns: {"max_tokens": ..., "top_p": ..., "extra_body": {...}}
    Jo set nahi hai wo None — provider apna default use karega.
    """
    prefix = name.upper()
    extra = dict(base_extra or {})

    thinking = _env_bool_or_none(f"{prefix}_ENABLE_THINKING")
    if thinking is not None:
        # NVIDIA NIM ka format. Nemotron/DeepSeek dono isi se
        # reasoning on/off karte hain.
        kwargs = dict(extra.get("chat_template_kwargs") or {})
        kwargs["thinking"] = thinking
        extra["chat_template_kwargs"] = kwargs

    return {
        "max_tokens": _env_int_or_none(f"{prefix}_MAX_TOKENS"),
        "top_p": _env_float_or_none(f"{prefix}_TOP_P"),
        "extra_body": extra,
    }


def _env_choice(key: str, allowed: tuple, default: str) -> str:
    """
    .env se ek fixed choice padho.

    Galat value likhi ho to CHUP-CHAAP default use karte hain — crash
    karna bekaar hai, aur galat value pe agent chalna band ho jaaye
    to wo user ke liye zyada bura hai.
    """
    raw = (os.getenv(key) or "").strip().lower()
    return raw if raw in allowed else default


@dataclass
class ProviderConfig:
    """Ek LLM provider ki settings."""

    name: str
    api_key: str | None
    model: str

    # Screenshot dekh sakta hai?
    supports_vision: bool = False

    # TOOL CALLING kar sakta hai?
    #
    # Ye SAARTHI ke liye sabse zaroori capability hai — agent ka pura
    # kaam tools se hota hai (app kholo, tap karo, search karo).
    # Jo model tools support nahi karta wo sirf baat kar sakta hai,
    # KAAM nahi kar sakta.
    #
    # Isliye Brain aise providers ko tool wale kaam ke liye SKIP kar
    # deta hai. Wo phir bhi kaam ke hain — vision aur simple sawaal
    # ke liye.
    supports_tools: bool = True

    # Provider-specific extra payload (NVIDIA ke reasoning models ko
    # `chat_template_kwargs` chahiye hota hai thinking on/off karne ke
    # liye). Khali dict = kuch extra nahi bhejna.
    extra_body: dict = field(default_factory=dict)

    # --- Generation tuning (.env se, per-provider) ---
    #
    # None = is provider ka apna default use karo.
    #
    # max_tokens KHAAS ZAROORI hai reasoning models ke liye: thinking
    # ON ho aur max_tokens chhota ho to jawab BEECH MEIN KAT jaata hai
    # (reasoning tokens budget kha jaate hain).
    max_tokens: int | None = None
    top_p: float | None = None

    @property
    def is_available(self) -> bool:
        """Key hai ya nahi — yahi decide karta hai use kar sakte hain ya nahi."""
        return bool(self.api_key and self.api_key.strip())


@dataclass
class Settings:
    """SAARTHI ki poori configuration."""

    # --- Providers ---
    providers: list[ProviderConfig] = field(default_factory=list)

    # Kis order mein providers try karne hain
    provider_order: list[str] = field(
        default_factory=lambda: list(DEFAULT_PROVIDER_ORDER)
    )

    # --- Behaviour ---
    #
    # "auto" = user ki bhasha copy karo (English mein pucho -> English
    # mein jawab, Hinglish mein pucho -> Hinglish mein jawab).
    # Interface hamesha English hai — wo professional lagta hai — par
    # BAAT user ki bhasha mein hoti hai.
    # Fix karna hai to "hinglish" ya "english" set kar de.
    language: str = "auto"
    confirm_risky: bool = True

    # Ek command ke liye max kitne steps.
    #
    # 12 se 25 kiya gaya. Wajah: "youtube pe gaana chala do" jaisa kaam
    # 6-8 steps leta hai (site kholo -> page padho -> video pe click ->
    # verify). 12 mein multi-part command ("gaana chala aur mausam bata")
    # beech mein atak jaati thi.
    max_steps: int = 25

    # Jawab ki max length (global default).
    #
    # 2048 se 4096 kiya. Wajah: reasoning models (deepseek v4,
    # nemotron) thinking ON hone pe reasoning tokens bhi isi budget se
    # khaate hain — 2048 mein jawab BEECH MEIN KAT jaata tha.
    # Per-provider override: NVIDIA_MAX_TOKENS, DEEPSEEK_MAX_TOKENS...
    max_tokens: int = 4096

    # --- Screenshot caching ---
    # Kitne screenshots ek turn mein LLM ko bhejne hain (bade image =
    # bahut tokens). Purane evict ho jaate hain, sirf latest N rehte.
    # 0 = vision band (sirf text bhejo)
    max_screenshots: int = 2

    # Same screenshot dobara aaye to bhejne se baho (hash match)
    screenshot_dedupe: bool = True

    # FULL ACCESS MODE — risky tools bina puche chalenge.
    #
    # DHYAN: isse HARD BLOCKS nahi hatte. OTP/PIN/password type karna
    # aur rm -rf / jaise commands PHIR BHI blocked rehte hain — wo
    # safety.py mein alag layer hai jise bypass nahi kiya ja sakta.
    #
    # Ye sirf "confirmation" wale kaam auto-approve karta hai
    # (shell command, skill chalana, memory delete).
    auto_approve: bool = False

    debug: bool = False

    # --- Devices ---
    adb_path: str = "adb"
    default_device: str = "desktop"

    # --- Browser ---
    #
    # Ye setting "mera tab switch ho gaya" wali problem ka ilaaj hai.
    #
    #   agent  -> SAARTHI apni ALAG browser window use karega (Playwright).
    #             Tere personal Chrome ke tabs ko haath bhi nahi lagega.
    #             Sabse safe. Login state agent ke apne profile mein
    #             save hoti hai (ek baar login karna padega).
    #
    #   system -> Tera default browser. Agent naye TAB mein kholega
    #             (tera current tab replace NAHI karega) aur window
    #             ko zabardasti aage laane ki koshish nahi karega.
    #             Par dhyan: Chrome khud naye tab pe switch kar deta hai —
    #             ye Chrome ka behaviour hai, isko code se roka nahi ja
    #             sakta. Tab switch bilkul nahi chahiye to 'agent' use kar.
    #
    #   auto   -> Playwright installed ho to 'agent', warna 'system'.
    #             DEFAULT — kyunki ye bina setup ke sahi kaam karta hai.
    browser_mode: str = "auto"

    # Agent ka browser dikhe ya nahi.
    # False = dikhega (default — user dekh sakta hai kya ho raha hai,
    #         aur zarurat pade to khud takeover kar sakta hai)
    # True  = background mein, koi window nahi khulegi
    browser_headless: bool = False

    # --- Paths ---
    data_dir: Path = DATA_DIR

    # User ne .env mein khud order likha hai? Aur usme kaunse providers
    # chhoot gaye? (Startup pe batana hai — warna naye models chup-chaap
    # aakhir mein chale jaate hain aur user ko pata bhi nahi chalta.)
    order_is_explicit: bool = False
    order_missing: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        """Environment se settings banao."""
        # NVIDIA ki ek key se 4 models chalte hain. NVIDIA_API_KEY
        # standard hai, par NVIDIA_NIM_API_KEY bhi kai jagah use hoti
        # hai — dono support kar lete hain.
        nvidia_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY")

        providers = [
            ProviderConfig(
                name="groq",
                api_key=os.getenv("GROQ_API_KEY"),
                model=os.getenv("GROQ_MODEL", DEFAULT_MODELS["groq"]),
                supports_vision=False,
                **_provider_tuning("groq"),
            ),
            ProviderConfig(
                name="gemini",
                api_key=os.getenv("GEMINI_API_KEY"),
                model=os.getenv("GEMINI_MODEL", DEFAULT_MODELS["gemini"]),
                supports_vision=True,  # Screenshot dekh sakta hai
                **_provider_tuning("gemini"),
            ),
            ProviderConfig(
                name="openrouter",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                model=os.getenv(
                    "OPENROUTER_MODEL", DEFAULT_MODELS["openrouter"]
                ),
                supports_vision=False,
                **_provider_tuning("openrouter"),
            ),
            ProviderConfig(
                name="nvidia",
                api_key=nvidia_key,
                model=os.getenv("NVIDIA_MODEL", DEFAULT_MODELS["nvidia"]),
                supports_vision=False,
                **_provider_tuning("nvidia"),
            ),
            # --- NVIDIA ke same endpoint pe teen aur models ---
            ProviderConfig(
                name="deepseek",
                # Apni alag key mil jaaye to DEEPSEEK_API_KEY set kar de,
                # warna NVIDIA wali hi chalegi
                api_key=os.getenv("DEEPSEEK_API_KEY") or nvidia_key,
                model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODELS["deepseek"]),
                supports_vision=False,
                supports_tools=_env_bool("DEEPSEEK_TOOLS", True),
                # Thinking default OFF — warna reasoning ka pura chain
                # reply mein aa jaata hai. Free tier pe wo tokens
                # barbaad hain, aur user ko saaf jawab chahiye.
                # DEEPSEEK_ENABLE_THINKING=true se on kar sakta hai.
                **_provider_tuning(
                    "deepseek", {"chat_template_kwargs": {"thinking": False}}
                ),
            ),
            ProviderConfig(
                name="muse",
                api_key=os.getenv("MUSE_API_KEY") or nvidia_key,
                model=os.getenv("MUSE_MODEL", DEFAULT_MODELS["muse"]),
                # Multimodal — screenshot dekh sakta hai
                supports_vision=_env_bool("MUSE_VISION", True),
                # Native tool calling
                supports_tools=_env_bool("MUSE_TOOLS", True),
                **_provider_tuning("muse"),
            ),
            ProviderConfig(
                name="gemma",
                api_key=os.getenv("GEMMA_API_KEY") or nvidia_key,
                model=os.getenv("GEMMA_MODEL", DEFAULT_MODELS["gemma"]),
                # Text + image + video input leta hai
                supports_vision=_env_bool("GEMMA_VISION", True),
                # DEFAULT OFF — diffusion model hai, tool calling verify
                # nahi hua. Tere paas chal jaaye to .env mein
                # GEMMA_TOOLS=true kar de.
                supports_tools=_env_bool("GEMMA_TOOLS", False),
                **_provider_tuning("gemma"),
            ),
            ProviderConfig(
                name="bluesminds",
                api_key=os.getenv("BLUESMINDS_API_KEY"),
                model=os.getenv("BLUESMINDS_MODEL", DEFAULT_MODELS["bluesminds"]),
                # GPT-4o vision support karta hai — ye Gemini ka backup
                # ban sakta hai screenshot dekhne mein
                supports_vision="4o" in os.getenv("BLUESMINDS_MODEL", DEFAULT_MODELS["bluesminds"]),
                **_provider_tuning("bluesminds"),
            ),
            # --- OpenCode Zen — coding agent models ---
            ProviderConfig(
                name="opencode",
                api_key=os.getenv("OPENCODE_API_KEY"),
                model=os.getenv("OPENCODE_MODEL", DEFAULT_MODELS["opencode"]),
                supports_vision=False,
                # Laguna S 2.1 tool calling support karta hai
                supports_tools=_env_bool("OPENCODE_TOOLS", True),
                **_provider_tuning("opencode"),
            ),
        ]

        # Provider order — .env se override ho sakta hai
        raw_order = os.getenv("SAARTHI_PROVIDER_ORDER", "").strip()
        order_is_explicit = bool(raw_order)
        order_missing: list[str] = []

        if raw_order:
            order = [p.strip().lower() for p in raw_order.split(",") if p.strip()]
            known = {p.name for p in providers}
            order = [p for p in order if p in known]

            # Jo provider user ne likha hi nahi, wo end mein daal do.
            #
            # Ye ek CHUP-CHAAP TRAP hai: user ne purana order likha tha
            # (jab 5 providers the), phir naye models add hue — wo
            # automatically SABSE AAKHIR chale gaye, chahe wo sabse
            # smart hon. Isliye startup pe batate hain.
            order_missing = [p for p in DEFAULT_PROVIDER_ORDER if p not in order]
            order += order_missing
        else:
            order = list(DEFAULT_PROVIDER_ORDER)

        settings = cls(
            providers=providers,
            provider_order=order,
            language=_env_choice(
                "SAARTHI_LANGUAGE", ("auto", "hinglish", "hindi", "english"), "auto"
            ),
            confirm_risky=_env_bool("SAARTHI_CONFIRM_RISKY", True),
            auto_approve=_env_bool("SAARTHI_AUTO_APPROVE", False),
            max_steps=_env_int("SAARTHI_MAX_STEPS", 25),
            max_tokens=_env_int("SAARTHI_MAX_TOKENS", 4096),
            max_screenshots=_env_int("SAARTHI_MAX_SCREENSHOTS", 2),
            screenshot_dedupe=_env_bool("SAARTHI_SCREENSHOT_DEDUPE", True),
            order_is_explicit=order_is_explicit,
            order_missing=order_missing,
            debug=_env_bool("SAARTHI_DEBUG", False),
            adb_path=os.getenv("ADB_PATH", "adb"),
            # Validation zaroori hai: user ne galti se
            # SAARTHI_DEFAULT_DEVICE=Realtek likh diya tha (wo mic ki
            # setting samajh ke). Bina validation wo chup-chaap accept
            # ho jaata tha aur ittefaq se desktop pe gir jaata tha.
            default_device=_env_choice(
                "SAARTHI_DEFAULT_DEVICE",
                ("desktop", "android", "browser"),
                "desktop",
            ),
            browser_mode=_env_choice(
                "SAARTHI_BROWSER_MODE", ("auto", "agent", "system"), "auto"
            ),
            browser_headless=_env_bool("SAARTHI_BROWSER_HEADLESS", False),
        )

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return settings

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @property
    def available_providers(self) -> list[ProviderConfig]:
        """Jinke paas key hai, sirf wahi."""
        return [p for p in self.providers if p.is_available]

    @property
    def has_any_provider(self) -> bool:
        """Koi bhi LLM use kar sakte hain?"""
        return len(self.available_providers) > 0

    def vision_provider(self) -> ProviderConfig | None:
        """Screenshot samajhne wala provider dhoondo (Gemini)."""
        for p in self.available_providers:
            if p.supports_vision:
                return p
        return None

    def setup_help(self) -> str:
        """Key nahi hai to user ko kya karna chahiye."""
        return (
            "Koi API key nahi mili bhai!\n\n"
            "  1. cp .env.example .env       (Windows: Copy-Item .env.example .env)\n"
            "  2. Kam se kam EK free key le:\n"
            "       NVIDIA  -> https://build.nvidia.com           (BEST DEAL —\n"
            "                  ek key se 4 models: nemotron, deepseek v4 pro,\n"
            "                  muse glimmer, diffusiongemma)\n"
            "       GROQ    -> https://console.groq.com           (sabse tez)\n"
            "       GEMINI  -> https://aistudio.google.com/apikey (screenshot ke liye)\n"
            "  3. .env file mein paste kar de\n\n"
            "Sab free hain, credit card ki zarurat nahi.\n"
            "Salah: NVIDIA + GROQ dono le le — alag-alag limits hain,\n"
            "ek khatam ho to doosra chalta rahega."
        )


# Ek global instance — pura project isi ko use karega
settings = Settings.load()
