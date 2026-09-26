# SAARTHI / J.A.R.V.I.S. — Full Codebase Analysis & Upgrade Plan

> Scan date: 2026-09-26 · Branch: `arena/01a0dcf2-sarthi` · Base commit: `40722c2`
> **Verdict: Project solid hai. Foundation world-class hai. Ab isko "human-like powerful agent" banane ke liye 5 jagah upgrade chahiye.**
>
> ⚡ **UPDATE: Phase 5A (items 1-5 — Hindi TTS, Streaming TTS, Hinglish rules, Barge-in, Free wake word) IMPLEMENT HO GAYA.** Detail: [PHASE5A_UPDATE.md](PHASE5A_UPDATE.md) · 533 tests pass.
>
> ⚡ **UPDATE 2: Phase 5B bhi HO GAYA** — Persistent scheduler, Proactive mode, Vector memory, Telegram bot, GitHub CI. Detail: [PHASE5B_UPDATE.md](PHASE5B_UPDATE.md) · **555 tests pass**.
>
> ⚡ **UPDATE 3: Phase 5C bhi HO GAYA** — Web UI auth (G5 fix), Email tools, Hinglish Calendar, Multi-step Planner, History compaction · **68 tools, 592 tests**. [PHASE5C_UPDATE.md](PHASE5C_UPDATE.md)

---

## PART 1 — Abhi kya-kya hai (Full Inventory)

### 📊 Numbers (scan se verify kiye gaye)

| Metric | Value |
|---|---|
| Python code | **35,712 lines** (23,862 `saarthi/` + tests + CLI) |
| Kotlin (Android app) | **1,381 lines** (8 files, Compose + Accessibility) |
| Tools | **58 tools** (naam se count kiye) |
| LLM providers | **10+** (Groq, OpenRouter, Gemini, NVIDIA, Ollama, Kiro, Unikey, Bluesminds, OpenCode, Kira) |
| Tests | **489 passed + 170 subtests** ✅ (sandbox mein chala ke verify kiya) |
| Docs | 13 files — ARCHITECTURE, ROADMAP, VOICE, PHONE_SETUP... |
| Phases complete | 1 ✅ 2 ✅ 3 ✅ 4A ✅ 4B ✅ · **Phase 5 (Powerful) = NEXT** |

### 🏗️ Architecture (jo kaam karta hai)

```
Voice/Text → lang/normalize (Hinglish parse, 120+ apps, 18 intents)
           → agent.run_turn (hints + memory + skills + tools → LLM)
           → brain/router (multi-provider fallback, streaming, health tracking)
           → tools/registry (safety: HARD BLOCK / CONFIRM / SAFE)
           → devices (Android ADB · Android Accessibility HTTP · Desktop · Browser Playwright)
           → memory (SQLite facts + history) → jawab (voice/TTS ya text)
```

### ✅ Strong points (inhe todna mat)

1. **Safety layer** — OTP/PIN/password hard-block, payment confirmation, fail-safe design. Ye is project ki jaan hai.
2. **Hinglish pillar** — pre-analyzed hints LLM ko jaate hain (raw text nahi). 55 ASR correction rules. "die hazaar" → 2500 sahi detect hota hai.
3. **Skills + 3-level self-healing** — record/replay, semantic healing (research-paper level cheez).
4. **Multi-provider brain** — ek provider fail → agla. Free tier pe ye critical hai.
5. **Testing culture** — 489 tests, pure-logic separation (mic ke bina voice core test ho jaata hai).
6. **Docs Hinglish mein** — onboarding aasaan.

### 🎙️ Voice system (abhi ka status)

| Component | Abhi | Quality |
|---|---|---|
| STT | faster-whisper (offline, tiny→large) + Hinglish biasing | ✅ Accha |
| TTS | 6 backends — piper / espeak / say / pyttsx3 / **edge-tts** (en-GB-RyanNeural) / null | ⚠️ English voice roman Hinglish padhti hai |
| Wake word | push-to-talk / energy / Porcupine ("Hey Jarvis") | ✅ Kaam karta hai |
| Streaming ASR | ❌ Nahi — poora bolne ke baad transcribe | Gap |
| Barge-in (beech mein tokna) | ❌ Nahi — echo cancellation chahiye | Gap |
| Hindi pronunciation | ❌ Roman text English voice se padha jaata hai | **Sabse bada voice gap** |

