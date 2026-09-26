# Phase 5B — JARVIS ko Dimag aur Pahunch (Week 2-4 sab) 🧠📡

> **Kya update hua, kya fayda hua, kaam kaise karta hai** — poora hisaab.
> Date: 2026-09-26 · Status: ✅ IMPLEMENTED + TESTED (**555 tests pass**)
> Isse pehle: [PHASE5A_UPDATE.md](PHASE5A_UPDATE.md) (Hindi voice, streaming, barge-in, free wake word)

---

## TL;DR — ek line mein

JARVIS ab **restart-proof reminders khud bolta hai** (pehle restart pe mar jaate the),
**purani baatein MEANING se yaad rakhta hai** (pehle keyword-matching thi),
**Telegram se phone se control hota hai** (pehle laptop saamne hona zaroori tha),
aur **GitHub Actions CI** har push pe 555 tests chalata hai (pehle koi safety net nahi).

---

## 1️⃣ Persistent Scheduler — restart-proof reminders (`saarthi/scheduler.py` 🆕)

### Kya problem thi
`reminder_set` sirf `asyncio.create_task` tha — **PC restart = reminder gayab hamesha ke liye.**
"Kal subah 8 baje medicine yaad dilana" — raat ko PC band hua to subah kuch nahi hota.

### Kya kiya
- **SQLite-backed** (`~/.saarthi/scheduler.db`) — har task disk pe, restart-proof
- **Recurring tasks**: `repeat=daily` / `weekly` — "roz subah 8 baje" khud reschedule
- **Missed catch-up**: agent band tha tab due hue tasks yaad rehte hain — agli baar start hote hi milte hain
- Time UTC epoch store hota hai (timezone/DST kadve se bachne ke liye)

