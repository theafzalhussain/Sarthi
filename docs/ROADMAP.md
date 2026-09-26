# Roadmap

Kahan pahunche hain, aage kya. Sab ₹0 budget pe possible.

---

## ✅ Phase 1 — Foundation (HO GAYA)

- Multi-provider LLM brain (Groq + Gemini + OpenRouter, auto-fallback)
- Hinglish layer — 120+ apps, 18 intents, Hindi numbers, risky detection
- Universal device adapters (Android via ADB + Desktop)
- 39 tools + safety layer
- SQLite memory (facts + conversation history)
- Dikha Do Mode — record, replay, 3-level self-healing
- CLI

**Chalane ke liye:** `python cli.py`

---

## ✅ Phase 2 — Voice (HO GAYA)

- **Hinglish-tuned STT** — biasing (`initial_prompt`) + 55 correction rules + context-aware rules
- **Speech-to-text** — faster-whisper, offline, model size configurable (tiny→large)
- **Text-to-speech** — 5 backends (piper/say/espeak/pyttsx3/null) with auto-select
- **Wake word** — 3 modes (push-to-talk default / energy / Porcupine)
- **Silence detection** — auto noise calibration, works in noisy rooms
- **Voice confirmations** — risky kaam pe bolke "haan/nahi", fail-safe
- **Vocabulary boost** — memory + skills se Whisper ko bias karta hai (compounding fayda)
- Quality gates — Whisper ke hallucinations (`"Thank you."`) filter hote hain

**Chalane ke liye:**
```bash
python voice_cli.py --check    # setup diagnostic
python voice_cli.py            # bolke chala
python voice_cli.py --once     # ek baar test
```

Detail: [VOICE.md](VOICE.md)

**Measured fayda:** "pay time cholo aur die hazaar ka bell bhar do" —
bina correction amount **1000** (galat), correction ke saath **2500** (sahi).
₹1500 ka farak.

### Jo abhi bhi nahi hai
- Barge-in (agent bol raha ho tab tokna) — echo cancellation chahiye
- Perfect Hindi pronunciation — roman text ko English voice padhti hai
- Real-time streaming — pura bolne ke baad transcribe hota hai

---

## ✅ Phase 3 — Browser + Phone polish (HO GAYA)

### Browser device ("saari websites ka access") ✅
```python
# devices/browser.py — 800+ lines, fully operational
class BrowserDevice(Device):
    kind = "browser"
    capabilities = {TAP, TYPE, SCREENSHOT, UI_TREE, SWIPE, LAUNCH_APP, ...}
```
Playwright se — DOM hi `ui_tree` ban jaata hai, isliye `tap_text` aur **self-healing dono automatically kaam karte hain**. Tab-hijack protection, persistent login, smart partial text matching (YouTube/Google results pe kaam karta hai).

### Phone polish ✅
- ✅ Multiple devices ek saath (`adb -s`) — `list_adb_serials()`, auto-enumerate, `SAARTHI_ANDROID_SERIAL` pin
- ✅ Screenshot caching (max 2, dedupe via SHA256 hash — free tier tokens bachao)
- ✅ Retry logic (whitelist-based: read-only commands retry, `input tap` KABHI nahi)

### v2.0 Enhancements ✅
- ✅ Streaming responses (token-by-token real-time output)
- ✅ Parallel tool execution (independent tools via asyncio.gather)
- ✅ 9 LLM providers with auto-fallback + health tracking
- ✅ Chain-of-thought reasoning + advanced multi-task prompt
- ✅ 0.8s first token (Groq primary) vs 4-6s before

---

## 🎯 Phase 4 — Android App (bada milestone)

Abhi laptop ki zarurat hai. Iske baad phone khud chalega.

### ✅ Phase 4A — Python Side (HO GAYA)

USB cable / ADB ke bina phone control — HTTP-based AccessibilityDevice adapter.

| Kaam | Status |
|---|---|
| `AccessibilityDevice` class (httpx HTTP client) | ✅ |
| Token-based auth (constant-time compare, `secrets.compare_digest`) | ✅ |
| No SHELL capability (security rule) | ✅ |
| DeviceManager registration (`phone` + `android` alias) | ✅ |
| `phone_se_seekho` tool (phone se recorded actions → Skill) | ✅ |
| 29 contract + security + registration tests | ✅ |
| HTTP contract defined (Kotlin app isi ko implement karega) | ✅ |

**Architecture (phone = SERVER, laptop = CLIENT):**
```
   LAPTOP (Python agent)                    PHONE (Kotlin app)
   ─────────────────────                    ──────────────────
   AccessibilityDevice(Device)  ──HTTP──>   HTTP server (localhost:8080)
     .tap(x, y)                 POST /tap        │
     .ui_tree()                 GET  /ui_tree    ▼
     .tap_text("Send")                      AccessibilityService
                                              (asli tap karta hai)
```

Kyun ye direction: ADB ka exact mirror — laptop se phone ko command. Agent,
tools, skills, self-healing — kisi mein ek line nahi badli.

### ✅ Phase 4B — Android App (Kotlin) — HO GAYA

| Kaam | Tech |
|---|---|
| App | Kotlin + Jetpack Compose |
| Screen control | **AccessibilityService** |
| Background | Foreground Service |
| Notifications | NotificationListenerService |
| HTTP server | NanoHTTPD (single file, Apache-2.0) |

