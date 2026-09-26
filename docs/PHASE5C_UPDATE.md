# Phase 5C — JARVIS Final Form: Web Lock, Email, Calendar, Planner, Smart Memory 🔒📧📅

> **Kya update hua, kya fayda hua, kaam kaise karta hai.**
> Date: 2026-09-26 · Status: ✅ IMPLEMENTED + TESTED (**592 tests pass**)
> Series: [Phase 5A](PHASE5A_UPDATE.md) (human voice) · [Phase 5B](PHASE5B_UPDATE.md) (scheduler/proactive/memory/telegram)

---

## TL;DR

JARVIS ab **lock ho sakta hai** (web UI token), **mail padh/bhej sakta hai**, **Hinglish mein calendar events** bana sakta hai (auto-reminder ke saath), **bade kaam plan karke step-by-step** karta hai (checkbox progress), aur **lambi baat-cheet ka saaraansh khud yaad rakhta hai** (context kabhi nahi bhoolta). **68 tools** ho gaye.

---

## 1️⃣ Web UI Auth — LAN lock (`saarthi/web/app.py`)

### Problem (analysis ka G5)
Web UI `/api/chat` pe **koi auth nahi** — LAN pe koi bhi (cafe WiFi, hostel network) tere JARVIS ko command de sakta tha.

### Solution
- `SAARTHI_WEB_TOKEN` set karo → **saari API endpoints locked**
  - Constant-time compare (`secrets.compare_digest`) — timing-attack safe
  - UI shell khula rehta hai; pehli visit pe browser **token puchta hai** (localStorage mein yaad)
  - Saari `fetch()` calls automatically `X-Saarthi-Token` header bhejti hain (injected JS)
- Khaali = pehle jaisa open (existing users broken nahi), bas log mein warning

### Fayda
- Public/office WiFi pe bhi JARVIS safe — token ke bina API zero access

```ini
SAARTHI_WEB_TOKEN=mera-secret-token
```

---

## 2️⃣ Email Tools — `mail_padho` / `mail_dhoondho` / `mail_bhejo`

### Zero dependency design
Python stdlib (`imaplib` + `smtplib`) — **koi naya pip install nahi**. Gmail/Outlook/Yahoo/Rediff hosts khud guess hote hain email domain se.

### Tools (3 naye)
| Tool | Risk | Kya karta hai |
|---|---|---|
| `mail_padho` | SAFE | Last/unread mails — "koi naya mail aaya?" |
| `mail_dhoondho` | SAFE | Search — "rahul ka mail dhundo" (`from:rahul`, `subject:bill`) |
| `mail_bhejo` | **RISKY** | Mail send — **confirmation ke bina ek line nahi jaati** |

### Kaam kaise karta hai
- IMAP SSL (993) se fetch → headers decode (Hindi subjects bhi) → text body nikalta hai
- SMTP STARTTLS (587) se send
- Login fail → saaf message ("App Password check karo") — crash nahi

### Setup (one-time)
```ini
EMAIL_ADDRESS=tu@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # App Password — normal password NAHI chalega
# hosts auto-guess hote hain
```
(Google Account → Security → 2-Step Verification → App passwords)

---

## 3️⃣ Calendar — Hinglish events + auto-reminder (`saarthi/calendar_store.py` + 3 tools)

### Kya kiya
- **Local SQLite calendar** (restart-proof) — Google OAuth/bhaari deps ki zarurat nahi
- **HINGLISH DATE PARSER** (sabse mazedaar hissa, 11 tests):

| Tu bolta hai | JARVIS samajhta hai |
|---|---|
| "kal subah 9 baje" | kal 09:00 |
| "aaj shaam 6 baje" | aaj 18:00 |
| "parso raat 9" | parso 21:00 |
| "2 ghante mein" | +2 hours |
| "monday 5pm" | agla Monday 17:00 |
| "2026-10-01 09:00" | ISO seedha |

- **AUTO-REMINDER**: event bane to scheduler se reminder automatic lagta hai → ProactiveEngine us waqt **khud bol dega** (Phase 5B ka circle complete)

### E2E test se verified
```
"kal subah 9 baje Doctor appointment"
→ Event #1 @ 27 Sep, 09:00
→ AUTO-REMINDER: "📅 Doctor appointment — 15 min mein" @ 08:45 ✅
```

### Tools
`event_banao` · `events_dikhao` · `event_hatao`

---

## 4️⃣ Planner — bade kaam step-by-step (`saarthi/planner.py` + 3 tools)

### Problem
"Billa bharo, mail bhejo, reminder lagao" jaise multi-part kaam mein LLM steps **bhool jaata tha** — aadha kaam chhod deta tha.

