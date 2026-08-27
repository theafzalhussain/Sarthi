# SAARTHI 🛕

**Ek personal AI agent jo Hinglish samajhta hai aur tere devices chalata hai.**

सारथी = rath chalane wala. Jo raasta jaanta hai aur khud chalata hai.

```
tu     > bhai paytm khol ke dhai hazaar ka bijli ka bill bhar de
saarthi> Paytm khol diya. Electricity section pe hun.
         Ruk ja — ₹2500 ka payment hai. Confirm kar?
```

---

## Ye kyun banaya (aur kaise alag hai)

Global AI agents (Gemini, Siri) technically strong hain, par **Hinglish pe girte hain**:

| Problem | Data |
|---|---|
| Code-mixed queries pe task success **20-45% girta** hai | [Exotel/arXiv research](https://next.exotel.com/blog/hinglish-conversational-ai-benchmarks-for-indian-banks/) |
| Indic code-switched speech pe **25-35% word error rate** | [Mihup](https://mihup.ai/blog/realtime-agent-assist-indic-languages-how-it-works) |
| **250 million+ log** Hindi-English mix bolte hain | [HiACC study, NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC12329218/) |
| Standard ASR models code-switching ke liye **bane hi nahi** the | [Deepgram](https://deepgram.com/learn/hinglish-voice-ai-speech-recognition) |

*(Content licensing ke liye rephrase kiya gaya)*

SAARTHI ke 4 pillars isi gap pe bane hain:

| # | Pillar | Kya matlab |
|---|---|---|
| **1** | **Hinglish-first** | Code-switching native hai, bolt-on nahi. "dhai hazaar" → 2500 |
| **2** | **Dikha Do Mode** | Ek baar dikha, hamesha yaad — aur UI badle to **khud theek ho jaata hai** |
| **3** | **Budget hardware** | Python 3.9+, SQLite, screen-size-relative coords. Purana laptop, sasta phone — chalega |
| **4** | **Indian apps** | 120+ apps ka package database — Paytm, IRCTC, DigiLocker, Swiggy, PhonePe, Groww |

---

## ₹0 setup (5 minute)

### 1. Free API key le

| Provider | Link | Kis liye |
|---|---|---|
| **NVIDIA** 🏆 | https://build.nvidia.com | **Ek key se 4 models** — deepseek v4 pro, nemotron, muse glimmer, diffusiongemma |
| **Groq** ⭐ | https://console.groq.com | Sabse fast. **Alag limit** — NVIDIA khatam ho to ye bacha lega |
| **Gemini** ⭐ | https://aistudio.google.com/apikey | Screenshot dekhne ke liye (vision) |
| OpenRouter | https://openrouter.ai/keys | 98 free models ka router (optional) |
| Bluesminds | https://api.bluesminds.com | GPT-4o/GPT-5.6 gateway (optional) |

Sab free hain. **Credit card nahi maangte.**

**Salah: NVIDIA + Groq dono le le.** Dono ki limit alag hai — ek khatam ho
to doosra chalta rahega. Total **8 providers** ka fallback ban jaata hai.

> ⚠️ Dhyan: ChatGPT Plus / Claude Pro subscription se API **nahi** chalti — wo alag cheez hai. Isliye upar wale free tiers use kar.

### 2. Install

```bash
git clone <tera-repo-url>
cd saarthi

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env kholke NVIDIA_API_KEY aur GROQ_API_KEY daal
```

### 3. Test kar (10 second)

```bash
python run_tests.py
```

360 tests, koi extra install nahi chahiye. Sab pass hone chahiye.
Kuch fail ho to **pehle wahi theek kar**.

### 4. Chala

```bash
python cli.py
```

Bas. Kuch aur nahi chahiye.

### 4. Voice chahiye? (optional)

```bash
pip install faster-whisper sounddevice
sudo apt install libportaudio2 espeak-ng    # Linux

python voice_cli.py --check     # setup check
python voice_cli.py             # bolke chala
```

Detail: [docs/VOICE.md](docs/VOICE.md)

---

## Phone control (optional, Phase 3)

Laptop se phone chalane ke liye ADB setup:

```bash
# 1. Phone pe: Settings > About phone > Build number pe 7 baar tap
#    (Developer Options unlock ho jaayega)
# 2. Settings > Developer options > USB Debugging ON
# 3. USB cable laga
# 4. Check kar:
adb devices
#    Phone pe popup aayega -> Allow

# 5. Test — tera phone khud tap karega:
adb shell input tap 500 500
```

Cable ke bina (WiFi):
```bash
adb tcpip 5555
adb connect <phone-ka-ip>:5555
```

Phir SAARTHI mein: `/devices` — android "connected" dikhega.

---

## Kaise use kare

Normal Hinglish mein bol:

```
paytm kholo
mere phone me kya notifications hain
internet pe dhoondh IRCTC tatkal ka time
yaad rakh ki mummy ka number 98765xxxxx hai
laptop pe batao kitni disk space bachi hai
screen pe kya hai dekh ke bata
```

### Dikha Do Mode — naya kaam sikhana

```
tu     > dekh, ye kaam yaad kar le
saarthi> Recording ON hai. Bata kya karna hai.

tu     > paytm khol, Electricity pe tap kar, 2500 daal
saarthi> [karta hai, saath mein steps yaad rakhta hai]

tu     > isko "bijli ka bill" bol de
saarthi> Skill save ho gayi (3 steps). Agli baar amount batana padega.
```

**Agle mahine:**
```
tu     > bijli ka bill bhar de 1240 ka
saarthi> Kar diya.
```

**Aur jab Paytm apna UI badal dega?**
```
saarthi> Dhyan de: 1 step khud theek karna pada — app ka UI badla lagta hai.
         Skill update kar di hai.
```

Normal automation (Tasker, macros) yahin toot jaate hain. SAARTHI screen padh ke naya button dhoondh leta hai.

### Voice mode

```bash
python voice_cli.py
```

```
[Enter dabao aur bolo]
  >>> sun raha hun...
  fix  suna: "pay time cholo" -> samjha: "paytm kholo"
  tu > paytm kholo
  saarthi > Paytm khol diya bhai.
```

Risky kaam pe bolke confirmation maangta hai:

```
  !!! Ruk ja. 2500 rupay bhejna hai. kisko mummy. Karu? Haan ya nahi bol.
  tu > haan bhai kar de
  ok  kar raha hun
```

**Kuch samajh na aaye to mana kar deta hai** (fail-safe) — chup-chaap paise nahi jaate.

### CLI commands

| Command | Kaam |
|---|---|
| `/status` | Sab kuch ka status |
| `/devices` | Connected devices |
| `/skills` | Seekhi hui skills |
| `/memory` | Yaad rakhi baatein |
| `/tools` | 39 tools ki list |
| `/browser` | Browser kaise khulega — tab switch setting |
| `/auto` | Full access — risky kaam bina puche |
| `/retry` | Hate hue providers dobara try karo |
| `/verbose` | Tool results dikhao/chhupao |
| `/reset` | Baat bhool jao (memory safe) |
| `/quit` | Band karo |

---

## Kya kaam karta hai, kya nahi (imaandaar list)

### ✅ Ab kaam karta hai
- Hinglish samajhna (numbers, apps, intent, risky detection)
- **Voice — bolke command dena aur jawab sunna** (offline, free)
- **Hinglish-tuned speech recognition** — "pay time cholo" → "paytm kholo"
- Laptop control — shell, files, apps
- Internet — search + website padhna
- Memory — facts aur purani baatein
- Android control ADB ke through (phone connected ho to)
- Dikha Do Mode — skill record, replay, self-heal
- 39 tools, safety layer + **voice confirmations**
- **Browser automation** (Playwright) — koi bhi website, aur tera tab
  kabhi hijack nahi hota
- **8 LLM providers** with smart fallback — dead provider session bhar
  hat jaata hai, rate-limit wala cooldown pe
- **Professional English interface, par baat teri bhasha mein** — English
  mein pucho English mein jawab, Hinglish mein pucho Hinglish mein
- **360 tests** — `python run_tests.py`

### 🚧 Abhi nahi (roadmap pe hai)
- **Standalone Android app** — abhi laptop ki zarurat hai (Phase 4)
- **User ke taps sunna** — abhi agent ke apne actions record hote hain. Tere manual taps record karne ke liye Accessibility Service chahiye (Phase 4)
- **Barge-in** — agent bol raha ho tab tokna (echo cancellation chahiye)
- **Vector memory** — semantic recall (ChromaDB, Phase 5)

### ❌ Kabhi nahi hoga (aur kyun)
| Cheez | Wajah |
|---|---|
| **iPhone ka full control** | Apple ka sandbox allow nahi karta. Technically impossible without jailbreak |
| **OTP/PIN/password type karna** | Jaan-boojh ke block kiya hai. Agent galti kare to account chala jaayega. Tu khud daalega |
| **Final payment button dabana** | Agent screen tak le jaayega, confirm tu karega. Banking apps automation detect karke block bhi karte hain |
| **Kisi aur ka device** | Sirf apne devices. Bina permission illegal hai |

---

## Safety

Ye agent ke paas device ka access hai — isliye brake zaroori hai:

- **Hard blocks:** OTP/PIN/password type karna, `rm -rf /`, fork bomb, disk format, `curl | bash`
- **Confirmation:** paise, delete, message bhejna, shell commands, skill chalana
- **Fail-safe:** confirmation ka koi tareeka na ho → **mana kar deta hai** (chup-chaap nahi karta)
- **Blind tap protection:** UI badal gaya aur sahi button na mile → purane coordinates pe tap karne se **pehle puchta hai** (warna galat button dab sakta hai)

`.env` mein `SAARTHI_CONFIRM_RISKY=false` karna **khatarnak** hai. Mat kar.

---

## Project structure

```
saarthi/
├── brain/      8 LLM providers + fallback + provider health
├── lang/       Hinglish layer — PILLAR #1
├── voice/      Bolna/sunna — Hinglish-tuned STT, TTS, wake word
├── devices/    Universal device adapters — android, desktop, browser
├── tools/      39 tools + safety layer
├── memory/     SQLite yaaddasht
├── skills/     DIKHA DO MODE — store, recorder, self-healing runner
├── ui.py       Terminal UI — pura look ek jagah
├── config.py   Settings
└── agent.py    Main loop
cli.py              Text interface
voice_cli.py        Voice interface
run_tests.py        360 tests — koi install nahi chahiye
hardware_check.py   Mic/speaker/phone diagnostic
tests/              Test suite (8 bugs ka regression guard)
```

---

## Testing

```bash
python run_tests.py              # sab — 360 tests, 0.1 second
python run_tests.py known_bugs   # sirf bug regression tests
```

**Koi extra install nahi chahiye** — stdlib `unittest` use hota hai
(₹0 budget, purana laptop). pytest ho to `pytest tests/` bhi chalega.

Tests **hardware ke bina** chalte hain — mic, phone, browser, internet
kuch nahi chahiye.

**Har fix hue bug ka apna named test hai:**
```
test_bug1_paytm_youtube_match_nahi_karta
test_bug3_semantic_healing_coordinates_se_pehle_hai
test_bug7_user_ka_navigate_kiya_tab_detect_hota_hai
```
Fail hone pe seedha samajh aata hai ki kya toota.

**Hardware test** (ye sirf tu kar sakta hai):
```bash
python hardware_check.py                # sab kuch

# Voice mein problem ho to — GUESS mat kar, MEASURE kar:
python hardware_check.py --mic-scan     # kaunsa mic sach mein sunta hai
python hardware_check.py --stt-tune     # galat suna? best Whisper setting
python hardware_check.py --mic-live     # "kuch sunai nahi diya" aata ho to
python hardware_check.py --mic-stream   # mic se sirf 0 aa raha ho to
```
Detail: **[HARDWARE_TEST.md](docs/HARDWARE_TEST.md)**

**Docs:**
**[UPDATE.md](docs/UPDATE.md) — 👈 `git pull` kaam nahi kar raha? YE padho** ·
**[HANDOFF.md](docs/HANDOFF.md) — naya developer/AI ho to YE pehle padho (pura context)** ·
[ARCHITECTURE.md](docs/ARCHITECTURE.md) — code kaise organize hai ·
[HARDWARE_TEST.md](docs/HARDWARE_TEST.md) — mic/speaker/phone test ·
[VOICE.md](docs/VOICE.md) — voice setup + Hinglish tuning ·
[DEPLOYMENT.md](docs/DEPLOYMENT.md) — server, bijli, hardware ·
[ROADMAP.md](docs/ROADMAP.md) — aage kya

---

## Requirements

- **Python 3.9+** (purane laptop pe bhi chalega)
- Internet (LLM API ke liye)
- ADB (optional — sirf phone control ke liye)
- 4GB RAM kaafi hai

---

## Ek baat

Ye project ek student ne ₹0 budget pe banaya hai — mehnat aur dimag se.

Agar tu bhi apna agent bana raha hai: **choti cheez se shuru kar, aur unique wedge pakad.** "Sab kuch karne wala agent" duniya ka sabse crowded idea hai. "Hinglish samajhne wala, sasta phone pe chalne wala, dikha ke sikhaya jaane wala agent" — ye tera hai.

**Sirf apne devices pe use kar.**
