# Phase 5A — JARVIS Human Voice Upgrade 🎙️

> **Kya update hua, kya fayda hua, aur kaam kaise karta hai** — poora hisaab.
> Date: 2026-09-26 · Status: ✅ IMPLEMENTED + TESTED (533 tests pass)

---

## TL;DR — ek line mein

JARVIS ab **Hindi neural awaaz mein Hinglish bolta hai** (pehle roboti English accent thi),
**sochte hi bolna shuru kar deta hai** (pehle poora jawab ka intezaar karta tha),
**beech mein bolke roka ja sakta hai** (pehle bilkul nahi),
aur **"Hey Jarvis" wake word ab 100% free hai** (koi API key nahi).

---

## 1️⃣ Hindi Neural Voice (hinglish_tts.py — NAYA FILE)

### Kya problem thi
English voice (en-GB-RyanNeural) Hinglish ko angrezi uchcharan se padhti thi:
"bhai, 2500 ka bill bhar do" → *"bay-hi, twenty-five hundred..."* — robot jaisa.
Hindi voices Devanagari padhti hain, roman text nahi.

### Kya kiya
1. **Voice auto-select**: `EDGE_VOICE=auto` (ab default) — text dekh ke decide:
   - Hinglish/Hindi → `hi-IN-MadhurNeural` (Jarvis-type Hindi male, neural, FREE)
   - Pure English → `en-GB-RyanNeural` (original Jarvis)
2. **Roman → Devanagari engine** (`saarthi/voice/hinglish_tts.py`):
   - **~370 common Hinglish shabdon ka dictionary** (bhai, kholo, chai, mummy...)
   - **Conservative rule-engine** unknown shabdon ke liye — jis shabd pe shak ho wo Latin rehta hai (galat Devanagari se accha)
   - Brands (paytm, youtube...) Latin hi rehte hain — Hindi voice waise bhi sahi padhti hai
3. **Hindi numbers**: `2500` → "do hazaar paanch sau" → `दो हज़ार पांच सौ` (Indian system: hazaar/lakh/crore), time `8:30` → "aath bajke tees"

### Live example (test se verified)
```
Input:  "mummy ko 350 bhej do aur mujhe batana"
Output: "मम्मी को तीन सौ पचास भेज दो और मुझे बताना"
Voice:  hi-IN-MadhurNeural
```

### Fayda
- **"Human ki voice" ka 80% yahi hai** — ab Jarvis sach mein HINDI mein baat karta hai
- ₹0 cost, koi API key nahi (edge-tts free hai)
- Chah to apni voice chuno: `EDGE_HINGLISH_VOICE=hi-IN-SwaraNeural` (female)

---

## 2️⃣ Streaming TTS (streaming.py — NAYA FILE)

### Kya problem thi
Agent ka poora jawab aane ka intezaar → phir bolna shuru. Lambe jawab pe user
5-10 second chup chaap wait karta tha. Voice mode slow FEEL hota tha.

### Kya kiya
- `SentenceBuffer` (pure logic): LLM ke tokens jodta hai, sentence poora hote hi nikal deta hai
- `StreamSpeaker` (async): sentences ki queue → **ek hi worker task sequentially bolta hai**
  - Order KABHI shuffle nahi hota (purane jarvis.py mein har sentence ka alag task tha — overlap ho sakta tha)
  - Naya turn shuru → purana speech turant cancel (`stop_speaking()`)
- Wire ho gaya: **VoiceSession** (voice mode) + **jarvis.py RealtimeStreamHandler** dono mein

### Flow
```
LLM stream ─ token ─ token ─ token ─┐
                                    ▼
                      SentenceBuffer (". ! ? ।" detect)
                                    │ sentence poora?
                                    ▼
                     StreamSpeaker queue ──► TTS bol raha hai #1
                                    │         #2 line mein ready
                                    ▼
                       user ko pehli awaaz ~1-2 sec mein
```