---

## PART 2 — KAMIYAN (gaps jo maine pakde)

### 🔴 Critical gaps (Jarvis feel ke liye zaroori)

| # | Gap | Detail |
|---|---|---|
| G1 | **Voice insani nahi hai** | edge-tts default `en-GB-RyanNeural` hai. Hinglish reply Hindi voice se nahi bolta. "Madhur" ya "Swara" jaisi natural Hindi awaaz ka use nahi ho raha. |
| G2 | **Reminders restart pe mar jaate hain** | `reminder_set` sirf `asyncio.create_task` hai — PC restart = reminder gayab. Koi persistence nahi. |
| G3 | **Semantic memory nahi hai** | SQLite keyword search hai. "Wo cheez jo pichle mahine discuss hui thi" nahi milta. ChromaDB roadmap mein tha, abhi tak nahi. |
| G4 | **Koi proactive behavior nahi** | Agent sirf react karta hai. Khud kuch nahi bolta ("bill kal due hai", "meeting 10 min mein"). Scheduler daemon nahi hai. |
| G5 | **Web UI pe koi auth nahi** | `web/app.py` mein `/api/chat`, `/v1/chat/completions` pe token check nahi mila. LAN pe koi bhi agent ko command de sakta hai. Phone side secure hai, laptop web side nahi. |
| G6 | **CI nahi hai** | 489 tests hain lekin `.github/` folder hi nahi — push pe koi test nahi chalta. |

### 🟡 Missing integrations (ek asli Jarvis ke paas ye hote hain)

- ❌ **Email** (Gmail/IMAP) — na padhna na likhna
- ❌ **Calendar** (Google Calendar API)
- ❌ **Telegram/WhatsApp bot** — phone se laptop ke agent ko bolna (roadmap mein tha, abhi nahi)
- ❌ **Weather / News / Translate** dedicated tools
- ❌ **Music streaming control** (YouTube Music/Spotify dedicated tool)
- ❌ **Smart home** (Home Assistant/MQTT — optional)

### 🟢 Nice-to-have polish

- History compaction (purani baatein summarize nahi hoti, sirf `trim_history` cut karta hai)
- Streaming TTS (LLM bol raha hai tabhi bolna shuru — abhi poora jawab aane pe bolta hai)
- Barge-in + echo cancellation
- Voice cloning (XTTS-v2/F5-TTS) — apni pasand ki Jarvis awaaz
- Plugin system (third-party tools auto-load)
- Docker setup

---

## PART 3 — UPGRADE PLAN (Priority order)

### 🥇 PHASE 5A — "Awaaz insani banao" (sabse pehle — ye tere Jarvis ka dil hai)

| Kaam | Kaise | Effort | Fayda |
|---|---|---|---|
| **1. Hindi neural TTS default** | edge-tts voices: `hi-IN-MadhurNeural` (male, Jarvis-type), `hi-IN-SwaraNeural` (female). Devanagari voice ko roman Hinglish nahi padh sakti — isliye chhota **roman→Devanagari transliterator** likhna padega (indic-transliteration lib ya custom map) | 2-3 din | "Human ki voice" ka 80% yahi hai |
| **2. Streaming TTS** | LLM stream se pehla complete sentence milte hi TTS start karo (sentence-boundary chunking). Abhi poora jawab ka intezaar | 1-2 din | Response feel 2-3x fast |
| **3. Hinglish TTS rules** | TTS se pehle text prepare karo: numbers → Hindi words ("2500" → "do hazaar paanch sau"), English tech words as-is rakho | 1 din | Natural sunai deta hai |
| **4. Barge-in (tokna)** | Speaker hone pe mic energy check + webrtc-audio-processing (AEC). Pehle simple version: TTS ke time mic mute, phir VAD-based | 3-4 din | Real conversation feel |
| **5. Free wake word option** | `openWakeWord` — bilkul free, koi API key nahi (Porcupine key maangta hai) | 1 din | Zero-friction setup |

