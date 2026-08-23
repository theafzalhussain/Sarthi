# Architecture

Ye document batata hai code kaise organize hai aur **isko extend kaise karna hai**.

---

## Ek command ka safar

```
tu bola: "bhai paytm khol ke dhai hazaar ka bill bhar de"
    │
    ▼
[1] lang/normalize.py — parse()
    Hinglish -> structured hints
    intent=pay, app=paytm(net.one97.paytm), amount=2500, risky=True
    │
    ▼
[2] agent.py — run_turn()
    System prompt + memory + skills + hints -> messages
    │
    ▼
[3] brain/router.py — think()
    Groq try -> fail ho to OpenRouter -> screenshot ho to Gemini
    │
    ▼
[4] LLM: "app_kholo(app=paytm) chalao"
    │
    ▼
[5] tools/registry.py — execute()   <-- SAARI SAFETY YAHAN
    validate args -> types theek karo -> risky? confirmation lo -> chalao
    │
    ▼
[6] devices/android.py
    ADB: monkey -p net.one97.paytm ...
    │
    ▼
[7] Result LLM ko wapas -> loop repeat -> final jawab
```

**Poora loop `agent.py` mein ~100 line ka hai.** Jaan-boojh ke — samajh aana zaroori hai.

---

## Layers

### `brain/` — LLM
Provider-agnostic. Naya provider add karna:

```python
# brain/mera_provider.py
from .base import LLMProvider

class MeraProvider(LLMProvider):
    async def chat(self, messages, tools=None, temperature=0.3, max_tokens=2048):
        ...
        return LLMResponse(text=..., tool_calls=[...])
```
Phir `router.py` ke `_build_provider()` mein ek line.

OpenAI-compatible API hai? To kuch likhna hi nahi — `openai_compat.py` ke `BASE_URLS` mein URL daal de.

**Fallback:** `PREFERRED_ORDER = [groq, openrouter, gemini]`. Ek provider rate-limit hit kare to agla chalta hai. Free tier pe ye zaroori hai.

---

### `lang/` — Hinglish (PILLAR #1)

| File | Kaam |
|---|---|
| `lexicon.py` | Data: 120+ Indian apps, 18 intents, risky words, Hindi numbers, device words |
| `normalize.py` | Devanagari→roman, number parsing, filler removal, `parse()` |
| `prompts.py` | System prompt, language rules, safety rules |

**Design ka core:** LLM ko sirf raw text nahi, **pre-analyzed hints** bhi jaate hain:

```
bhai phonepe se saadhe teen sau rupay mummy ko bhej de

[Hinglish analysis]
- Lagta hai user ye chahta hai: send
- Mentioned apps: phonepe (com.phonepe.app)
- Amount detected: 350
- RISKY COMMAND — confirmation lena zaroori hai
```

Isse LLM ko guess nahi karna padta → accuracy badhti hai. **Yahi differentiator hai.**

⚠️ **Extend karte waqt dhyan:** har match **word boundary** (`\b`) se hona chahiye. Warna `"paytm"` ke andar `"yt"` (YouTube) match ho jaata hai, aur `"paytm"` ke andar `"pay"` se app kholna bhi risky flag ho jaata hai. Ye bug ho chuka hai — fix hai, tod mat.

Naya app add karna:
```python
# lexicon.py
INDIAN_APPS = {
    "mera app": "com.example.package",
    ...
}
```

---

### `voice/` — Bolna aur sunna (Phase 2)

| File | Kaam |
|---|---|
| `hinglish_asr.py` | **PILLAR #1 voice pe** — biasing + 55 correction rules |
| `audio.py` | Mic recording, silence detection, playback |
| `stt.py` | Whisper wrapper (offline) |
| `tts.py` | 5 TTS backends with auto-select |
| `wake.py` | 3 wake modes |
| `session.py` | Pura voice loop |

