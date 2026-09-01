# SAARTHI — Setup on a New Device

Run SAARTHI on any laptop or desktop (Windows / macOS / Linux).
It is a normal Python project, so setup is the same everywhere with tiny
per-OS differences.

> Phones (Android/iOS) cannot run this directly — see the "Mobile" section
> at the bottom for how to use SAARTHI *from* a phone.

---

## What you need (once per device)

1. **Python 3.10 or newer** — check with: `python --version`
   - Windows: install from https://python.org (tick "Add to PATH")
   - macOS: `brew install python` (or from python.org)
   - Linux: `sudo apt install python3 python3-venv python3-pip`
2. **Git** — check with: `git --version`
   - https://git-scm.com/downloads
3. **Your API keys** — the `.env` file is NOT in Git (it holds secrets),
   so you create it fresh on each device. Keep your keys somewhere safe
   (password manager) so you can paste them in.

---

## Step-by-step

### 1. Get the code

```bash
git clone https://github.com/theafzalhussain/Sarthi.git
cd Sarthi
```

(If you already cloned it before, just update: `git pull`)

### 2. Create a virtual environment (keeps things clean)

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should now see `(.venv)` at the start of your prompt.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

That is enough for text mode. Document tools (PDF/Excel/PPT/Word) install
their own libraries automatically the first time you use them.

### 4. Add your API keys

Copy the example file, then edit it and paste your keys:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux:**
```bash
cp .env.example .env
nano .env
```

You need **at least one** free key. The easiest is NVIDIA (one key = 4
models) or Gemini (needed for screenshots/vision). All are free:
- NVIDIA: https://build.nvidia.com
- Gemini: https://aistudio.google.com/apikey
- Groq: https://console.groq.com

### 5. Run it

```bash
python cli.py
```

That's it. Type in any language — English or Hinglish — and it replies in
the same language.

---

## Optional features (install only if you want them)

These are commented out in `requirements.txt`. Uncomment the lines you
want, then run `pip install -r requirements.txt` again.

- **Voice** (talk to it): `faster-whisper`, `sounddevice`, `numpy`
  - Linux/macOS also need PortAudio (see comments in requirements.txt)
- **Browser control** (open/read any website): `playwright`
  - After installing: `playwright install chromium`
- **Desktop control** (screenshots, mouse/keyboard): `mss`, `Pillow`, `pyautogui`

---

## Moving to another device — the short version

On the OLD device, make sure your work is pushed:
```bash
git add -A
git commit -m "my changes"
git push
```

On the NEW device:
```bash
git clone https://github.com/theafzalhussain/Sarthi.git
cd Sarthi
python -m venv .venv
# activate it (see step 2 above)
pip install -r requirements.txt
# create .env with your keys (see step 4 above)
python cli.py
```

The only thing that does NOT travel through Git is your `.env` (keys) and
the `data/` folder (memory, generated files). That is by design — secrets
should never be in Git.

---

## Mobile (Android / iOS)

SAARTHI's brain is a Python program — a phone cannot run `python cli.py`
directly. Two realistic options:

1. **Run SAARTHI on a laptop/desktop and control it from your phone.**
   The `android/` folder in this repo is a companion phone app that talks
   to the running agent over your local WiFi. Your laptop is the "brain",
   the phone is a remote.

2. **Run it in a Linux environment on the phone (advanced).**
   On Android you can install [Termux](https://termux.dev), then follow
   the Linux steps above (`pkg install python git`, clone, etc.). This
   works for text mode but is fiddly — the laptop approach is much easier.

For most people: keep the agent on a laptop/desktop, and if you want phone
control, set up the `android/` app (see its own instructions).
```
