# SAARTHI — Complete Handoff Document

> **Ye file kis liye hai:** Agar tu naya AI assistant / developer hai jo is
> project pe kaam karne wala hai — **ye pura padh le pehle.** Isme sab kuch
> hai: vision, decided architecture, kya ban chuka hai, kya bacha hai, aur
> kaunsi galtiyan mat karna.
>
> **Repo:** https://github.com/theafzalhussain/Sarthi
> **Last updated:** August 2026 · 16 commits
> **Status:** Phase 1 ✅ · Phase 2 ✅ · Phase 3 🟡 (part 1 done) · Phase 4-5 ⬜
>
> **Ek line mein abhi ka haal:** 8 LLM providers, 34 tools, 110 Indian apps,
> professional English interface (par baat user ki bhasha mein), browser
> automation, aur **238 tests jo `python run_tests.py` se chalte hain.**

---

## 1. PROJECT KYA HAI

**SAARTHI** (सारथी = rath chalane wala) — ek personal AI agent jo:
- **Hinglish** samajhta hai (Hindi + English mila ke, roman script)
- User ke **devices chalata hai** (Android phone, laptop)
- **Bolke ya likhke** command lete hai
- **Naye kaam seekhta hai** jab user dikhata hai
- **Internet access** rakhta hai

### Banane wala
Ek Indian student, **₹0 budget**. Isliye **har cheez free tier pe** honi chahiye.
Ye constraint negotiable nahi hai — koi paid dependency add mat karna.

### Vision (user ke shabdon mein)
User chahta tha "aisa agent jo sab kuch kar sake, har device ka access ho".
Usko **honestly** samjhaya gaya ki "sab kuch" duniya ka sabse crowded idea hai
(Google/Apple/OpenAI billions laga rahe hain). Isliye **specific wedge** pakda:

---

## 2. THE 4 PILLARS (ye project ki jaan hain — inko kabhi mat todna)

| # | Pillar | Kya matlab | Kyun ye moat hai |
|---|---|---|---|
| **1** | **Hinglish-first** | Code-switching native hai, bolt-on nahi | Global agents Hinglish pe girte hain (data neeche) |
| **2** | **Dikha Do Mode** | Ek baar dikha, hamesha yaad — UI badle to **khud theek ho** | Research papers mein hai, kisi phone product mein shipped nahi |
| **3** | **Budget hardware** | Python 3.9+, SQLite, screen-size-relative coords | India ka 80% market sasta phone/purana laptop |
| **4** | **Indian apps** | 110+ apps ka package database | Silicon Valley ko IRCTC ka naam bhi nahi pata |

### Research data jo Pillar #1 justify karta hai (README mein cited hai)
- Code-mixed queries pe task success **20-45% girta** hai
- Indic code-switched speech pe **25-35% word error rate**
- **250 million+ log** Hindi-English mix bolte hain
- Standard ASR models code-switching ke liye **bane hi nahi** the

### Killer feature (Pillar #2 ka core)
**3-level self-healing skills.** Normal automation (Tasker/macros) coordinates pe
chalte hain — app update aaya, button hila, automation toot gaya. SAARTHI screen
padh ke naya button dhoondh leta hai aur **skill ko permanently update** kar deta hai.

---

## 3. PHASE 1 ✅ COMPLETE (commit `b4fd58f`)

**Foundation.** 40 files, ~8,000 lines.

### Modules

```
saarthi/
├── config.py       Settings, DEFAULT_MODELS, DEFAULT_PROVIDER_ORDER
├── agent.py        Main plan-act-observe loop (~100 lines, NO framework)
├── brain/          LLM providers + auto-fallback
├── lang/           PILLAR #1 — Hinglish parsing
├── devices/        Universal device adapters
├── tools/          34 tools + safety layer
├── memory/         SQLite (facts + conversations)
└── skills/         PILLAR #2 — Dikha Do Mode
cli.py              Text REPL
```

### `brain/` — LLM layer
- `types.py` — Message/ToolCall/LLMResponse/ToolSchema, exceptions
- `base.py` — abstract `LLMProvider` (+ `list_models()`)
- `openai_compat.py` — **ek class, saare OpenAI-compatible providers**
- `gemini.py` — Gemini ka apna format (contents/systemInstruction, inlineData)
- `router.py` — `Brain` class, auto-fallback, vision routing, `discover_models()`

### `lang/` — Hinglish (PILLAR #1)
- `lexicon.py` — **110 Indian apps** → package names, 18 intents, risky keywords,
  Hindi numbers (sau/hazaar/lakh/crore + dhai/saadhe/paune), device words