### Fayda
- **Pehli awaaz ~1-2 second mein** (pehle 5-10 sec)
- Lambe jawab bhi lagta nahi — bolte-bolte banta rehta hai
- Overlapping/gedbad speech bug khatam

---

## 3️⃣ Barge-in — beech mein tokna (audio.py mein add)

### Kya problem thi
Agent bol raha tha to tu chup baithna padta tha. "Ruk ja" bolne ka koi faida nahi —
wo khud ki awaaz sun nahi sakta tha.

### Kya kiya
- `BargeInDetector` (pure state machine, tested bina mic ke):
  - Bolna shuru hote hi mic loudness ka **baseline** banao (speaker ki awaaz jo mic tak aayi)
  - Baseline se **bahut upar, LAMBI awaaz** (5 consecutive chunks) = user bol raha hai → trigger
  - Ek-do spike (hichki/TV) pe trigger NAHI — reset hota hai
- `MicMonitor`: background thread mic sunta hai, RMS nikaalta hai
- `TTSEngine.stop_speaking()`: chalta hua playback process turant kill
  - EdgeTTS playback ab Popen + poll-loop hai (pehle blocking `subprocess.run` tha — rok hi nahi sakte the)
  - Windows MCI playback bhi cancel-aware (thread + stop command)
- **VoiceSession.speak() mein wire**: `VOICE_BARGE_IN=true` se on

### Imaandaar bat (honest limitation)
- **DEFAULT OFF hai.** Speakers pe agent ki apni awaaz mic mein echo hoti hai —
  false-trigger ho sakta hai (full echo-cancellation/AEC nahi hai).
- **Headphone pe bilkul reliable** — wahan `VOICE_BARGE_IN=true` kar do, magic hai.

### Fayda
- Real conversation jaisa — jaise Jarvis ko beech mein rok dete ho
- Fail-safe design repo ke rules ke saath: doubt ho to off, headphone pe on

---

## 4️⃣ Free Wake Word — openWakeWord (wake.py mein add)

### Kya problem thi
- Porcupine (best quality) ke liye **API key** chahiye thi (free hai par signup chahiye)
- Whisper-based `hey_jarvis` mode free tha par **heavy** (whisper chalta rehta hai)

### Kya kiya
Naya mode `WAKE_MODE=oww`:
- `openwakeword` package — **chhota ONNX neural model, ZERO API key**
- Pre-trained **"hey_jarvis"** model ke saath — naam se hi Jarvis project ke liye bana hai 😄
- Porcupine wala **frame-buffer lesson** apply kiya (mic 480-sample chunks, model 1280 maangta hai)
- Pehli baar chalane pe ~1-2 MB model auto-download
- Fallback: install nahi hai to push-to-talk pe chup-chaap aa jaata hai (agent kabhi nahi rukta)

### Setup
```bash
pip install openwakeword
# .env mein:
WAKE_MODE=oww
OWW_THRESHOLD=0.5   # optional tuning (zyada = strict)
```