**Testing design (important):** `SilenceDetector` aur `prepare_text_for_speech` **pure logic** hain — mic ke bina test ho jaate hain. Hardware I/O jaan-boojh ke alag rakha hai. Isliye Phase 2 ka pura core sandbox mein verify ho gaya, bina mic ke.

**Do subtle cheezein jo miss karna aasaan hai:**

1. **int16 → float32 conversion** (`stt.py`)
   Whisper `[-1, 1]` range maangta hai, mic `int16` (0-32767) deta hai. Divide by 32768 zaroori hai — warna Whisper ko **sirf shor** sunai deta hai.

2. **Porcupine ka frame size** (`wake.py`)
   Porcupine **exactly 512 samples** maangta hai, hamara chunk 480 hai. Frame buffer banaya hai. Ye miss karne pe Porcupine **chup-chaap** kaam nahi karta.

**Compounding fayda:** `session.refresh_vocabulary()` memory aur skills se Whisper ki vocabulary banata hai. Matlab jitna agent ko sikhaayega, utna accha wo sunega. Detail: [VOICE.md](VOICE.md)

---

### `devices/` — "Sab devices ka access"

Yahi wo architectural faisla hai jo tera "har device" sapna possible banata hai.

```
Device (abstract)
  ├── AndroidDevice   ADB
  ├── DesktopDevice   shell + files + (optional) mouse/keyboard
  └── BrowserDevice   <- tu banayega (Phase 3)
```

**Capability system:** har device declare karta hai wo kya kar sakta hai. Laptop pe `tap` nahi hota, phone pe `shell` limited hai. Agent sirf available tools dekhta hai.

Naya device:
```python
class MeraTV(Device):
    kind = "tv"
    capabilities = {Capability.TAP, Capability.LAUNCH_APP}

    async def is_available(self): return True
    async def info(self): return ActionResult.success("Mera TV")
    async def tap(self, x, y): ...
    async def launch_app(self, app): ...
```
```python
manager.register(MeraTV(name="tv"))
```

**Agent ka code ek line nahi badalta.** Bas.

#### Reliability ka core: `tap_text` vs coordinates

```python
await device.tap_text("Recharge")     # ✅ PREFERRED
await device.tap(540, 360)            # ⚠️ last resort
```

`tap_text` andar `ui_tree()` se screen padhta hai aur text se element dhoondhta hai. Coordinates screen size aur UI update pe toot jaate hain — text nahi.

`ui_tree()` screenshot se **behtar** hai:
- Exact text (OCR ki galti nahi)
- Exact coordinates
- **Bahut kam tokens** (free tier bachta hai)
- Budget phone pe fast

---

### `tools/` — Agent ke haath

```python
class MeraTool(Tool):
    name = "mera_kaam"
    description = "Ye kaam karta hai. LLM isse padh ke decide karta hai."
    parameters = {
        "type": "object",
        "properties": {"cheez": {"type": "string", "description": "..."}},
        "required": ["cheez"],
    }
    risky = False          # True -> confirmation liya jaayega
    requires_capability = None

    async def run(self, ctx: ToolContext, cheez: str) -> ActionResult:
        return ActionResult.success("ho gaya")
```
```python
registry.register(MeraTool())
```

**Rules:**
1. **Exception throw mat karo** — `ActionResult.failure()` return karo. Agent ko structured error chahiye taaki wo recover kar sake.
2. `description` LLM ke liye likho, insaan ke liye nahi. Yahi wo padh ke decide karta hai.
3. Risky ho to `risky = True`. `registry.execute()` khud confirmation le lega.

#### `registry.execute()` — single chokepoint

Har tool call yahin se guzarta hai:
```
validate args -> coerce types -> risky? confirm -> run -> never raise
```

Type coercion zaroori hai: LLM `"500"` bhejta hai jahan `500` chahiye, aur skill ka `{amount}` resolve hoke `1240` (int) ban jaata hai jahan `"1240"` (string) chahiye. Dono handle hote hain.

---

### `memory/` — Yaaddasht

