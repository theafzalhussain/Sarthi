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

    # Gemini 2.0-flash band ho gaya (API khud 3.6-flash suggest karta hai)
    "gemini": "gemini-3.6-flash",

    # "openrouter/free" ek ROUTER hai — ye khud available free model
    # chun leta hai. Isliye jab koi ek free model delist hota hai to
    # ye TOOTTA NAHI. Specific model naam se behtar hai.
    "openrouter": "openrouter/free",
}


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


@dataclass
class ProviderConfig:
    """Ek LLM provider ki settings."""

    name: str
    api_key: str | None
    model: str
    supports_vision: bool = False

    @property
    def is_available(self) -> bool:
        """Key hai ya nahi — yahi decide karta hai use kar sakte hain ya nahi."""
        return bool(self.api_key and self.api_key.strip())


@dataclass
class Settings:
    """SAARTHI ki poori configuration."""

    # --- Providers ---
    providers: list[ProviderConfig] = field(default_factory=list)

    # --- Behaviour ---
    language: str = "hinglish"
    confirm_risky: bool = True
    max_steps: int = 12
    debug: bool = False

    # --- Devices ---
    adb_path: str = "adb"
    default_device: str = "desktop"

    # --- Paths ---
    data_dir: Path = DATA_DIR

    @classmethod
    def load(cls) -> "Settings":
        """Environment se settings banao."""
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
        ]

        settings = cls(
            providers=providers,
            language=os.getenv("SAARTHI_LANGUAGE", "hinglish").strip().lower(),
            confirm_risky=_env_bool("SAARTHI_CONFIRM_RISKY", True),
            max_steps=_env_int("SAARTHI_MAX_STEPS", 12),
            debug=_env_bool("SAARTHI_DEBUG", False),
            adb_path=os.getenv("ADB_PATH", "adb"),
            default_device=os.getenv("SAARTHI_DEFAULT_DEVICE", "desktop"),
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
            "  1. cp .env.example .env\n"
            "  2. Free key le:\n"
            "       GROQ    -> https://console.groq.com\n"
            "       GEMINI  -> https://aistudio.google.com/apikey\n"
            "  3. .env file mein paste kar de\n\n"
            "Dono free hain, credit card ki zarurat nahi."
        )


# Ek global instance — pura project isi ko use karega
settings = Settings.load()
