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

## ⚠️ SABSE PEHLE: PROMPT PADHNA SEEKH LE

PowerShell ka prompt batata hai tu KAHAN khada hai:

```
PS C:\>              <- tu C: drive pe hai. Yahan project ki files NAHI hain.
PS C:\Sarthi>        <- tu project ke ANDAR hai. Sahi jagah. ✅
```

**99% "file not found" error isi wajah se aati hai** — command sahi
hoti hai, par tu galat folder mein khada hota hai.

```
PS C:\> python run_tests.py
C:\Python314\python.exe: can't open file 'C:\run_tests.py'
                                             ^^^^^^^^^^^^^^^
                              dekh — ye C:\ mein dhoondh raha hai,
                              C:\Sarthi mein nahi
```

**Fix hamesha yahi hai:**

```powershell
cd C:\Sarthi
```

Koi bhi command chalane se PEHLE dekh le ki prompt `PS C:\Sarthi>`
dikha raha hai ya nahi.

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

Ek-ek line chala, har line ke baad Enter:

```powershell
cd C:\
```
```powershell
git clone https://github.com/theafzalhussain/Sarthi.git
```
```powershell
cd C:\Sarthi
```
> ⬆️ **YE LINE SABSE ZARURI HAI.** Iske bina agli saari commands fail
> hongi, kyunki tu C:\ pe khada rahega jahan project ki files nahi hain.
> Prompt `PS C:\Sarthi>` dikhna chahiye.

```powershell
pip install -r requirements.txt
```

**"destination path 'Sarthi' already exists" aaya?** Matlab clone pehle
hi ho chuka hai — dobara clone karne ki zarurat nahi. Seedha
`cd C:\Sarthi` kar aur aage badh.

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
python run_tests.py     # 451 tests pass hone chahiye
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

**Python 3.14 pe VOICE bhi chalta hai — verify ho chuka hai.**

Pehle mujhe (AI ko) shak tha ki `faster-whisper` aur `sounddevice`
jaise C-extension packages ke 3.14 wheels nahi honge. Par user ne asli
machine pe chala ke dikhaya — sab native cp314 wheels ke saath install
ho gaye:

```
ctranslate2-4.8.1-cp314-cp314-win_amd64.whl
numpy-2.5.2-cp314-cp314-win_amd64.whl
onnxruntime-1.29.0-cp314-cp314-win_amd64.whl
sounddevice-0.5.6-py3-none-win_amd64.whl
faster_whisper-1.2.1-py3-none-any.whl
```

**Sabak: guess mat karo, chala ke dekho.**

```powershell
pip install faster-whisper sounddevice numpy
pip install pyttsx3          # Windows pe awaaz ke liye
```

Agar KABHI `Building wheel ... failed` ya `Microsoft Visual C++ 14.0 or
greater is required` aaye, to us package ke wheels tere Python version
ke liye nahi hain.

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
python run_tests.py     # 451 tests
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