**Ban gaya:** `android/` folder, 1,340 lines Kotlin, 8 files.
Saare 14 endpoints implement hue aur Python client ke contract se
**exactly match** karte hain (`ui_tree`, `notifications`,
`recorded_actions` ke JSON keys verify kiye gaye).

Security verified — 8/8 points:
SecureRandom 32-char token · `MessageDigest.isEqual` constant-time
compare · sirf private IP (public/mobile data pe server band ho jaata
hai) · default OFF · `isPassword` node ka text khali · recording mein
`{PASSWORD}` placeholder · **koi `/shell` endpoint nahi** · koi logging
nahi. Plus `/type` pe apna OTP/PIN/CVV block (do-tarfa defense).

Manual test checklist: [PHASE4B_TEST.md](PHASE4B_TEST.md)

### Asli inaam: user ke taps sunna

Abhi recorder **agent ke apne** actions record karta hai. Accessibility Service ke baad **tere manual taps** record honge — matlab sach mein "dikha do" mode. Phase 4A ka `phone_se_seekho` tool already ye data accept karta hai.

Achhi khabar: `skills/store.py` ka data format **same rahega**. Store aur runner dobara nahi likhna padega. Sirf ek naya recorder source.

⚠️ **Google Play policy:** autonomous accessibility agents publish karna allowed nahi hai. **Personal use / sideload bilkul theek hai.** Isko product banake bechne ka plan mat bana.

---

## ✅ Phase 5A — Human Voice (HO GAYA)

JARVIS ab sach mein insaan jaisa bolta hai. Detail: [PHASE5A_UPDATE.md](PHASE5A_UPDATE.md)

| Kaam | Status |
|---|---|
| Hindi neural voice — `hi-IN-MadhurNeural` auto-select + roman→Devanagari engine (~370 shabd dict + rules) | ✅ |
| Hindi numbers TTS mein — "2500" → "दो हज़ार पांच सौ", time "8:30" → "aath bajke tees" | ✅ |
| Streaming TTS — LLM ka pehla sentence aate hi bolna shuru (VoiceSession + jarvis.py dono) | ✅ |
| Barge-in — bolte waqt beech mein tokna (VOICE_BARGE_IN=true; headphone pe reliable) | ✅ |
| Free wake word — `WAKE_MODE=oww` (openwakeword "hey_jarvis", zero API key) | ✅ |
| 44 naye pure-logic tests — total **533 tests pass** | ✅ |

## ✅ Phase 5B — Powerful (HO GAYA)

Detail: [PHASE5B_UPDATE.md](PHASE5B_UPDATE.md)

| Kaam | Status |
|---|---|
| Persistent scheduler (SQLite) — restart-proof reminders, daily/weekly recurrence, missed catch-up | ✅ |
| Proactive mode — reminders pe JARVIS khud bole + session-start briefing | ✅ |
| Vector memory — trigram-TFIDF semantic recall (offline, zero dep) + agent context injection | ✅ |
| Telegram bot — phone se text/voice note command, whitelist security, risky auto-deny | ✅ |
| Streaming TTS | ✅ (Phase 5A mein ho chuka tha) |
| GitHub Actions CI — Python 3.10/3.11/3.12, full suite (555 tests) | ✅ |

## 🎯 Phase 5C — Powerful banao (baaki)

| Kaam | Kyun |
|---|---|
| Web UI auth (token/PIN) | LAN pe bhi lock — G5 |
| Skill chaining | Ek skill doosri ko call kare |
| On-device LLM | Gemma 4 12B / Qwen3.6 — privacy + no rate limit |
| Multi-step planning | Bade kaam automatically todna |
| Email + Calendar tools | Gmail/Google Calendar API |
| History compaction | Purani baatein LLM-summary mein |

---

## Ye ab bhi kabhi nahi hoga

| Cheez | Wajah |
|---|---|
| iPhone full control | Apple sandbox. Sirf Shortcuts tak |
| OTP/PIN/password type karna | Jaan-boojh ke block. Security rule, negotiable nahi |
| Final payment button | Agent le jaayega, tu dabayega. Banking apps automation detect karte hain |
| Kisi aur ka device | Illegal. Sirf apne devices |

---

## Priority (mera suggestion)

```
1. ✅ Phase 1 (Foundation)    <- HO GAYA
2. ✅ Phase 2 (Voice)         <- HO GAYA
3. ✅ Phase 3 (Browser+Polish) <- HO GAYA (v2.0)
4. ✅ Phase 4A (Python side)   <- HO GAYA — HTTP contract + tests
   ✅ Phase 4B (Kotlin app)   <- HO GAYA — 1,340 lines, security 8/8
5. ✅ Phase 5A (Human Voice)   <- HO GAYA — Hindi TTS + streaming + barge-in + free wake word
   ✅ Phase 5B (Powerful)     <- HO GAYA — scheduler + proactive + vector memory + Telegram + CI
   🎯 Phase 5C (Advanced)     <- NEXT — web auth, email/calendar, planner
```

---

## Har phase mein ye yaad rakh

1. **Ek waqt pe ek pillar.** Sab ek saath karne se kuch bhi accha nahi banega.
2. **Safety layer mat todo.** Feature add kar, brake mat hatao.
3. **Budget hardware test kar.** Apne sabse purane phone pe chala ke dekh — Pillar #3 yahi hai.
4. **Hinglish test cases likh.** `lang/` badle to purane commands verify kar.
5. **Har phase ke baad GitHub pe push kar.** Portfolio ban raha hai.