- `normalize.py` — Devanagari→roman, `parse_hindi_number()`, `extract_amount()`,
  `ParsedCommand.to_hint()` ← **ye LLM ko structured hints deta hai**
- `prompts.py` — system prompt, language rules, safety rules

### `devices/` — "Sab devices ka access"
- `base.py` — `Capability` enum, `ActionResult`, `UIElement`, abstract `Device`
  + composed helpers `find_element()` / `tap_text()`
- `android.py` — ADB (tap/swipe/type/screenshot/ui_tree/launch_app/notifications)
- `desktop.py` — shell/files/apps + optional pyautogui
- `manager.py` — `DeviceManager`, Hinglish→device routing

### `tools/` — 34 tools
- `registry.py` — **`execute()` = single safety chokepoint**
  (validate → type-coerce → confirm → run → never raise)
- `safety.py` — hard blocks + confirm rules + `is_affirmative()`
- `device_tools.py` / `web_tools.py` / `system_tools.py` /
  `memory_tools.py` / `skill_tools.py`

### `skills/` — Dikha Do Mode (PILLAR #2)
- `store.py` — `SkillStep` stores **BOTH** `target_text` (primary) AND
  `target_coords` (fallback) = self-healing foundation.
  `parameterize_steps()` turns recorded "2500" into `{amount}`
- `recorder.py` — captures agent's successful actions
- `runner.py` — **3-level self-healing** (detail section 7 mein)

---

## 4. PHASE 2 ✅ COMPLETE (commit `a461d3a`)

**Voice.** +3,547 lines. Sab offline aur free.

```
saarthi/voice/
├── hinglish_asr.py   PILLAR #1 voice pe — biasing + 55 corrections
├── audio.py          mic, silence detection, playback
├── stt.py            faster-whisper wrapper
├── tts.py            5 backends, auto-select
├── wake.py           3 wake modes
└── session.py        pura loop
voice_cli.py          entrypoint (--check / --once)
```

### Hinglish ASR — do layer (ye Phase 2 ki asli value hai)

**Problem:** Whisper English-first hai.
| Bola | Suna |
|---|---|
| paytm kholo | pay time cholo |
| zomato se order | **tomato** se order |
| do hazaar paise | do hazar **peace** |
| irctc pe dekho | i r c t c pe dekho |

**Solution:**
1. **BIASING** — `initial_prompt` mein Hinglish examples + 22 app naam (free, no training)
2. **CORRECTION** — 55 word-boundary regex + `ContextRule` (enablers + blockers)

**MEASURED FAYDA:**
```
"pay time cholo aur die hazaar ka bell bhar do"
  bina correction : intent=type, app=none,  amount=1000  ← GALAT
  correction baad : intent=pay,  app=paytm, amount=2500  ← SAHI
```
**₹1500 ka farak.** Aur "phone pay" pehle DIALER app match karta tha, PhonePe nahi.

### Compounding fayda (accha side effect)
`session.refresh_vocabulary()` Whisper ki vocabulary **memory + skills se** banata
hai. Matlab **jitna agent ko sikhaayega, utna accha wo sunega.** Normal voice
assistants mein ye nahi hota.

### Voice confirmation — FAIL SAFE
Risky kaam pe bolke puchta hai. Sunai na de ya confusing jawab → **2 retry → mana**.
Chup-chaap paise kabhi nahi jaate.

---

## 5. LLM PROVIDERS — 8 hain

| Provider | Model (default) | Strength | Tools | Vision | Key kahan se |
|---|---|---|---|---|---|
| **deepseek** | `deepseek-ai/deepseek-v4-pro` | Sabse **smart** — 1.6T MoE, 1M context | ✅ | ❌ | build.nvidia.com |
| **nvidia** | `nvidia/nemotron-3-ultra-550b-a55b` | Long-running **agents** ke liye bana | ✅ | ❌ | build.nvidia.com |
| **muse** | `meta/muse-glimmer-30b` | **Vision + tools DONO**, tez (30B) | ✅ | ✅ | build.nvidia.com |
| **groq** | `openai/gpt-oss-20b` | Sabse **tez** | ✅ | ❌ | console.groq.com |
| **bluesminds** | `gpt-4o` | GPT-5.6/4o/GLM gateway | ✅ | ✅ | api.bluesminds.com |
| **openrouter** | `openrouter/free` | 98 free models ka router | ✅ | ❌ | openrouter.ai/keys |
| **gemini** | `gemini-3.6-flash` | **Aankh** (screenshot) | ✅ | ✅ | aistudio.google.com/apikey |
| **gemma** | `google/diffusiongemma-26b-a4b-it` | 262K context, image+video input | ❌ | ✅ | build.nvidia.com |