### Fayda
- "Ek ghante mein chai" ab **pakka** yaad dilayega — chahe beech mein 5 baar restart ho
- Proactive announcements ka foundation (neeche #2)

---

## 2️⃣ Proactive Mode — JARVIS KHUD bolta hai (`saarthi/proactive.py` 🆕)

### Kya problem thi
Agent sirf REACT karta tha. Kuch nahi batata tha jab tak pucho na —
asli Jarvis to khud bolta hai: *"Sir, aaj 3 kaam hain..."*

### Kya kiya
- **Background loop** har 20s scheduler check karta hai:
  - reminder due → turant announce (voice + terminal + Telegram)
  - missed catch-up → "ye kaam tab ka tha jab main band tha"
- **Session-start briefing**: "Good morning. Aaj 2 kaam hain: chai (1 ghante mein)..."
- `format_announcement` / `build_briefing` / `_relative_time` — sab **pure logic, tested**
- **FAIL-SAFE**: engine crash = sirf log, agent ka main loop KABHI nahi rukta (test mein prove kiya)

### Kahan wired
- `jarvis.py` → `proactive_loop` background task (`--no-proactive` se band)
- Voice mode mein announcement **Hindi voice mein bolta hai** (Phase 5A ka fayda)

### Fayda
- **Presence feel** — JARVIS ab saamne baithe insaan jaisa hai, tool nahi
- Bill due, medicine, meeting — sab kuch khud yaad dilata hai

---

## 3️⃣ Vector Memory — meaning se yaad (`saarthi/memory/vector.py` 🆕)

### Kya problem thi
Memory search keyword-based (`LIKE %query%`) thi:

    Stored: "sharma ji photographer wale ko advance dena"
    Query:  "photo wala kaam kya hua tha?"
    Pehle:  KUCH NAHI milta (keyword match fail)

### Kya kiya
- **Hybrid semantic engine**: word unigrams + **character trigrams** ka TF vector, IDF-weighted **cosine similarity**
- SQLite mein stored (memory.db ke saath hi) — **zero naya dependency, zero download, offline**
- Trigrams Hinglish ke liye perfect: "paytm walla" ~ "paytm wala", "photo" ~ "photographer"
- **Integration**:
  - `MemoryStore.log_turn` → har lamba message automatically index hota hai
  - `MemoryStore.search_relevant_history()` → semantic search (+ keyword fallback)
  - **Agent hook**: har turn pe top-3 relevant purane turns user message ke saath LLM ko jaate hain — `[Purani relevant baatein]`
- `MEMORY_SEMANTIC=false` se off; prune (last 5000) se db kabhi nahi bharta

### Fayda (test se verified)
```
Query (typo ke saath): "photographer wal kaam"
Stored:                "sharma ji photographer wale ko advance de dena..."
Result:                ✅ MATCH (score 0.28) — keyword search ye kabhi nahi kar sakta
```
"wo cheez jo pichle hafte discuss hui thi" type sawaal ab kaam karte hain —
**compounding fayda**: jitni zyada baat hogi, utna tez Jarvis yaad rakhega.

---

## 4️⃣ Telegram Bot — phone se JARVIS (`saarthi/telegram_bot.py` 🆕)

### Kya problem thi
Laptop saamne hona zaroori tha. Bahar gaye to JARVIS se baat hi nahi.

### Kya kiya
- **Telegram Bot API** directly httpx se (long polling) — **zero naya dependency**
  (ye ROADMAP ka "phone se laptop ke agent ko baat karana" hai — bina port khole, bina public IP)
- **Text** → agent.run_turn → jawab wapas
- **Voice note** → download → whisper transcribe (Hinglish correction ke saath) → agent
  — matlab phone pe Hinglish bola aur ghar ka kaam ho gaya
- **Commands**: `/start`, `/status`, `/tasks` (pending reminders + due time)
- `jarvis.py` mein background start (token ho to) · standalone: `python -m saarthi.telegram_bot`

### SECURITY (fail-safe — repo ka rule)
| Rule | Kya hota hai |
|---|---|
| `TELEGRAM_ALLOWED_CHAT_IDS` whitelist | **Sirf ye chats** jawab paate hain. Khaali = bot SABKO ignore (koi rogue access nahi) |
| Risky tools (payments) | Telegram se **AUTO-DENY** — "laptop pe puch ke karo" (remote paise-confirmation untrustworthy) |
| OTP/PIN/password | Pehle jaisa **hard-block** (yahan bhi) |
| Bot token | Sirf `.env` mein — code/repo mein kabhi nahi |

### Setup (2 minute)
```ini
# ~/.saarthi/.env
TELEGRAM_BOT_TOKEN=123:abc...        # @BotFather se
TELEGRAM_ALLOWED_CHAT_IDS=123456789  # apna id @userinfobot se
```

### Fayda
- Ghar ka PC on, tu kahin bhi — **JARVIS pocket mein**
- Voice note bhej ke Hinglish mein kaam karwa

---

## 5️⃣ GitHub Actions CI (`.github/workflows/ci.yml` 🆕)

### Kya problem thi
555 tests the lekin push pe **kuch nahi chalta tha** — koi check nahi, koi net nahi.

### Kya kiya
- `.github/workflows/ci.yml`: Python **3.10 / 3.11 / 3.12** matrix, Ubuntu
- Core deps install (sirf 7 packages — tests by-design hardware-free hain)
- `python run_tests.py -q` (poora suite) + `py_compile` sab entry points pe

### Fayda
- Har push/PR pe **555 tests auto-run** — kuch toota to turant pata
- Teesre contributor ke liye bhi safety net

---

## 📁 Changes map

| File | Status | Kya |
|---|---|---|
| `saarthi/scheduler.py` | 🆕 NAYA | SQLite scheduler: add/due/recur/cancel/catch-up |
| `saarthi/proactive.py` | 🆕 NAYA | Briefing + announce + polling engine |
| `saarthi/memory/vector.py` | 🆕 NAYA | Trigram-TFIDF semantic memory (offline) |
| `saarthi/telegram_bot.py` | 🆕 NAYA | Long-polling bot: text/voice/commands + whitelist |
| `.github/workflows/ci.yml` | 🆕 NAYA | CI: 3.10-3.12 matrix + full suite |
| `saarthi/agent.py` | ✏️ | scheduler init/context + semantic recall injection |
| `saarthi/tools/base.py` | ✏️ | ToolContext.scheduler field |
| `saarthi/tools/system_tools.py` | ✏️ | reminder_set persistent + reminders_dikhao + reminder_hatao (60 tools ab) |
| `saarthi/memory/store.py` | ✏️ | log_turn → semantic index + search_relevant_history |
| `jarvis.py` | ✏️ | proactive_loop + telegram start (+ flags) |
| `tests/test_phase5b.py` | 🆕 NAYA | 22 tests (temp-db + MockTransport, no network) |
| `.env.example` | ✏️ | PROACTIVE_*, MEMORY_SEMANTIC, TELEGRAM_* |

## 🧪 Verify kaise karein

```bash
python run_tests.py -q                 # 555 tests pass hone chahiye

# 1. Reminder persist karta hai? Do terminal kholo:
python -m pytest tests/test_phase5b.py::SchedulerCore -q

# 2. Proactive + Hindi voice live:
python jarvis.py
# ("remind me in 1 minute for chai" bolo — 1 min baad khud bolega)

# 3. Telegram:
# @BotFather se token -> .env mein daalo -> jarvis.py restart
# Phone se: "bhai kal subah 7 baje ka alarm" + voice note bhejo

# 4. CI: GitHub pe push karo -> Actions tab mein 3.10/3.11/3.12 green
```

## 📊 Pehle vs Ab (Week 2-4)

| Cheez | Pehle | Ab |
|---|---|---|
| Reminder + PC restart | ❌ Gayab hamesha | ✅ SQLite mein zinda |
| Recurring ("roz subah") | ❌ Nahi tha | ✅ daily/weekly auto-reschedule |
| Agent khud bole | ❌ Kabhi nahi | ✅ Due pe + morning briefing |
| "photo wala kaam" search | ❌ Keyword fail | ✅ Meaning match (typo se bhi) |
| Phone se control | ❌ Impossible | ✅ Telegram text + voice note |
| Push pe tests | ❌ Koi nahi | ✅ 555 tests × 3 Python versions |

## ⚙️ Naye .env options

```ini
PROACTIVE_ENABLED=true
PROACTIVE_POLL_SECONDS=20
MEMORY_SEMANTIC=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
```

## Aage kya (Phase 5C ideas)

1. **Web UI auth** — LAN pe token/PIN (analysis ka G5)
2. **Email + Calendar tools** (Gmail/Google Calendar API)
3. **History compaction** — purani baatein LLM-summary mein
4. **Multi-step planner** — bade kaam auto-todna
5. **openWakeWord auto-setup** — installer mein `pip install openwakeword`

---
*Repo ke rules ke andar: safety layer untouched (Telegram pe aur sakht), ₹0 budget, sab optional.*
