# Voice Setup

Bolke agent chalane ki poori guide. Sab **free aur offline** hai.

**Sabse pehle ye chala** — batayega kya missing hai:

```bash
python voice_cli.py --check
```

---

## Minimum setup (5 minute)

```bash
# 1. Sunne ke liye (Whisper)
pip install faster-whisper

# 2. Mic ke liye
pip install sounddevice
sudo apt install libportaudio2        # Ubuntu/Debian
# sudo dnf install portaudio          # Fedora
# brew install portaudio              # macOS
# Windows: kuch nahi chahiye

# 3. Bolne ke liye (sabse aasaan)
sudo apt install espeak-ng            # Linux
# macOS pe `say` already hai
```

Chala:
```bash
python voice_cli.py
```

Enter dabao → bolo → agent kaam karega aur jawab bolega.

---

## Model kaunsa chuno (Pillar #3 — budget hardware)

`.env` mein `WHISPER_MODEL` set kar:

| Model | RAM | Speed | Accuracy | Kiske liye |
|---|---|---|---|---|
| `tiny` | ~1 GB | bahut tez | kaam chalau | testing, bahut purana laptop |
| `base` | ~1 GB | tez | theek | **4GB RAM laptop** |
| `small` | ~2 GB | medium | acchi | **8GB RAM — recommended** |
| `medium` | ~5 GB | dheemi | bahut acchi | 16GB RAM |
| `large-v3` | ~10 GB | bahut dheemi | best | GPU chahiye |

`--check` khud bata dega tere RAM ke hisaab se kaunsa model lena hai.

Pehli baar model download hota hai (base = ~150MB), **uske baad offline chalta hai.**

---

## Awaaz ke options

| Backend | Quality | Setup |
|---|---|---|
| **piper** | bahut acchi | voice model download karna padta hai |
| **espeak** | robotic par saaf | `sudo apt install espeak-ng` — 10MB, sabse aasaan |
| **say** | acchi | macOS pe already hai |
| **pyttsx3** | theek | `pip install pyttsx3` |
| **null** | koi awaaz nahi | fallback — jawab print hota hai |

`TTS_BACKEND=auto` (default) sabse accha available backend khud chun leta hai.

### Piper (best quality chahiye to)

```bash
pip install piper-tts

mkdir -p ~/.local/share/piper/voices
cd ~/.local/share/piper/voices

# en_US-amy-medium — Hinglish ke liye theek
# Free models: https://huggingface.co/rhasspy/piper-voices
# .onnx AUR .onnx.json dono download karne hain
```

Phir `.env` mein:
```
TTS_BACKEND=piper
PIPER_MODEL=/home/tu/.local/share/piper/voices/en_US-amy-medium.onnx
```

---

## Wake mode — kaise jagaye

```
WAKE_MODE=push_to_talk    # Enter dabao. ZERO SETUP.  <- isse shuru kar
WAKE_MODE=energy          # koi bhi tez awaaz
WAKE_MODE=porcupine       # asli wake word, free key chahiye
```

**Push-to-talk se shuru kar.** Wake word fancy lagta hai par:
- Zero setup
- Zero false alarms
- Free-tier tokens bachte hain (galti se trigger nahi hota)

### Asli wake word chahiye to

```bash
pip install pvporcupine
```

Free key le: https://console.picovoice.ai/

```
WAKE_MODE=porcupine
PORCUPINE_ACCESS_KEY=tera_key
PORCUPINE_KEYWORD=jarvis
```

Built-in keywords: `jarvis`, `computer`, `alexa`, `hey google`, `hey siri`, `porcupine`, `bumblebee`, `terminator`, `blueberry`, `grasshopper` aur kuch aur.

**"Hey Saarthi" built-in nahi hai** — par Picovoice Console pe **free custom wake word train** kar sakta hai. `.ppn` file download karke:
```
PORCUPINE_KEYWORD_PATH=/path/to/hey_saarthi.ppn
```

---

## Hinglish tuning — ye SAARTHI ka asli kaam hai

Ye samajhna zaroori hai, kyunki **yahi differentiator hai.**

### Problem

Whisper English-first bana hai. Hinglish bolne pe galat sunta hai:

| Tu bola | Whisper ne suna |
|---|---|
| paytm kholo | pay time cholo |
| zomato se order | **tomato** se order |
| do hazaar paise | do hazar **peace** |
| phonepe se bhej | phone pay se **beige** |
| irctc pe dekho | i r c t c pe dekho |

Ek galat word = pura command fail. Aur paise wale case mein **khatarnak** bhi.

### Solution — do layer

**1. BIASING (sunne se pehle)**

Whisper ko `initial_prompt` dete hain jisme Hinglish examples aur app naam hote hain. Isse wo unhi words ki taraf jhukta hai. Ye bilkul free hai — koi training nahi.

**2. CORRECTION (sunne ke baad)**

`saarthi/voice/hinglish_asr.py` mein 55+ correction rules hain. Aur galat sunna theek ho jaata hai.

### Asli farak (measured)