### 🔑 EK NVIDIA KEY SE CHAAR MODELS

`deepseek`, `nvidia`, `muse`, `gemma` — chaaron **NVIDIA NIM ke same
endpoint** (`integrate.api.nvidia.com/v1`) pe chalte hain aur **ek hi
`NVIDIA_API_KEY`** use karte hain.

Alag "provider" isliye banaye hain (model switch ke bajaay) taaki:
- har model ko apna **fallback slot** mile — ek 404 de to agla automatic
- user `SAARTHI_PROVIDER_ORDER` se apna pasandeeda model pehle rakh sake
- `/models` sabke liye alag se kaam kare

**⚠️ Iska nuksaan bhi samajh:** us ek key ki limit khatam ho to **chaaron
ruk jaayenge.** Isliye `GROQ_API_KEY` bhi rakhna — uski limit alag hai.

### `supports_tools` FLAG — kyun banaya

SAARTHI ka pura kaam **tool calling** se hota hai. Jo model tools support
nahi karta wo unhe **chup-chaap IGNORE** kar deta hai — bas text bhej deta
hai, agent ka loop khatam, aur user sochta hai *"kaam kyun nahi hua"*.

**Silent failure sabse buri cheez hai.** Isliye `ProviderConfig` mein
`supports_tools` hai, aur `Brain.think()` tool wale kaam ke liye aise
providers ko **peeche dhakel deta hai** (hataata nahi — tool wale sab fail
ho jaayein to kuch jawab dena chup rehne se behtar hai).

DiffusionGemma diffusion-based hai, iska tool calling verify nahi hua →
`GEMMA_TOOLS` default **false**. Chal jaaye to `.env` mein `true` kar de.

**Order (best pehle):**
```
deepseek → nvidia → muse → groq → bluesminds → openrouter → gemini → gemma
```
**Best pehle, tez pehle nahi** — kyunki smart model ek hi prompt mein kaam
kar deta hai; tez-par-kamzor model 3-4 baar galti karta hai aur aakhir mein
zyada waqt + zyada tokens khaata hai.

**8 free tiers = practically unlimited.**

### 🩺 PROVIDER HEALTH — dead provider dobara try nahi hota

Ye ek asli problem se aaya: Bluesminds pe `glm-5.2` har message pe
HTTP 400 deta tha (*"Model has not been priced by the administrator"*).
Purana code use **har turn pe pehle** try karta tha → 1-2 second barbaad →
phir fallback. **Har ek message pe.**

Ab error classify hota hai (`brain/types.py` → `classify_http_error()`):

| Error | Matlab | Action |
|---|---|---|
| 400 + model/pricing error | **Permanent** | provider **session bhar** hat jaata hai |
| 404 model not found | **Permanent** | hat jaata hai + `/models` suggest |
| 401 / 403 bad key | **Permanent** | hat jaata hai |
| 429 rate limit | **Temporary** | **90s cooldown**, phir wapas |
| 5xx server down | **Temporary** | 90s cooldown (unka server issue hai) |

- Saare dead ho jaayein to phir bhi try karta hai (kuch na karne se behtar)
- `/retry` command sabko manually revive karta hai
- `/status` mein dead provider **HATA DIYA** dikhta hai

### ⚠️ MODEL NAMES DEPRECATE HOTE RAHTE HAIN
Ye **asli problem** hai jo user ne live pakdi. Groq ne June 2026 mein
`llama-3.3-70b-versatile` band kar diya, Gemini ne `gemini-2.0-flash`.

**Isliye ye system bana hai:**
1. `/models` CLI command — teri key se **LIVE** batata hai kaunse models available hain
2. 404 pe **actionable error** — "'/models' chala, phir .env update kar"
3. `.env.example` mein model lines **commented** — code se latest default aaye

**Naya AI/dev ke liye rule:** Agar `model_not_found` error aaye, model naam
**web se verify kar** ya `/models` chala. Apne training data ke naam mat maano.

---

## 6. ARCHITECTURE KE DECIDED PRINCIPLES (inko follow karna)

| Principle | Kyun |
|---|---|
| **Tools exception nahi throw karte** | `ActionResult.failure()` return karo — agent ko structured error chahiye recover karne ke liye |
| **Fail-safe defaults** | Confirmation ka tareeka na ho → **mana kar do** |
| **Optional dependencies degrade** | pyautogui/sounddevice na ho to crash nahi, clear message |
| **Text > coordinates** | UI badalta hai, text usually nahi |
| **`ui_tree` > screenshot** | Sasta, exact, fast — free tier aur budget phone dono ke liye |
| **Framework NAHI** | Loop 100 line ka hai. Chhota pad jaaye tab LangGraph laayenge — **pehle nahi** |
| **Python 3.9+** | Purane laptop pe chale. Har file mein `from __future__ import annotations` |
| **Hardware logic se alag** | `SilenceDetector` pure state machine hai → bina mic test hota hai |

