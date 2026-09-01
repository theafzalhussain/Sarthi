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

## Run it as ONE command from anywhere (like `kiro`)

Instead of `python cli.py`, you can install SAARTHI as a real command so
you can type just `saarthi` from **any folder** on the machine.

From inside the Sarthi folder (with your venv active), run once:

```bash
pip install -e .
```

Now, from any directory:

```bash
saarthi
```

- `-e` (editable) means your code changes take effect immediately — no
  reinstall needed after `git pull`.
- The `saarthi` command is created in your Python `Scripts`/`bin` folder,
  which is on your PATH, so it works globally like `kiro`.

### Where does it read your keys from?

You do NOT need to add keys in every project. `saarthi` looks for keys in
three places (in this order), and the device-wide file is the easy one:

1. **`~/.saarthi/.env` — set ONCE per device (recommended, like `kiro`).**
   Run this once and paste your keys when asked:
   ```bash
   saarthi login
   ```
   It saves your keys to your home folder (`~/.saarthi/.env`), NOT to the
   project. After that, `saarthi` works from ANY folder on that device
   with no local `.env` needed. This is the closest to how `kiro` works.

2. A `.env` file in the current project folder (optional per-project
   override).

3. System environment variables (`NVIDIA_API_KEY`, etc.).

You still enter your keys ONCE on each new device (a provider has to
authenticate somewhere), but never per-project and never per-run.

### Optional extras with the command install

```bash
pip install -e ".[docs]"      # PDF/Excel/PPT/Word libraries
pip install -e ".[browser]"   # website control (then: playwright install chromium)
pip install -e ".[voice]"     # talk to it
pip install -e ".[all]"       # everything
```

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
pip install -e .            # installs deps AND the `saarthi` command
saarthi login              # paste your keys ONCE (saved to ~/.saarthi/.env)
saarthi                     # now run from ANY folder
```

The only thing that does NOT travel through Git is your keys and the
`data/` folder (memory, generated files). That is by design — secrets
should never be in Git. `saarthi login` stores keys on the device (in
your home folder), so you enter them once per device, never per project.

---

## Mobile (Android / iOS)

SAARTHI's brain is a Python program — a phone cannot run it the normal
way. Two realistic options:

1. **Easiest: run SAARTHI on a laptop/desktop, control it from your phone.**
   The `android/` folder in this repo is a companion phone app that talks
   to the running agent over your local WiFi. Your laptop is the "brain",
   the phone is a remote.

2. **Android — run it directly with Termux (works, a bit fiddly):**
   [Termux](https://termux.dev) gives you a Linux shell on Android. Then
   it is the same as the Linux steps:
   ```bash
   pkg update && pkg install python git
   git clone https://github.com/theafzalhussain/Sarthi.git
   cd Sarthi
   pip install -e .
   # set your keys, then:
   saarthi
   ```
   Text mode works well this way. Voice/desktop/browser control are hard
   on a phone — for those, use option 1.

iOS does not allow this kind of Python app, so on iPhone use option 1
(control a laptop agent from the phone).

For most people: keep the agent on a laptop/desktop, and if you want phone
control, set up the `android/` app.
