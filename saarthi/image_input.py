"""
Image input helper — chat mein image/screenshot attach karne ke liye.

Teen source support karte hain:
  - clipboard  (Win+Shift+S se screenshot lo, phir agent ko /paste)
  - file path  (koi bhi .png/.jpg file)
  - desktop screenshot (agent khud le le)

Sab ek base64 string return karte hain (bina data-uri prefix) jise
Message.user(image_b64=...) mein seedha bheja ja sakta hai.

Pillow (PIL) use hota hai — already project mein installed hai.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path


class ImageInputError(Exception):
    """Image load/grab nahi ho payi — user ko saaf wajah batao."""


def _pil_to_b64(img, fmt: str = "PNG") -> str:
    """PIL Image ko base64 PNG string mein badlo."""
    # RGBA/palette images ko RGB pe laao — JPEG/consistency ke liye safe
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def from_clipboard() -> str:
    """
    Clipboard mein jo image hai usse base64 do.

    Windows: Win+Shift+S se area screenshot lo (wo clipboard mein
    jaata hai), phir ye call karo. Ya kisi image ko copy karo.

    Raises ImageInputError agar clipboard mein image na ho.
    """
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        raise ImageInputError(
            "Pillow install nahi hai. Chala: pip install pillow"
        ) from exc

    try:
        img = ImageGrab.grabclipboard()
    except Exception as exc:  # noqa: BLE001 — platform-specific gadbad
        raise ImageInputError(
            f"Clipboard se image nahi mili: {exc}"
        ) from exc

    if img is None:
        raise ImageInputError(
            "Clipboard mein koi image nahi hai.\n"
            "  Pehle Win+Shift+S se screenshot lo (ya image copy karo),\n"
            "  phir dobara /paste chala."
        )

    # Kabhi-kabhi grabclipboard() file path(s) ki list deta hai
    # (jab tumne Explorer mein image file copy ki ho) — pehli file load
    if isinstance(img, list):
        if not img:
            raise ImageInputError("Clipboard mein image nahi mili.")
        return from_file(str(img[0]))

    return _pil_to_b64(img)


def try_from_clipboard() -> str | None:
    """
    Clipboard mein image ho to base64 do, warna None — koi error nahi.

    Ye `from_clipboard()` ka "silent" version hai. Isse REPL har normal
    message se pehle chup-chaap clipboard check kar sakta hai: agar user
    ne abhi Ctrl+V / Win+Shift+S se koi image copy ki hai to wo apne-aap
    us message ke saath attach ho jaati hai — `/paste` likhne ki zarurat
    nahi. Kuch na mile (ya koi gadbad ho) to bas None milta hai.
    """
    try:
        return from_clipboard()
    except ImageInputError:
        return None
    except Exception:  # noqa: BLE001 — clipboard kabhi crash na kare
        return None


def from_file(path: str) -> str:
    """Ek image file (.png/.jpg/.webp...) ko base64 do."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise ImageInputError(
            "Pillow install nahi hai. Chala: pip install pillow"
        ) from exc

    # Quotes hata do — user aksar drag-drop pe path quotes ke saath deta hai
    clean = path.strip().strip('"').strip("'")
    p = Path(clean).expanduser()

    if not p.exists():
        raise ImageInputError(f"File nahi mili: {p}")
    if not p.is_file():
        raise ImageInputError(f"Ye file nahi hai: {p}")

    try:
        with Image.open(p) as img:
            img.load()
            return _pil_to_b64(img)
    except Exception as exc:  # noqa: BLE001
        raise ImageInputError(f"Image khul nahi payi ({p.name}): {exc}") from exc


def from_screenshot() -> str:
    """
    Poore desktop ka screenshot le ke base64 do.

    Agent ko screen dikhane ka sabse aasaan tareeka — kuch copy karne
    ki zarurat nahi.
    """
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        raise ImageInputError(
            "Pillow install nahi hai. Chala: pip install pillow"
        ) from exc

    try:
        img = ImageGrab.grab()
    except Exception as exc:  # noqa: BLE001
        raise ImageInputError(
            f"Screenshot nahi liya ja saka: {exc}"
        ) from exc

    return _pil_to_b64(img)
