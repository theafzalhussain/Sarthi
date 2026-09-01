"""
Ctrl+V se seedha image paste — custom line reader (Windows).

Normal Python input() Ctrl+V ko sirf TEXT ki tarah leta hai; wo clipboard
ki image nahi dekh sakta. Isliye ye chhota reader banaya hai jo har key
khud padhta hai (msvcrt) aur:

  - Ctrl+V (\x16) dabte hi clipboard check karta hai:
        * image ho     -> use base64 bana ke attach kar leta hai
                          (line par ek "[image attached]" marker dikhta hai)
        * text ho      -> woh text seedha line mein paste ho jaata hai
  - Enter        -> line poori
  - Backspace    -> ek char (ya attached image) hatao
  - Esc          -> caller ko batao (KeyboardInterrupt jaisa) — cancel
  - baaki keys   -> normal typing

Non-Windows par msvcrt nahi hota — wahan ye module `supported()` False
deta hai aur caller normal input() use karta hai.

Return: read_line() ek (text, image_b64) tuple deta hai. image_b64 None
ho sakta hai. Text/aur-image dono ho sakte hain.
"""

from __future__ import annotations

import sys

try:
    import msvcrt  # Windows only
    _HAVE_MSVCRT = True
except ImportError:  # pragma: no cover - non-Windows
    _HAVE_MSVCRT = False


def supported() -> bool:
    """Ye reader is platform par chal sakta hai?"""
    return _HAVE_MSVCRT


def poll_for_esc(stop_flag) -> bool:
    """
    Blocking: jab tak Esc na dabe ya `stop_flag.is_set()` na ho, sunte
    raho. Esc dabe to True, warna (stop hone par) False.

    Ye AGENT ke chalte waqt (turn processing) use hota hai — user beech
    mein Esc daba ke cancel kar sake. Thread mein chalao (blocking hai).

    Non-Windows par msvcrt nahi — turant False (wahan Ctrl+C se cancel).
    """
    if not _HAVE_MSVCRT:
        return False
    import time as _time
    while not stop_flag.is_set():
        try:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == "\x1b":  # Esc
                    return True
                # koi aur key — ignore (turn ke beech typing bekaar)
        except Exception:  # noqa: BLE001
            return False
        _time.sleep(0.03)
    return False


# Control keys
_CTRL_V = "\x16"
_CTRL_C = "\x03"
_ENTER = ("\r", "\n")
_BACKSPACE = ("\x08", "\x7f")
_ESC = "\x1b"
# Function keys aate hain do-byte sequence me: prefix (\x00 ya \xe0) + code
_FN_PREFIXES = ("\x00", "\xe0")
_FN_F2 = "<"   # F2 ka second byte (msvcrt): '<'
_FN_F3 = "="   # F3 (spare)


class EscPressed(Exception):
    """User ne prompt par Esc dabaya — current input cancel."""


def read_line(prompt: str) -> tuple[str, str | None]:
    """
    Ek line padho, Ctrl+V se image paste support ke saath.

    Returns:
        (text, image_b64)  — image_b64 None ho sakta hai.

    Raises:
        EscPressed        — user ne Esc dabaya (khaali prompt cancel)
        EOFError          — Ctrl+D / stream end
        KeyboardInterrupt — Ctrl+C
    """
    # Prompt likho. Saath hi bracketed-paste mode ON karo — taaki Ctrl+V
    # par terminal content ko ESC[200~ ... ESC[201~ me lapet ke bheje.
    # Isse hum paste ko normal typing se alag pehchan lete hain, aur
    # clipboard me image ho to usse attach kar dete hain.
    sys.stdout.write("\x1b[?2004h" + prompt)
    sys.stdout.flush()

    st = {"buf": [], "image": None, "shown": False}

    def _do_paste() -> None:
        """Clipboard se image (priority) ya text uthao aur line mein daalo."""
        img, text = _grab_clipboard()
        if img is not None:
            st["image"] = img
            if not st["shown"]:
                sys.stdout.write(" [image attached] ")
                sys.stdout.flush()
                st["shown"] = True
            return
        if text:
            clean = text.replace("\r", " ").replace("\n", " ")
            st["buf"].append(clean)
            sys.stdout.write(clean)
            sys.stdout.flush()

    try:
        while True:
            ch = msvcrt.getwch()

            # --- Enter: line khatam ---
            if ch in _ENTER:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(st["buf"]), st["image"]

            # --- Ctrl+C ---
            if ch == _CTRL_C:
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt

            # --- Esc: cancel YA bracketed-paste ka shuruaat ---
            # Kai terminal (VS Code, Windows Terminal) Ctrl+V par
            # "bracketed paste" bhejte hain:
            #     ESC [ 2 0 0 ~  <content>  ESC [ 2 0 1 ~
            # Yani Ctrl+V ka \x16 hum tak aata hi nahi — uske badle ye
            # sequence aati hai.
            if ch == _ESC:
                pasted = _read_bracketed_paste()
                if pasted is not None:
                    # Paste tha. Pehle clipboard me IMAGE dekho — hai to
                    # wahi attach (text ignore). Warna bracket ka text.
                    img, _ = _grab_clipboard()
                    if img is not None:
                        st["image"] = img
                        if not st["shown"]:
                            sys.stdout.write(" [image attached] ")
                            sys.stdout.flush()
                            st["shown"] = True
                    elif pasted:
                        clean = pasted.replace("\r", " ").replace("\n", " ")
                        st["buf"].append(clean)
                        sys.stdout.write(clean)
                        sys.stdout.flush()
                    continue
                # Warna: normal Esc — khaali prompt par cancel
                if not st["buf"] and st["image"] is None:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    raise EscPressed
                continue

            # --- Backspace ---
            if ch in _BACKSPACE:
                if st["image"] is not None and not st["buf"]:
                    st["image"] = None
                    if st["shown"]:
                        _erase_marker()
                        st["shown"] = False
                    continue
                if st["buf"]:
                    # buf entry poora paste-chunk ho sakti hai; ek char hatao
                    last = st["buf"][-1]
                    if len(last) > 1:
                        st["buf"][-1] = last[:-1]
                    else:
                        st["buf"].pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            # --- Ctrl+V: PASTE (image ya text) ---
            if ch == _CTRL_V:
                _do_paste()
                continue

            # --- Special / function keys (arrows, F-keys) ---
            if ch in _FN_PREFIXES:
                second = msvcrt.getwch()
                if second == _FN_F2:
                    # F2 = image paste (Ctrl+V ka guaranteed backup)
                    _do_paste()
                # baaki F-keys / arrows — ignore
                continue

            # --- Normal printable char ---
            if ch.isprintable():
                st["buf"].append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        # Har raaste par (Enter/Ctrl+C/Esc/exception) mode band ho
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()

    # unreachable