```
Whisper ne suna : "pay time cholo aur die hazaar ka bell bhar do"
Correction baad : "paytm kholo aur dhai hazaar ka bill bhar do"

                    BINA correction    CORRECTION ke saath
  intent            type  (galat)      pay        ✓
  app               koi nahi           paytm      ✓
  amount            1000  (GALAT!)     2500       ✓
```

**₹1500 ka farak.** Isliye ye layer zaroori hai, cosmetic nahi.

### Apni correction add karna

`saarthi/voice/hinglish_asr.py` mein:

```python
SAFE_CORRECTIONS = [
    (r"\bmera\s*app\b", "meraapp"),   # word boundary ZAROORI hai
    ...
]
```

⚠️ **Do rules yaad rakh:**

1. **Word boundary (`\b`) hamesha lagao.** Warna `"paytm"` ke andar `"pay"` match ho jaayega.

2. **Risky corrections `ContextRule` se karo** — enablers *aur* blockers ke saath:

```python
ContextRule(
    wrong="tomato",
    right="zomato",
    enablers=("order", "app", "kholo"),          # DISTINCTIVE hone chahiye
    blockers=("sabzi", "mandi", "khareedo"),     # inke hone pe fix MAT karo
)
```

Ye maine ek asli bug se seekha: pehle enabler list mein `"se"` tha, to *"tomato khareedo sabzi mandi **se**"* bhi zomato ban gaya. **Enabler distinctive hona chahiye, common nahi.**

---

## Compounding fayda (accha side effect)

Whisper ko jo vocabulary bhejte hain wo **memory aur skills se** banti hai:

```
memory  "mummy ka number"  ->  "mummy" boost hota hai
skills  "bijli ka bill"    ->  pura phrase boost hota hai
```

Matlab **jitna tu agent ko sikhaayega, utna accha wo tujhe sunega.** Normal voice assistants mein ye nahi hota.

---

## Voice confirmation (safety)

Risky kaam pe agent bolke puchta hai:

```
saarthi > Ruk ja. 2500 rupay bhejna hai. kisko mummy. Karu? Haan ya nahi bol.
tu      > haan bhai kar de
saarthi > Kar raha hun.
```

**FAIL SAFE hai:**
- Kuch sunai na aaye → 2 baar dobara puchega → phir **mana** kar dega
- Confusing jawab → **mana**
- Chup-chaap paise kabhi nahi jaayenge

Band karna hai to `.env` mein `VOICE_CONFIRMATIONS=false` — **par mat karna.**

---

## Problems aur fix

| Problem | Wajah | Fix |
|---|---|---|
| "PortAudio library not found" | System lib missing | `sudo apt install libportaudio2` |
| Mic detect nahi ho raha | Permission ya device | `python voice_cli.py --check` se devices dekh |
| Whisper bahut dheema | Model bada hai | `WHISPER_MODEL=tiny` ya `base` |
| Awaaz nahi aa rahi | TTS backend nahi | `sudo apt install espeak-ng` |
| Har awaaz pe trigger | energy mode | `WAKE_MODE=push_to_talk` |
| Bolna shuru karte hi kat jaata | silence threshold kam | `min_threshold` badha (`audio.py`) |
| Pehla shabd kat jaata hai | — | already handled (pre-speech buffer hai) |
| Shor wale kamre mein kaam nahi | — | auto-calibrate hota hai, par headset behtar hai |
| Galat app khul raha hai | ASR galti | Us galti ke liye `SAFE_CORRECTIONS` mein rule add kar |

### Debug karna

```bash
# .env mein
SAARTHI_DEBUG=true
```

Isse dikhega ki Whisper ne kya suna aur correction ne kya badla:
```
fix  suna: "pay time cholo" -> samjha: "paytm kholo"
```

### Ek baar test karna (loop ke bina)

```bash
python voice_cli.py --once
```

Ek baar sunega, transcribe karega, result dikhayega. Tuning ke liye best.

---

## Kya nahi hota (imaandaar list)

| Cheez | Wajah |
|---|---|
| **Barge-in** (agent bol raha ho tab tokna) | Echo cancellation chahiye — mushkil hai. Abhi: agent bolega, phir sunega |
| **Perfect Hindi pronunciation** | Hamara text roman hai, Hindi TTS voices Devanagari maangti hain. English voice se padhta hai — samajh aata hai, thoda accent lagta hai |
| **Continuous conversation** | Har command ke liye wake chahiye. Jaan-boojh ke — free tier bachta hai |
| **Real-time streaming** | Pura bolna khatam hone ke baad transcribe hota hai |

---

## Architecture

```
saarthi/voice/
├── hinglish_asr.py   PILLAR #1 — biasing + correction (yahi asli value hai)
├── audio.py          mic recording, silence detection, playback
├── stt.py            Whisper wrapper
├── tts.py            5 TTS backends
├── wake.py           3 wake modes
└── session.py        pura loop
voice_cli.py          entrypoint
```

**Testing note:** `SilenceDetector` aur `prepare_text_for_speech` **pure logic** hain — mic ke bina test ho jaate hain. Hardware I/O alag rakha hai jaan-boojh ke.