### 🥈 PHASE 5B — "Agent ko dimaag do"

| Kaam | Kaise | Effort | Fayda |
|---|---|---|---|
| **6. Vector memory (ChromaDB)** | `fastembed`/`sentence-transformers` (free, offline) + ChromaDB. `memory/store.py` ke saath parallel rakho — facts embedding ho, recall semantic ho | 2-3 din | "Wo cheez batao jo... " type recall |
| **7. Persistent Scheduler** | SQLite-backed `scheduler.py` daemon: reminders PC restart ke baad bhi zinda, recurring tasks ("roz subah 8 baje news batao"), missed reminders catch-up | 2-3 din | G2 fix — Jarvis ka core duty |
| **8. Proactive mode** | Scheduler se linked: due bills, calendar events, morning briefing ("Good morning, aaj 3 kaam hain...") | 2 din | Agent khud bolega — asli Jarvis |
| **9. Multi-step Planner** | Bade task ko plan banao (steps list) → execute → verify → fail pe re-plan. `_classify_task_size` already hai, usko extend karo | 3 din | Complex kaam autonomous |
| **10. History compaction** | 40 messages se purane turns ka LLM-summary banao, context mein sirf summary rakho | 1 din | Lambi baat-cheet memory |

### 🥉 PHASE 5C — "Jarvis ka network"

| Kaam | Kaise | Effort | Fayda |
|---|---|---|---|
| **11. Telegram bot** | `python-telegram-bot` (free). Phone se message bhejo, ghar ka agent kaam kare. Voice notes bhi chalte hain (STT already hai!) | 2 din | Laptop on, tu bahar — phir bhi control |
| **12. Email tool** | Gmail API (free, OAuth) ya IMAP/SMTP. Padhna SAFE, bhejna CONFIRM | 2-3 din | "Bhai Rahul ko mail kar de" |
| **13. Calendar tool** | Google Calendar API free. Events padho/banao + proactive reminders se jodo | 2 din | "Kal kya hai mera?" |
| **14. Weather + News + Translate** | Open-Meteo (keyless), RSS/Hindi news scrape, free translate | 1 din | Roz ke sawaal |
| **15. Web UI auth** | LAN binding pe token/PIN auth (`SAARTHI_WEB_TOKEN`), pehli baar browser mein PIN | 1 din | G5 security fix |

### 🏅 PHASE 5D — Infra polish

- **GitHub Actions CI**: pytest + ruff (489 tests already hain — bas chalana) — G6 fix
- Docker + `requirements-voice.txt` (abhi commented hain)
- Hinglish eval set: 50 golden commands, har parse change pe compare
- Plugin system: `~/.saarthi/plugins/` se tools auto-load
- Desktop overlay HUD (transparent always-on-top arc reactor)

---

## PART 4 — Suggested order (meri recommendation)

```
Week 1: 5A-1 Hindi TTS + 5A-3 Hinglish TTS rules   ← sabse zyada feel badlega
Week 2: 5B-7 Scheduler + 5B-8 Proactive            ← "jarvis jo khud kaam kare"
Week 3: 5B-6 Vector memory + 5A-2 Streaming TTS
Week 4: 5C-11 Telegram + 5D CI                      ← phone se control + safety net
Baad:   Email, Calendar, Barge-in, Planner, baaki sab
```

**Rule (repo ke ROADMAP wala):** Ek waqt pe ek pillar. Safety layer kabhi mat todo.

---

## PART 5 — Jo KABHI nahi karna (repo ki rules ke saath)

| Cheez | Wajah |
|---|---|
| OTP/PIN/password typing | Hard block — negotiable nahi |
| Final payment button | Agent le jaayega, tu dabayega |
| WhatsApp auto-send bina confirmation | Spam/ghalat message risk — CONFIRM level pe rakhna |
| iPhone full control | Apple sandbox — sirf Shortcuts |
| Kisi aur ka device | Illegal |
| Voice cloning kisi aur ki awaaz ki | Legal/ethical issue — sirf apni ya synthetic voice |

---

*Report: full-scan ke baad banayi gayi. Tests verify hue: `489 passed, 170 subtests passed`.*