SQLite, do tables:
- **facts** — permanent baatein (`mummy ka number`, `ghar ka address`)
- **conversations** — chat history (`"wahi jo pichli baar kiya tha"` isse chalta hai)

Vector DB nahi hai — abhi zarurat nahi. Chahiye to `ChromaDB` add kar sakta hai, par pehle SQLite se kaam chala.

---

### `skills/` — DIKHA DO MODE (killer feature)

| File | Kaam |
|---|---|
| `store.py` | Skills ka DB + **parameterization** |
| `recorder.py` | Steps capture karna |
| `runner.py` | Replay + **self-healing** |

#### Parameterization
Recording ke waqt jo values badalti hain wo placeholder ban jaati hain:

```
Record hua:  text_likho(text="2500")
Save hua:    text_likho(text="{amount}")
Chalane pe:  text_likho(text="1240")
```

Isliye ek demo hamesha ke liye kaam karta hai. `guess_parameter_name()` decide karta hai (number→amount, 10-digit→number, email, date).

#### Self-healing — 3 level

Har step **do** targets store karta hai: `target_text` (primary) + `target_coords` (fallback).

```
LEVEL 1  target_text se element mila?           -> chalao
LEVEL 2  nahi mila -> screen padho, LLM se pucho
         "Electricity ka kaam ab kaunsa button karega?"
         -> "Bijli Bill" -> tap karo
         -> SKILL PERMANENTLY UPDATE karo
LEVEL 3  LLM bhi na dhoondhe -> purane coordinates
         (par pehle user se PUCHO)
```

**Order jaan-boojh ke aisa hai.** Agar text nahi mila to UI badal gaya hai — aise waqt purane coordinates pe tap karna khatarnak hai, kyunki wahan ab **doosra button** ho sakta hai. ADB ko farak nahi padta, tap "safal" dikhega, par galat kaam ho jaayega. Payment screen pe ye bahut bura hai.

Isliye pehle **semantic** healing (samajh ke), phir coordinates — aur wo bhi permission ke saath.

Normal automation tools (Tasker, macros) yahi galat karte hain.

---

## Design principles

| Principle | Kyun |
|---|---|
| **Tools exception nahi throw karte** | Agent ko structured error chahiye recover karne ke liye |
| **Fail-safe defaults** | Confirmation ka tareeka na ho → mana kar do |
| **Optional dependencies degrade** | `pyautogui` na ho to shell chalta rahe, crash na ho |
| **Text > coordinates** | UI badalta hai, text usually nahi |
| **`ui_tree` > screenshot** | Sasta, exact, fast — free tier aur budget phone dono ke liye |
| **Framework nahi** | Loop 100 line ka hai. Chhota pad jaaye tab LangGraph laayenge |
| **Python 3.9+** | Purane laptop pe chale (`from __future__ import annotations` har file mein) |

---

## Extend karne ki cheat sheet

| Kya add karna hai | Kahan |
|---|---|
| Naya app | `lang/lexicon.py` → `INDIAN_APPS` |
| Naya Hinglish phrase | `lang/lexicon.py` → `VERB_INTENTS` |
| Naya tool | `tools/` mein file, phir `default_registry()` |
| Naya device | `devices/` mein `Device` subclass, phir `manager.register()` |
| Naya LLM provider | `brain/` — ya OpenAI-compatible ho to bas `BASE_URLS` |
| Naya risky pattern | `tools/safety.py` |
| **ASR correction** | `voice/hinglish_asr.py` → `SAFE_CORRECTIONS` (word boundary zaroori!) |
| **Context-dependent ASR fix** | `voice/hinglish_asr.py` → `CONTEXT_CORRECTIONS` (enablers + blockers) |
| **Naya TTS backend** | `voice/tts.py` → `TTSBackend` subclass, phir `BACKEND_ORDER` |
| **Naya wake mode** | `voice/wake.py` → `WakeDetector` subclass, phir `WAKE_MODES` |