### Naya kuch add karna hai? — Cheat sheet

| Kya | Kahan |
|---|---|
| Naya app | `lang/lexicon.py` → `INDIAN_APPS` |
| Naya Hinglish phrase | `lang/lexicon.py` → `VERB_INTENTS` |
| Naya tool | `tools/` mein file, phir `default_registry()` |
| Naya device | `devices/` mein `Device` subclass, phir `manager.register()` |
| **Naya LLM provider** | OpenAI-compatible ho to **sirf** `openai_compat.py` ke `BASE_URLS` mein ek line |
| Naya risky pattern | `tools/safety.py` |
| ASR correction | `voice/hinglish_asr.py` → `SAFE_CORRECTIONS` |
| Naya TTS backend | `voice/tts.py` → `TTSBackend` subclass + `BACKEND_ORDER` |

---

## 7. SELF-HEALING — 3 LEVEL (killer feature ka core)

Har `SkillStep` **do** targets store karta hai: `target_text` + `target_coords`.

```
LEVEL 1  target_text se element mila?  -> chalao
LEVEL 2  nahi mila -> screen padho, LLM se pucho
         "Electricity ka kaam ab kaunsa button karega?"
         -> "Bijli Bill" -> tap karo
         -> SKILL PERMANENTLY UPDATE karo (target_text + coords + notes)
LEVEL 3  LLM bhi na dhoondhe -> purane coordinates
         (par pehle USER SE PUCHO)
```

### ⚠️ ORDER JAAN-BOOJH KE AISA HAI — MAT BADALNA

Agar text nahi mila to **UI badal gaya hai.** Aise waqt purane coordinates pe tap
karna **KHATARNAK** hai — wahan ab **doosra button** ho sakta hai. ADB ko farak
nahi padta, tap "safal" dikhega, par **galat kaam** ho jaayega. **Payment screen
pe ye bahut bura hai.**

Isliye pehle **semantic** healing (samajh ke), phir coordinates — aur wo bhi
**permission ke saath.** Ye bug pehle tha, fix kiya gaya. **Regress mat karna.**

---

## 8. SAFETY — ye sab decided hai, mat hatana

### Hard blocks (kabhi nahi honge)
- **OTP / PIN / password / CVV type karna** — user khud daalega
- `rm -rf /`, `mkfs`, fork bomb, disk wipe, `curl | bash`, shutdown

### Confirmation chahiye
- Paise / payment / recharge / order
- Kuch delete karna
- Message / call kisi ko
- Shell commands
- Skill chalana

### Fail-safe rules
- Confirmation ka koi tareeka na ho → **deny** (silently proceed **NAHI**)
- Voice pe samajh na aaye → 2 retry → **deny**
- Blind coordinate tap se pehle **pucho**

### Final payment button
**Agent screen tak le jaayega, user dabayega.** Ye rule negotiable nahi hai —
banking apps automation detect karke block bhi karte hain, aur galat transfer
wapas nahi aata.

---

## 9. BUGS JO MILE AUR FIX HUE (regress mat karna)

