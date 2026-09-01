"""
Credential Store — website logins ka safe ghar.

KYUN CHAHIYE:
    User chahta hai ki agent uski taraf se websites pe login kare
    (Gmail, GitHub, koi bhi site). Iske liye email/username aur
    password kahin store karne padenge — warna har baar user ko
    daalna padega.

KAISE SAFE RAKHTE HAIN (imaandaar baat):

    Ye MILITARY-GRADE encryption NAHI hai. Ye ek local, single-user
    tool hai. Store do cheezein karta hai:

      1. File `data/credentials.json` mein hai, aur `data/` GITIGNORED
         hai — matlab galti se git/GitHub pe kabhi nahi jaayega.

      2. Password plaintext mein NAHI likha — machine-specific key se
         obfuscate (XOR + base64) hota hai. Koi file khol ke seedha
         password nahi padh sakta.

    Ye "casual snooping" se bachata hai (koi file khole to password
    saaf na dikhe). Agar attacker ke paas machine ka poora access hai
    to wo phir bhi nikaal sakta hai — us level ki security OS keychain
    se aati hai, ek JSON file se nahi. Isliye jhooth nahi bolenge.

    ⚠️ Behtar chahiye to `keyring` library use ki ja sakti hai (OS ka
    apna secure store). Wo optional rakha — abhi zero-dependency
    approach hai taaki setup aasaan rahe.

DHYAN: OTP / 2FA / PIN yahan STORE NAHI hote. Wo har baar user khud
daalega — ye safety rule hai (safety.py dekh).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import platform
from dataclasses import dataclass
from pathlib import Path

from ..config import settings as default_settings

log = logging.getLogger("saarthi.security.credentials")


# ----------------------------------------------------------------------
#  Obfuscation — plaintext se behtar, keychain se kam
# ----------------------------------------------------------------------


def _machine_key() -> bytes:
    """
    Is machine ke liye ek stable key banao.

    Machine ke naam + user home se derive hoti hai — matlab ye file
    kisi DOOSRI machine pe copy ki jaaye to password decode NAHI hoga
    (thoda extra protection). Same machine pe hamesha same key.
    """
    seed = f"saarthi::{platform.node()}::{Path.home()}"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _xor(data: bytes, key: bytes) -> bytes:
    """Simple repeating-key XOR."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _obfuscate(plain: str) -> str:
    """Password ko obfuscate karke store-able string banao."""
    raw = plain.encode("utf-8")
    scrambled = _xor(raw, _machine_key())
    return base64.b64encode(scrambled).decode("ascii")


def _deobfuscate(stored: str) -> str:
    """Store ki hui string ko wapas password banao."""
    try:
        scrambled = base64.b64decode(stored.encode("ascii"))
        raw = _xor(scrambled, _machine_key())
        return raw.decode("utf-8")
    except Exception:  # noqa: BLE001 — corrupt ya doosri machine se copy
        return ""


# ----------------------------------------------------------------------
#  Data type
# ----------------------------------------------------------------------


@dataclass
class Credential:
    """Ek website ka login."""

    site: str                 # normalized key, jaise "github.com" ya "gmail"
    username: str             # email ya username
    password: str             # plaintext (memory mein) — file pe obfuscated
    login_url: str = ""       # optional — login page ka URL
    notes: str = ""

    def masked(self) -> str:
        """User ko dikhane ke liye — password chhupa ke."""
        pw = "•" * 8 if self.password else "(none)"
        url = f"  [{self.login_url}]" if self.login_url else ""
        return f"{self.site}: {self.username} / {pw}{url}"


# ----------------------------------------------------------------------
#  Store
# ----------------------------------------------------------------------


def _normalize_site(site: str) -> str:
    """
    Site naam ko ek consistent key banao.

    "https://github.com/login" -> "github.com"
    "Gmail"                    -> "gmail"
    "www.Flipkart.com"         -> "flipkart.com"
    """
    s = (site or "").strip().lower()
    if not s:
        return s

    # URL se domain nikaalo
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]          # path hatao
    s = s.split("?", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s.strip()


class CredentialStore:
    """
    Website logins ka store — JSON file, obfuscated passwords.

    Use:
        store = CredentialStore()
        store.save("github.com", "me@x.com", "hunter2")
        cred = store.get("github")          # partial match chalega
        store.delete("github.com")
    """

    def __init__(self, path: Path | str | None = None):
        if path is None:
            path = default_settings.data_dir / "credentials.json"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._creds: dict[str, Credential] = {}
        self._load()

    # ------------------------------------------------------------------
    #  Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("credentials.json padh nahi paya: %s", exc)
            return

        for site, entry in (raw or {}).items():
            self._creds[site] = Credential(
                site=site,
                username=entry.get("username", ""),
                password=_deobfuscate(entry.get("password", "")),
                login_url=entry.get("login_url", ""),
                notes=entry.get("notes", ""),
            )

    def _persist(self) -> None:
        data = {
            site: {
                "username": cred.username,
                "password": _obfuscate(cred.password),
                "login_url": cred.login_url,
                "notes": cred.notes,
            }
            for site, cred in self._creds.items()
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

        # File permissions tang karo (best-effort, POSIX pe kaam karta hai)
        try:
            import os
            import stat

            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except Exception:  # noqa: BLE001 — Windows pe chmod limited hai
            pass

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def save(
        self,
        site: str,
        username: str,
        password: str,
        login_url: str = "",
        notes: str = "",
    ) -> Credential:
        """Ek login save/update karo."""
        key = _normalize_site(site)
        if not key:
            raise ValueError("site khali nahi ho sakta")

        cred = Credential(
            site=key,
            username=username.strip(),
            password=password,
            login_url=login_url.strip(),
            notes=notes.strip(),
        )
        self._creds[key] = cred
        self._persist()
        log.info("Credential save hua: %s", key)
        return cred

    def get(self, site: str) -> Credential | None:
        """
        Site ka login nikaalo.

        Pehle exact key, phir partial match — user "github" bole aur
        store mein "github.com" ho to bhi mil jaaye.
        """
        key = _normalize_site(site)
        if key in self._creds:
            return self._creds[key]

        # Partial match — dono taraf se
        for stored_key, cred in self._creds.items():
            if key and (key in stored_key or stored_key in key):
                return cred

        # Naam ka hissa (subdomain-free) match
        base = key.split(".", 1)[0] if key else ""
        if base:
            for stored_key, cred in self._creds.items():
                if base and base in stored_key:
                    return cred
        return None

    def delete(self, site: str) -> bool:
        """Ek login hata do."""
        key = _normalize_site(site)
        if key in self._creds:
            del self._creds[key]
            self._persist()
            return True
        # Partial — get() jaisa hi resolve karke hata do
        cred = self.get(site)
        if cred is not None and cred.site in self._creds:
            del self._creds[cred.site]
            self._persist()
            return True
        return False

    def list_sites(self) -> list[Credential]:
        """Saare saved logins (password masked karke dikhaana caller ka kaam)."""
        return sorted(self._creds.values(), key=lambda c: c.site)

    def __len__(self) -> int:
        return len(self._creds)