### Solution — plan as scaffolding (agent loop untouched)
1. LLM complex task pe **pehle `plan_banao`** call karta hai (2-8 steps)
2. Har step apne **existing tools** se execute karta hai
3. Har step ke baad **`plan_update`** (done/failed/skip) — progress live
4. `plan_dikhao` — user ko bhi status

```
📋 PLAN: Portfolio website banao
  ✅ 1. design
  ⬜ 2. code
  ⬜ 3. deploy
  — 1/3 ho gaya —
```

- System prompt mein `PLANNING_RULES` add kiya — LLM ko kab use karna hai pata hai
- **Architecture clean**: pure logic (`planner.py`) alag, tools (`tools/planner_tools.py`) alag — circular import zero, direction sirf tools→planner

---

## 5️⃣ History Compaction — smart yaaddasht (agent.py)

### Problem
`trim_history()` purane messages **seedha delete** karta tha — "subhe jo baat hui thi" ka context hi gayab.

### Solution
Jab history > threshold (36):
- Purane turns ka **LLM-summary** banta hai (important facts, numbers, decisions rakhta hai)
- Summary ek SYSTEM message ke roop mein rehta hai + recent 16 turns fresh
- Fail-safe: LLM down → raw text fallback · `HISTORY_COMPACT=false` se off · kabhi turn nahi rokta

### Fayda
3-4 ghante ki lambi baat-cheet mein bhi **"subhe wali baat" yaad rehti hai** — tokens bhi bache, context bhi.

---

## 📁 Changes map

| File | Status | Kya |
|---|---|---|
| `saarthi/tools/email_tools.py` | 🆕 | 3 email tools + pure helpers (hosts guess, criteria, body extract) |
| `saarthi/calendar_store.py` | 🆕 | Hinglish when-parser + SQLite CalendarStore + auto-reminder |
| `saarthi/tools/calendar_tools.py` | 🆕 | 3 event tools |
| `saarthi/planner.py` | 🆕 | PURE logic: Plan, parse_plan_json, PlanTracker |
| `saarthi/tools/planner_tools.py` | 🆕 | 3 plan tools |
| `saarthi/web/app.py` | ✏️ | TokenAuthMiddleware + check_web_token + HTML token-JS inject |
| `saarthi/agent.py` | ✏️ | compact_history() + calendar init + planner scratch |
| `saarthi/lang/prompts.py` | ✏️ | PLANNING_RULES |
| `saarthi/tools/__init__.py` | ✏️ | 3 naye tool-groups registered (**68 tools**) |
| `tests/test_phase5c.py` | 🆕 | 37 tests (network-free) |
| `.github/workflows/ci.yml` | ✏️ | (5B se) ab ye sab bhi cover |
| `.env.example` | ✏️ | SAARTHI_WEB_TOKEN, EMAIL_*, HISTORY_COMPACT_* |

## 🧪 Verify

```bash
python run_tests.py -q          # 592 tests pass

# Web lock:
SAARTHI_WEB_TOKEN=test python jarvis.py
# -> browser kholo: token puchega; bina token /api/chat 401

# Email (App Password ke saath):
# .env mein EMAIL_* bharo -> "mere mails dikhao" bolo

# Calendar:
# "kal subah 9 baje doctor ka appointment rakho" -> event + auto reminder

# Planner:
# "mera project setup kar de — repo banao, code likho, test chalao"
# -> LLM plan banayega, checkbox progress dikhayega
```

## 📊 Poora Safar (5A → 5B → 5C)

| | Pehle (scan wala) | Ab |
|---|---|---|
| Awaaz | Roboti English | Hindi neural + streaming + barge-in + free wake word |
| Yaaddasht | Keyword match | Semantic recall + **LLM compaction** |
| Reminders | Restart pe gayab | Persistent + **khud bolne wale** + calendar-linked |
| Kaam karna | Ek-ek command | **Plan → steps → progress** |
| Pahunch | Laptop saamne | **Phone se (Telegram) + mail se** |
| Security | Web khula (LAN) | **Token lock + whitelist + auto-deny** |
| Tools | 58 | **68** |
| Tests | 489 | **592** |
| CI | ❌ | ✅ 3 Python versions |

## Ab kya bacha (optional future)

- Google Calendar real sync (OAuth) — local calendar upar lag sakta hai
- on-device LLM (Ollama vision models)
- Skill chaining
- Multi-device sync

---
*Poora upgrade ₹0 mein, sab optional, safety layer untouched. JARVIS ab sach mein "sab kuchh kar sakta hai" wala hai — jo wo nahi kar sakta wo tools banane ki zarurat batata hai.* 🛕