### Fayda
- "Hey Jarvis" bolke jagana ab **bina kisi signup/key** ke
- Whisper-wake se **bahut kam CPU** — purane laptop pe bhi chalega (Pillar #3)

---

## 5️⃣ Hinglish TTS text rules (hinglish_tts.py ka hissa)

`prepare_text_for_speech` ke baad Hindi voice ke liye extra preparation:
- **Numbers** → Hindi words (₹2500 → rupay do hazaar paanch sau → रुपये दो हज़ार पांच सौ)
- **Time** → "aath bajke tees"
- **Markdown/emoji** pehle se saaf (pehle se tha)
- **Symbols** → words (₹ → rupay) (pehle se tha)

## 📁 Kaunsi file mein kya (changes map)

| File | Status | Kya hai |
|---|---|---|
| `saarthi/voice/hinglish_tts.py` | 🆕 NAYA | Script detect, Hindi numbers, roman→Devanagari, sentence split, SentenceBuffer |
| `saarthi/voice/streaming.py` | 🆕 NAYA | StreamSpeaker — sequential sentence queue |
| `saarthi/voice/audio.py` | ✏️ +140 lines | BargeInDetector + MicMonitor (thread) |
| `saarthi/voice/tts.py` | ✏️ modified | Auto voice select, Hinglish pipeline, cancel-aware playback, stop_speaking() |
| `saarthi/voice/wake.py` | ✏️ +170 lines | OpenWakeWordWake (oww mode) |
| `saarthi/voice/session.py` | ✏️ modified | Streaming TTS wiring + barge-in speak() |
| `jarvis.py` | ✏️ modified | RealtimeStreamHandler — SAB sentences sequential bolta hai |
| `tests/test_phase5a.py` | 🆕 NAYA | 44 naye tests (sab pure logic, mic ke bina) |
| `.env.example` | ✏️ | Naye config options documented |
| `requirements.txt` / `pyproject.toml` | ✏️ | edge-tts (recommended), openwakeword (optional) |

## ⚙️ Naye Config Options (.env)

```ini
# Voice auto-selection (DEFAULT: auto — recommended)
EDGE_VOICE=auto
EDGE_HINGLISH_VOICE=hi-IN-MadhurNeural    # Hinglish/Hindi ke liye
EDGE_ENGLISH_VOICE=en-GB-RyanNeural       # pure English ke liye
TTS_DEVANAGARI=true                        # roman → Devanagari pipeline

# Streaming + barge-in
VOICE_STREAMING_TTS=true                   # sentence-by-sentence bolna
VOICE_BARGE_IN=false                       # headphone pe true karo!

# Free wake word
WAKE_MODE=oww                              # + pip install openwakeword
OWW_THRESHOLD=0.5
```

## 🧪 Kaise verify karein

```bash
# 1. Sab tests (533 pass hone chahiye)
python run_tests.py

# 2. Voice setup check
python voice_cli.py --check

# 3. Bolke try karo:
python voice_cli.py            # ya: python jarvis.py --voice
# Bolo: "bhai 2500 ka bill bharne ka reminder lagao"
# → Hindi voice mein jawab aayega, pehla sentence turant

# 4. Wake word (ek baar):
pip install openwakeword
WAKE_MODE=oww python voice_cli.py
# "Hey Jarvis!" bolke jagao
```

## 🚦 Kya nahi badla (jaan-boojh ke)

- **Safety layer** — OTP/payment blocks waise hi hain
- **Purane TTS backends** — piper/espeak/sab waise hi kaam karte hain
- **Bina edge-tts ke** — espeak pe fallback ho jaata hai, kuch nahi toota
- **Barge-in default off** — fail-safe philosophy
- 489 purane tests mein **zero change** — sab waise ke waise pass

## 📊 Pehle vs Ab

| Cheez | Pehle | Ab |
|---|---|---|
| Hinglish voice | English accent, roboti | Hindi neural (Madhur), natural |
| "2500" bolna | "twenty-five hundred" | "दो हज़ार पांच सौ" |
| Pehli awaaz | Poore jawab ke baad (5-10s) | Pehle sentence pe (~1-2s) |
| Beech mein tokna | ❌ Impossible | ✅ VOICE_BARGE_IN=true se |
| "Hey Jarvis" wake | Key chahiye (Porcupine) ya heavy (Whisper) | ✅ FREE, halka neural model |
| Speech order | Overlap ho sakta tha | ✅ Guaranteed sequential |

## Aage kya (Phase 5B — next)

1. **Vector memory** (ChromaDB) — "pichle mahine wali baat" semantic recall
2. **Persistent scheduler** — reminders restart-proof
3. **Proactive mode** — "Good morning, aaj 3 kaam hain..."
4. **Telegram bot** — phone se ghar ke agent ko command
5. **CI** — GitHub Actions pe 533 tests auto-run

---
*Ye upgrade repo ke rules ke andar hai: safety layer untouched, sab dependencies optional/free (₹0), purane hardware pe chalega.*