def _read_bracketed_paste() -> str | None:
    """
    ESC already padha ja chuka hai. Dekho kya ye bracketed-paste hai:
        ESC [ 2 0 0 ~   <content>   ESC [ 2 0 1 ~

    Agar haan -> content string return karo (image ho to caller clipboard
    se lega, ye text sirf fallback hai).
    Agar ye paste NAHI hai (normal Esc ya doosri escape sequence) -> None.

    msvcrt me "unread" nahi hota, isliye kbhit() se peek karte hain.
    Paste ke saare bytes turant queue me hote hain, isliye ye safe hai.
    """
    # Turant koi key available hai? Nahi -> ye akela Esc tha.
    if not msvcrt.kbhit():
        return None

    # Bracketed paste start marker: '[200~'
    start_expected = "[200~"
    seen = ""
    for want in start_expected:
        if not msvcrt.kbhit():
            # Adhoora — matlab ye paste nahi tha. (Jo padha wo consume ho
            # gaya; normal Esc-sequence me ye theek hai.)
            return None
        c = msvcrt.getwch()
        seen += c
        if c != want:
            # Match nahi hua — ye koi aur escape sequence (arrow etc.).
            # Baaki available bytes bhi kha jao taaki line ganda na ho.
            _drain()
            return ""  # paste-jaisa tha par marker match nahi — safe empty
    # Ab content padho jab tak '[201~' (end marker) na aaye
    content = []
    tail = ""
    while True:
        if not msvcrt.kbhit():
            # End marker ke bina khatam — jo mila wahi content
            break
        c = msvcrt.getwch()
        tail += c
        if tail.endswith("\x1b[201~"):
            # End marker mila — usse content se hatao
            content_str = "".join(content) + tail[:-6]
            return content_str
        # tail ko chhota rakho (memory)
        if len(tail) > 6:
            content.append(tail[0])
            tail = tail[1:]
    return "".join(content) + tail


def _drain() -> None:
    """Available buffered keys ko kha jao (best-effort)."""
    try:
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:  # noqa: BLE001
        pass


def _erase_marker() -> None:
    """Line se ' [image attached] ' marker mitao (best-effort)."""
    marker = " [image attached] "
    sys.stdout.write("\b" * len(marker) + " " * len(marker) + "\b" * len(marker))
    sys.stdout.flush()


def _grab_clipboard() -> tuple[str | None, str | None]:
    """
    Clipboard se image (base64) YA text nikaalo.

    Returns:
        (image_b64, text) — dono None ho sakte hain. Image ko priority.
    """
    # 1. Image?
    try:
        from .image_input import try_from_clipboard

        img = try_from_clipboard()
        if img:
            return img, None
    except Exception:  # noqa: BLE001
        pass

    # 2. Text?
    try:
        text = _clipboard_text()
        if text:
            return None, text
    except Exception:  # noqa: BLE001
        pass

    return None, None


def _clipboard_text() -> str | None:
    """Windows clipboard se text (best-effort)."""
    # tkinter har Python ke saath aata hai — koi extra dependency nahi
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        finally:
            root.destroy()
        return text or None
    except Exception:  # noqa: BLE001
        return None
