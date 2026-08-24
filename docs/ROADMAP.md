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

## 🎯 Phase 3 — Browser + Phone polish

### Browser device ("saari websites ka access")
```python
# devices/browser.py
class BrowserDevice(Device):
    kind = "browser"
    capabilities = {TAP, TYPE, SCREENSHOT, UI_TREE, ...}
```
Playwright se — DOM hi `ui_tree` ban jaayega, isliye `tap_text` aur **self-healing dono automatically kaam karenge**. Ye architecture ka fayda hai.

⚠️ Imaandaar baat: CAPTCHA aur bot-detection real hain. ~90% websites chalengi.

### Phone polish
- Multiple devices ek saath (`adb -s`)
- Screenshot caching (free tier tokens bachao)
- Retry logic

---

## 🎯 Phase 4 — Android App (bada milestone)

Abhi laptop ki zarurat hai. Iske baad phone khud chalega.

| Kaam | Tech |
|---|---|
| App | Kotlin + Jetpack Compose |
| Screen control | **AccessibilityService** |
| Background | Foreground Service |
| Notifications | NotificationListenerService |
| Naye API | Android AppFunctions |

### Asli inaam: user ke taps sunna

Abhi recorder **agent ke apne** actions record karta hai. Accessibility Service ke baad **tere manual taps** record honge — matlab sach mein "dikha do" mode.

Achhi khabar: `skills/store.py` ka data format **same rahega**. Store aur runner dobara nahi likhna padega. Sirf ek naya recorder source.

⚠️ **Google Play policy:** autonomous accessibility agents publish karna allowed nahi hai. **Personal use / sideload bilkul theek hai.** Isko product banake bechne ka plan mat bana.

---

## 🎯 Phase 5 — Powerful banao

| Kaam | Kyun |
|---|---|
| Vector memory (ChromaDB) | Semantic recall — "wo cheez jo pichle mahine ki thi" |
| Skill chaining | Ek skill doosri ko call kare |
| Proactive suggestions | "bijli ka bill 3 din mein due hai" |
| On-device LLM | Gemma 4 12B / Qwen3.6 — privacy + no rate limit |
| Multi-step planning | Bade kaam automatically todna |
| Local server | Phone se laptop ke agent ko baat karana |

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
1. ✅ Phase 2 (Voice)        <- HO GAYA
2. ASLI HARDWARE PE TEST     <- ABHI YAHI KAR
   - Mic pe voice test kar (python voice_cli.py --check)
   - ADB laga ke asli phone pe Dikha Do Mode chala
3. Phase 4 (Android app)     <- sabse bada kaam, sabse bada inaam
4. Phase 3 (Browser)         <- scope badhega
5. Phase 5                   <- polish
```

**Ab #2 kyun (code likhne se pehle):** Phase 1 aur 2 dono ka code **asli hardware pe test nahi hua** — sandbox mein mic aur phone nahi tha. Aage badhne se pehle apne laptop pe voice aur apne phone pe ADB chala ke dekh. Jo bugs milenge wo asli honge, aur unko theek karna naya feature banane se zyada valuable hai.

Server/hosting ka sawaal? → [DEPLOYMENT.md](DEPLOYMENT.md) (short answer: abhi zarurat nahi)

---

## Har phase mein ye yaad rakh

1. **Ek waqt pe ek pillar.** Sab ek saath karne se kuch bhi accha nahi banega.
2. **Safety layer mat todo.** Feature add kar, brake mat hatao.
3. **Budget hardware test kar.** Apne sabse purane phone pe chala ke dekh — Pillar #3 yahi hai.
4. **Hinglish test cases likh.** `lang/` badle to purane commands verify kar.
5. **Har phase ke baad GitHub pe push kar.** Portfolio ban raha hai.