| # | Bug | Fix |
|---|---|---|
| 1 | **Substring matching** — "pa**ytm**" ne YouTube match kiya, "**wa**hi" ne WhatsApp, "**pay**tm" risky flag hua | **Word boundaries (`\b`) everywhere** + non-overlapping span tracking + `AMBIGUOUS_APP_NAMES`/`POSSESSIVES` |
| 2 | **Type mismatch crash** — `{amount}` → int 1240 → `check_text_safety(1240)` → `.lower()` crash | `Tool.coerce_args()` schema ke hisaab se type convert karta hai. Isse LLM ka `"500"` vs `500` bhi fix hua |
| 3 | **Unsafe healing order** — coordinates pehle try hote the, galat button dab sakta tha | Semantic healing pehle, coordinates last + permission (section 7) |
| 4 | **ASR false positive** — "tomato khareedo sabzi mandi **se**" → zomato ban gaya (enabler mein "se" tha) | `ContextRule` with **blockers**. **Seekh: enabler DISTINCTIVE hona chahiye, common nahi** |
| 5 | **Porcupine error khali** — short-circuit se `_error` populate nahi hua, user ko wajah nahi pata chalti | `_build()` pehle call + `unavailable_reason()` jo SAARE blockers batata hai |
| 6 | **Deprecated model names** — teeno providers 404 de rahe the | `/models` discovery + actionable 404 + `.env.example` mein model lines commented |
| 7 | **Browser tab hijack** — agent user ka chalu tab chheen leta tha. Do jagah se: `webbrowser.open()` ka default `new=0` current tab REPLACE kar sakta tha, aur `launch_app()` hamesha `self._page` reuse karta tha | `new=2` + `autoraise=False`; naya tab per task; `_agent_url` se **user-takeover detection**; `MAX_TABS=10` cap; `bring_to_front()` kabhi nahi |
| 9 | **Galat voice API naam** `hardware_check.py` mein — `Microphone` (asli `Recorder`), `engine.speak()` (asli `engine.say()`). Sandbox mein pakda nahi gaya kyunki mic nahi tha, wo code path chala hi nahi | Asli code padh ke sahi naam. Plus thin wrappers + AST test jo function-level imports bhi verify karta hai |
| 10 | **Galat mic device** — Windows pe default "Microsoft Sound Mapper" (legacy MME) select hota tha, `peak` sirf 303 = silence. Whisper ko kuch sunai nahi deta tha. Asli wajah: `AudioConfig` mein device field HI NAHI THA, mic chunne ka koi tareeka nahi tha | `AudioConfig.device` + `from_env()` + `SAARTHI_MIC_DEVICE` (naam ya index se). Plus `--mic-scan` jo har mic try karke best batata hai, aur live level meter |
| 8 | **`extract_amount()` substring** (BUG#1 ka same class) — money context `"rs"` SUBSTRING se check hota tha, to "yea**rs**", "fi**rs**t", "hou**rs**" amount de dete the | `\b` word boundaries + payment app naam explicit (`paytm`/`phonepe`/`upi`), kyunki `"pay"` substring hatane se wo miss ho rahe the |

### ⚠️ Jo galti MAINE (AI ne) ki thi — isse seekh

Tab-fix ke saath maine prompt mein ye rule likh diya tha:
> *"Site khul gayi aur user ko wahi chahiye tha? To **RUK JA**."*

Token bachane ke chakkar mein **agent ko aadha kaam karna sikha diya.**
Nateeja: user ne bola *"youtube pe gaana chala do"* → agent ne sirf SEARCH
kiya aur ruk gaya. User ko alag se *"play kar"* bolna padta tha.

**Sabak: efficiency ke naam pe kaam adhoora karwana bug hai, feature nahi.**
Ab rule #9 (`KAAM PURA KARO`) ulta hai — jab tak kaam ho na jaaye, rukna nahi.

---

## 10. DO SUBTLE GOTCHAS (miss karna aasaan hai)

1. **int16 → float32 conversion** (`voice/stt.py`)
   Whisper `[-1,1]` maangta hai, mic `int16` (0-32767) deta hai.
   **Divide by 32768 zaroori hai** — warna Whisper ko **sirf shor** sunai deta hai.

2. **Porcupine frame size** (`voice/wake.py`)
   Porcupine **exactly 512 samples** maangta hai, hamara chunk 480 hai.
   Frame buffer banaya hai. Ye miss karne pe Porcupine **chup-chaap** fail hota hai.

---

## 11. TESTING STATUS — ye IMAANDAARI se padh

### ✅ AB ASLI TEST SUITE HAI — 238 tests

```bash
python run_tests.py              # sab (0.1 second mein)
python run_tests.py known_bugs   # sirf bug regression tests
python -m unittest discover -s tests   # ya seedha unittest se
```

**Koi extra install nahi chahiye** — stdlib `unittest` use hota hai.
Ye jaan-boojh ke hai: ₹0 budget aur purane laptop pe bhi chale.
(pytest ho to `pytest tests/` bhi chalega.)

**Tests HARDWARE KE BINA chalte hain** — mic, phone, browser, internet
kuch nahi chahiye. Sab fake ho jaata hai (`tests/helpers.py`).

| File | Tests | Kya cover karta hai |
|---|---|---|
| `test_known_bugs.py` | 31 | **8 asli bugs** + hard blocks. Sabse zaroori file |
| `test_config.py` | 26 | 8 providers, ek key = 4 models, capabilities, order trap |
| `test_brain.py` | 21 | Error classification, provider health, tool filtering, vision routing |
| `test_browser_tabs.py` | 21 | Tab safety, URL resolution, teen browser mode |
| `test_hinglish.py` | 25 | Parsing, 110 apps, Hindi numbers, language detection |
| `test_asr.py` | 17 | ASR corrections, ₹1500 case, false positives |
| `test_tools.py` | 16 | Registry, confirmation, full access mode |
| `test_ui.py` | 26 | Renderers, ASCII/plain fallback, interface English hai |
| `test_skills_healing.py` | 12 | **Teen level healing** — fake device se UI change simulate |
| `test_hardware_check.py` | 43 | Voice API contract, mic device selection, level meter |

**Bug ka number test ke naam mein hai.** Fail hone pe seedha samajh aata hai:
```
FAIL: test_bug1_paytm_youtube_match_nahi_karta
FAIL: test_bug3_semantic_healing_coordinates_se_pehle_hai
```

**Naya bug mile to yahan test add karna — fix ke SAATH, baad mein nahi.**

### ⚠️ BUG#9 se seekha ek zaroori sabak

`hardware_check.py` mein maine (AI ne) voice API ke naam GUESS kar liye
the — `Microphone` (asli: `Recorder`), `engine.speak()` (asli:
`engine.say()`). Sandbox mein pakda NAHI gaya kyunki wahan mic nahi tha,
to wo code path chala hi nahi. User ki asli machine pe crash hua.

Pehli koshish mein maine test bhi GALAT likha — voice API ko alag se
test kiya, wo pass hota raha aur bug phir bhi nikal gaya. Kyunki galat
naam script ke ANDAR the, function-level import mein.

**Do cheezein ab hain:**
1. Script ke API calls **thin wrappers** mein hain (`open_recorder()`,
   `speak_text()` etc.) jinhe test SEEDHA call karta hai — hardware ke
   bina bhi.
2. Ek **AST test** har entrypoint ke saare `from saarthi... import X`
   verify karta hai, **chahe wo function ke andar likhe hon.**
   Function-level imports sabse khatarnak hain — wo sirf tab fail hote
   hain jab wo function chalta hai.

**Aur sabse zaroori:** maine bug WAPAS daal ke verify kiya ki test
sach mein fail hota hai. Warna "test pass ho raha hai" ka jhoota
bharosa ban jaata hai. **Naya test likho to ye zaroor karo.**

Aur verified:
- 56 Python files, ~15,300 lines (+2,700 test lines)
- Saare modules **Python 3.9 pe import hote hain**
- Browser tab safety **asli chromium ke saath** end-to-end verify hui
- Web search **live chala**
- NVIDIA `/models` **live chala**

### ❌ NAHI Verified — ASLI HARDWARE

- **Asli microphone pe voice** — sandbox mein mic nahi hai
- **Asli speaker pe TTS** — sandbox mein audio output nahi hai
- **Asli phone pe ADB** — sandbox mein phone nahi hai

> **Naye AI/dev ke liye:** Ye **sirf user kar sakta hai.** Uske liye
> `docs/HARDWARE_TEST.md` aur `python hardware_check.py` bana diya hai —
> user chalayega, output paste karega, tu bugs fix karega.
>
> Jo bugs wahan milenge wo **asli** honge, aur unko fix karna naya feature
> banane se zyada valuable hai.

---

## 12. AAGE KYA BACHA HAI

### 🟡 Phase 3 — Browser + phone polish (PART 1 DONE)

**✅ Ho gaya:**
- `devices/browser.py` — Playwright se `BrowserDevice`
  **Fayda sach nikla:** DOM hi `ui_tree` ban gaya, isliye `tap_text` aur
  **self-healing dono AUTOMATICALLY kaam karne lage** — ek line nahi likhni
  padi. Ye Phase 1 ke `Device` abstraction ka payoff hai.
- `website_kholo` tool — `url` + `search` se ek hi call mein kaam
- `phone_wifi_se_jodo` tool — cable ke bina phone control
- **Tab discipline** — user ka tab kabhi hijack nahi hota (BUG#7 dekh)

**⬜ Bacha hai:**
- Multiple devices (`adb -s`), screenshot caching, retry logic
- Browser mein login flows ka polish

⚠️ Honest: CAPTCHA aur bot-detection real hain. ~90% websites chalengi.

### ⬜ Phase 4 — Android App (SABSE BADA MILESTONE)
| Kaam | Tech |
|---|---|
| App | Kotlin + Jetpack Compose |
| Screen control | **AccessibilityService** |
| Background | Foreground Service |
| Notifications | NotificationListenerService |
| Naye API | Android AppFunctions |

**Asli inaam:** Abhi recorder **agent ke apne** actions record karta hai.
Accessibility Service ke baad **user ke MANUAL taps** record honge — matlab sach
mein "dikha do" mode.

**Achhi khabar:** `skills/store.py` ka data format **same rahega**. Store aur
runner dobara nahi likhna padega. Sirf naya recorder source.

⚠️ **Google Play policy:** Autonomous accessibility agents publish karna **allowed
nahi** hai. **Personal use / sideload bilkul theek hai.** Product banake bechne ka
plan mat banao.

### ⬜ Phase 5 — Polish
- Vector memory (ChromaDB) — semantic recall
- Skill chaining, proactive suggestions
- On-device LLM (Gemma/Qwen) — privacy + no rate limit
- `saarthi/server/` module — `/chat`, `/voice`, scheduler
- Barge-in (echo cancellation)

---

## 13. JO KABHI NAHI HOGA (aur kyun)

| Cheez | Wajah |
|---|---|
| **iPhone full control** | Apple sandbox. Technically impossible without jailbreak. Sirf Shortcuts tak |
| **OTP/PIN/password type karna** | Jaan-boojh ke block. Security rule, negotiable nahi |
| **Final payment button dabana** | Agent le jaayega, user dabayega |
| **Banking apps automation** | Wo apps khud detect karke block karte hain |
| **Kisi aur ka device** | Illegal. Sirf apne devices |
| **Play Store pe publish** | Google policy autonomous a11y agents ko ban karti hai |

---

## 14. DEPLOYMENT — server ka sawaal (poora `docs/DEPLOYMENT.md` mein)

### 🔴 Critical insight
**Cloud server phone ko ADB se control NAHI kar sakta** — ADB ko USB ya same LAN
chahiye. Solution: **Tailscale** (free mesh VPN).

### Short answer
**Abhi server ki zarurat NAHI hai.** 90% kaam reactive hai (user bolta hai, agent
karta hai). Server sirf proactive cheezon ke liye (scheduled tasks, monitoring).

**Aur Phase 4 ke baad kabhi nahi padegi — kyunki phone hi server ban jaayega.**

### Bijli ka kharcha (24/7, ~₹8/unit)
| Device | Mahine ka |
|---|---|
| Purana Android phone (Termux) | **~₹12** 🏆 |
| Raspberry Pi | ~₹30 |
| Laptop idle | ~₹110 |
| Desktop PC | ~₹450 ❌ |
| Oracle Cloud Always Free | **₹0** 🏆 |

**PC kharab hoga?** Battery nahi phategi (modern BMS overcharge rokta hai), par
**garmi + hamesha 100% charge** se battery degrade hoti hai, fan ghista hai.
**Salah: primary laptop 24/7 mat chalao.**

---

## 15. SETUP (naye machine pe)

```bash
git clone https://github.com/theafzalhussain/Sarthi.git
cd Sarthi
pip install -r requirements.txt

cp .env.example .env          # Windows: Copy-Item .env.example .env
# .env mein keys daal (model lines COMMENTED rehne do)

python run_tests.py           # PEHLE YE — 195 tests, 0.1 second
python cli.py                 # text mode
```

**⚠️ `.env` mein `SAARTHI_PROVIDER_ORDER` COMMENTED rehne do.** Agar tu khud
order likhega, to baad mein add hone wale naye models **sabse aakhir** chale
jaayenge — chahe wo sabse smart hon. Startup pe warning aati hai agar aisa ho.

### Voice (optional)
```bash
pip install faster-whisper sounddevice
sudo apt install libportaudio2 espeak-ng    # Linux
# Windows: PortAudio included; espeak-ng installer ya pip install pyttsx3

python voice_cli.py --check   # setup diagnostic — YAHAN SE SHURU
python voice_cli.py --once    # ek baar test
python voice_cli.py           # pura loop
```

### Phone (optional)
```bash
# Settings > About phone > Build number pe 7 baar tap
# Settings > Developer options > USB Debugging ON
adb devices                   # phone pe "Allow"
adb shell input tap 500 500   # test — phone khud tap karega
```

### Hardware test (mic / speaker / phone)
```bash
python hardware_check.py      # diagnostic — output paste kar dena
```
Detail: `docs/HARDWARE_TEST.md`

### CLI commands
```
/status   /models   /tools    /skills   /devices  /memory
/browser  /auto     /retry    /verbose  /reset    /help    /quit
```
| Command | Kab kaam aata hai |
|---|---|
| `/models` | Model deprecate ho jaaye (404 error) |
| `/browser` | Tab switch ho raha ho |
| `/retry` | Provider hat gaya ho aur dobara try karna ho |
| `/auto` | Full access — risky kaam bina puche (hard blocks bache rahenge) |

---

## 16. ⚠️ SECURITY — API KEYS

User ne is project ke dauraan **do baar galti se API keys chat mein paste kar di
thi.** Wo keys revoke karni padi.

### Rules
1. **API key kabhi kisi ko share mat karo** — AI ko bhi nahi
2. `.env` file ka screenshot **kabhi mat bhejo** (terminal ka theek hai)
3. `.env` gitignored hai ✅ — par **`.env.example` TRACKED hai**, usme asli key
   daalna = GitHub pe public ho jaayegi
4. Key dikh jaaye to **turant revoke + nayi banao**

### Keys jo chahiye (kam se kam 1)
```env
GROQ_API_KEY=
NVIDIA_API_KEY=
BLUESMINDS_API_KEY=
GEMINI_API_KEY=          # screenshot dekhne ke liye
OPENROUTER_API_KEY=
```

---

## 17. NAYE AI ASSISTANT KE LIYE INSTRUCTIONS

Agar tu naya AI hai jo ye project continue kar raha hai:

### Pehle ye karo
1. **Ye file puri padho** (kar liya ✅)
2. `docs/ARCHITECTURE.md` padho — code kaise organize hai + extend recipes
3. `docs/ROADMAP.md` padho — phase-wise plan
4. `docs/VOICE.md` padho (voice pe kaam karna ho)
5. `docs/DEPLOYMENT.md` padho (server pe kaam karna ho)

### Bolne ka tareeka
User **Hinglish** mein baat karta hai aur **Hinglish jawab** pasand karta hai.
Code ke comments bhi Hinglish mein hain — **wahi style maintain karo.**
Formal Hindi ("aap", "kripya") mat use karo — dostana ("bhai", "tu") theek hai.

### Kaam karne ka tareeka
- **Sach bolo.** Jo nahi ho sakta, saaf bolo. User ne specifically appreciate kiya
  ki usko honest limitations bataye gaye
- **Test karo, phir bolo "ho gaya".** Is project mein 6 asli bugs testing se mile
- **Model naam web se verify karo** — training data ke naam purane ho sakte hain
- **₹0 budget constraint** — koi paid dependency nahi
- **Safety layer mat todo** — feature add karo, brake mat hatao
- **Pillars ke against kaam mat karo** — Hinglish-first, self-healing,
  budget hardware, Indian apps

### Sabse pehla kaam (recommended)
**Asli hardware pe test karvao** — mic, speaker, phone. Phase 1 aur 2 ka code
sandbox mein bana tha jahan hardware nahi tha. Jo bugs milenge wo asli honge,
aur unko fix karna naya feature banane se zyada valuable hai.

---

## 18. QUICK REFERENCE

| | |
|---|---|
| **Repo** | https://github.com/theafzalhussain/Sarthi |
| **Commits** | 16 |
| **Files** | 53 tracked, 56 Python |
| **Lines** | ~15,300 Python (+2,700 tests) |
| **Python** | 3.9+ |
| **Tools** | 34 |
| **Indian apps** | 110 |
| **LLM providers** | **8** (chaar ek hi NVIDIA key pe) |
| **ASR corrections** | 65 rules |
| **Tests** | **238 pass** — `python run_tests.py` |
| **Interface** | English (professional) |
| **Agent ki baat** | User ki bhasha — `SAARTHI_LANGUAGE=auto` |
| **Max steps** | 25 |
| **Phase 1** | ✅ Complete — foundation |
| **Phase 2** | ✅ Complete — voice |
| **Phase 3** | 🟡 Part 1 done — BrowserDevice + tab discipline |
| **Phase 4-5** | ⬜ Pending — Android app, vector memory |
| **Real hardware test** | ❌ Pending — **`python hardware_check.py`** |

### Naye AI ke liye 60-second summary

1. `python run_tests.py` chala — 195 pass hone chahiye. Kuch fail ho to
   **wahi pehle theek kar**, naya feature baad mein.
2. Interface **English** hai, agent ki **baat user ki bhasha** mein. Ye do
   alag cheezein hain — confuse mat kar.
3. **8 providers**, best pehle (`deepseek`). Chaar ek hi NVIDIA key pe.
4. **Safety layer mat todo.** Hard blocks (OTP/PIN/`rm -rf`) ko `/auto`
   bhi bypass nahi karta — ye design hai, bug nahi.
5. Self-healing ka order: **semantic pehle, coordinates last.** Ulta karna
   payment screen pe khatarnak hai (BUG#3).
6. Bacha hua sabse valuable kaam: **asli hardware pe test** — mic, speaker,
   phone. Wo sirf user kar sakta hai.
