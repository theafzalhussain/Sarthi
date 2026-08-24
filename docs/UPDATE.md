# Update kaise kare (Windows)

> **Ye file isliye hai** kyunki `git pull` kaam nahi karta agar tera
> folder git repo hi na ho. Ye sabse common problem hai.

---

## Pehle check kar: tera folder git repo hai?

PowerShell mein apne project folder mein jaake:

```powershell
git status
```

| Output | Matlab | Kya karna hai |
|---|---|---|
| `On branch main ...` | ✅ Sahi repo hai | Neeche **"Normal update"** dekh |
| `fatal: not a git repository` | ❌ **Ye repo nahi hai** | Neeche **"Pehli baar setup"** dekh |

**`fatal: not a git repository` ka matlab:** tune code ZIP download kiya
tha ya copy-paste kiya tha, `git clone` nahi kiya. Isliye `git pull`
kabhi kaam nahi karega — us folder ka GitHub se koi rishta hi nahi hai.

---

## Normal update (repo sahi hai)

```powershell
cd C:\Sarthi
git pull
python run_tests.py
```

Bas. `.env` file safe rehti hai — wo gitignored hai, `git pull` usko
chhuta nahi.

### Agar `git pull` error de

```powershell
# Tere local changes hain jo conflict kar rahe hain
git stash          # unhe side mein rakh do
git pull
git stash pop      # zarurat ho to wapas laao
```

Ya agar tere local changes ki zarurat nahi:

```powershell
git fetch origin
git reset --hard origin/main    # tere local changes MIT jaayenge
```

---

## Pehli baar setup (fresh clone)

### Do cheezein DHYAN se

**1. OneDrive folder mein git repo MAT rakho.**
OneDrive sync aur git ek doosre se ladte hain — OneDrive `.git` folder ke
files ko lock kar deta hai aur repo corrupt ho jaata hai.

**2. Folder ke naam mein SPACE mat rakho.**
`Sarthi agent` mein space hai. Isse commands mein quotes lagane padte
hain aur bahut tools confuse ho jaate hain.

### Commands (poora block copy karke paste kar de)

```powershell
cd C:\
git clone https://github.com/theafzalhussain/Sarthi.git
cd C:\Sarthi
pip install -r requirements.txt
```

### Apni purani `.env` copy kar (keys usme hain)

```powershell
Copy-Item "$HOME\OneDrive\Desktop\Sarthi agent\.env" C:\Sarthi\.env
```

`.env` na ho to naya bana:

```powershell
Copy-Item .env.example .env
notepad .env
```

### Check kar ki sab theek hai

```powershell
cd C:\Sarthi
git status              # "On branch main" aana chahiye
python run_tests.py     # 195 tests pass hone chahiye
python cli.py
```

### Purana folder

Naya wala chal jaaye tab purana folder delete kar de, warna confusion
hoti rahegi ki kaunsa chala raha hun.

---

## Python version ka dhyan

```powershell
python --version
```

SAARTHI **Python 3.9+** pe chalta hai. Par ek baat:

**Bahut naya Python (3.13 / 3.14) ho to VOICE ke packages install nahi
honge.** Wajah: `faster-whisper`, `sounddevice`, `pvporcupine` — ye
C-extension packages hain, aur naye Python version ke liye unke
pre-built wheels aane mein kuch mahine lagte hain.

**Check kar:**

```powershell
pip install faster-whisper sounddevice numpy
```

Error aaye jisme `Building wheel ... failed` ya `Microsoft Visual C++
14.0 or greater is required` likha ho, to wheels available nahi hain.

**Fix — Python 3.12 alag se install kar (purana hataye bina):**

1. https://www.python.org/downloads/release/python-3129/ se
   *Windows installer (64-bit)* download kar
2. Install karte waqt **"Add python.exe to PATH" MAT** tick kar
   (warna tera Python 3.14 confuse ho jaayega)
3. Us Python se venv bana:

```powershell
cd C:\Sarthi
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install faster-whisper sounddevice numpy
```

Ab jab bhi kaam karna ho:

```powershell
cd C:\Sarthi
.\.venv\Scripts\Activate.ps1
python cli.py
```

**Text mode (`python cli.py`) Python 3.14 pe theek chalta hai** — sirf
voice ke liye 3.12 chahiye.

---

## PowerShell ke do chhote jhamele

**1. Ek baar mein ek command chala.**
Kai lines ek saath paste karne pe PowerShell `>>` dikhata hai aur
intezaar karta rehta hai. Ek line chala, Enter, phir agli.

**2. `#` ke baad ka hissa comment hai.**
`python cli.py   # text mode` — ye chalega, `#` wala hissa ignore ho
jaayega. Par safe rehne ke liye comment paste hi mat kar.

**3. Script chalane pe "running scripts is disabled" error?**

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Quick reference

```powershell
cd C:\Sarthi
git status              # repo theek hai?
git pull                # update
python run_tests.py     # 195 tests
python cli.py           # text mode
python hardware_check.py    # mic/speaker/phone diagnostic
```

| Problem | Fix |
|---|---|
| `fatal: not a git repository` | Fresh clone kar (upar dekh) |
| `can't open file 'hardware_check.py'` | File nahi hai — matlab pull nahi hua |
| `git pull` conflict | `git stash` phir `git pull` |
| Voice packages install nahi hote | Python 3.12 ka venv bana |
| `.env` gayab | `Copy-Item .env.example .env` |
