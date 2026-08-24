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
    "deepseek": "deepseek-ai/deepseek-v4-pro",

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
DEFAULT_PROVIDER_ORDER: list[str] = [
    "groq", "nvidia", "deepseek", "muse",
    "bluesminds", "openrouter", "gemini", "gemma",
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
    language: str = "hinglish"
    confirm_risky: bool = True
    max_steps: int = 12
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
            ),
            ProviderConfig(
                name="gemini",
                api_key=os.getenv("GEMINI_API_KEY"),
                model=os.getenv("GEMINI_MODEL", DEFAULT_MODELS["gemini"]),
                supports_vision=True,  # Screenshot dekh sakta hai
            ),
            ProviderConfig(
                name="openrouter",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                model=os.getenv(
                    "OPENROUTER_MODEL", DEFAULT_MODELS["openrouter"]
                ),
                supports_vision=False,
            ),
            ProviderConfig(
                name="nvidia",
                api_key=nvidia_key,
                model=os.getenv("NVIDIA_MODEL", DEFAULT_MODELS["nvidia"]),
                supports_vision=False,
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
                # Thinking OFF — warna reasoning ka pura chain reply mein
                # aa jaata hai. Free tier pe wo tokens barbaad hain, aur
                # user ko saaf jawab chahiye, model ki bakbak nahi.
                extra_body={"chat_template_kwargs": {"thinking": False}},
            ),
            ProviderConfig(
                name="muse",
                api_key=os.getenv("MUSE_API_KEY") or nvidia_key,
                model=os.getenv("MUSE_MODEL", DEFAULT_MODELS["muse"]),
                # Multimodal — screenshot dekh sakta hai
                supports_vision=_env_bool("MUSE_VISION", True),
                # Native tool calling
                supports_tools=_env_bool("MUSE_TOOLS", True),
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
            ),
            ProviderConfig(
                name="bluesminds",
                api_key=os.getenv("BLUESMINDS_API_KEY"),
                model=os.getenv("BLUESMINDS_MODEL", DEFAULT_MODELS["bluesminds"]),
                # GPT-4o vision support karta hai — ye Gemini ka backup
                # ban sakta hai screenshot dekhne mein
                supports_vision="4o" in os.getenv("BLUESMINDS_MODEL", DEFAULT_MODELS["bluesminds"]),
            ),
        ]

        # Provider order — .env se override ho sakta hai
        raw_order = os.getenv("SAARTHI_PROVIDER_ORDER", "").strip()
        if raw_order:
            order = [p.strip().lower() for p in raw_order.split(",") if p.strip()]
            # Jo provider order mein nahi likha, wo end mein daal do
            known = {p.name for p in providers}
            order = [p for p in order if p in known]
            order += [p for p in DEFAULT_PROVIDER_ORDER if p not in order]
        else:
            order = list(DEFAULT_PROVIDER_ORDER)

        settings = cls(
            providers=providers,
            provider_order=order,
            language=os.getenv("SAARTHI_LANGUAGE", "hinglish").strip().lower(),
            confirm_risky=_env_bool("SAARTHI_CONFIRM_RISKY", True),
            max_steps=_env_int("SAARTHI_MAX_STEPS", 12),
            debug=_env_bool("SAARTHI_DEBUG", False),
            adb_path=os.getenv("ADB_PATH", "adb"),
            default_device=os.getenv("SAARTHI_DEFAULT_DEVICE", "desktop"),
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
