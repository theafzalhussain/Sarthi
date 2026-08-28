# Phase 5 implementation prompt — Powerful banao

Ye READY-TO-PASTE prompt hai. Apne Kiro CLI / VS Code agent mein paste karo.

**Phase 5 ke 5 hisse hain (5A se 5E).** Prompt mein order diya hai — usi
kram mein karna hai, aur beech mein rukna hai.

`---` ke beech ka hissa copy karna hai.

---

SAARTHI repo mein Phase 5 implement karo — on-device LLM, vector memory,
multi-step planning, skill chaining, aur proactive suggestions.

## PROJECT KE NON-NEGOTIABLE RULES

1. **Budget ₹0.** Koi paid dependency nahi. Naya pip package **sirf tab**
   jab bilkul zaroori ho, aur wo bhi **optional** ho (import fail ho to
   feature disable ho, crash NAHI).
2. **Python 3.9+ compatible** rehna hai (purane laptop — Pillar #3).
3. **Code comments HINGLISH mein.** UI text English mein. Ye style mat badlo.
4. **Safety layer CHHUNA NAHI** — `saarthi/tools/safety.py`,
   `saarthi/tools/redact.py`, `saarthi/tools/banking.py` jaise hain waise.
   Feature add karo, brake mat hatao.
5. **Tests stdlib `unittest` se**, pytest nahi. `python run_tests.py`.
6. **HAR naya test bug WAPAS daal ke VERIFY karo:** test likho, fix ulta
   karo, confirm karo test FAIL hota hai, phir fix wapas lagao.
7. **🚨 SOURCE-INSPECTION TEST SE BACHO.** Is project mein wo **paanch
   baar** dhoka de chuka hai:
   - `assertIn("xyz", source)` COMMENT pe match kar jaata hai
   - Aur DEAD CODE pe bhi pass ho jaata hai (code path chalta hi nahi,
     par shabd source mein hota hai)

   **Niyam:** pehle **BEHAVIOUR** test likho (fake object inject karke
   asli code chalao). Possible na ho to **AST** use karo, plain text
   NAHI. `docs/HANDOFF.md` ka "SOURCE-INSPECTION TEST" section padho.
8. Khatam hone pe `python run_tests.py`, test count `README.md` /
   `docs/HANDOFF.md` / `docs/UPDATE.md` / `docs/HARDWARE_TEST.md` mein
   update, aur `main` pe direct push.

## CURRENT STATE — VERIFIED HAI, DOBARA KHOJ MAT KARO

- **468 tests pass**, ~27,000 lines Python, 40 tools
- 9 LLM providers, 4 devices (android/phone/browser/desktop)
- Phase 1, 2, 3, 4A, 4B complete
- Security layer: `safety.py` (hard blocks) + `redact.py` (card/OTP/CVV)
  + `banking.py` (app lock)

### Brain layer — `saarthi/brain/`

```python
# openai_compat.py
BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "bluesminds": "https://api.bluesminds.com/v1",
    "opencode": "https://opencode.ai/zen/v1",
    "nvidia": _NVIDIA_NIM, "deepseek": _NVIDIA_NIM,
    "muse": _NVIDIA_NIM, "gemma": _NVIDIA_NIM,
}

class OpenAICompatProvider(LLMProvider):
    def __init__(self, config: ProviderConfig, base_url: str | None = None)
    # /models discovery line ~165, /chat/completions line ~241 aur ~334
    # (doosra streaming ke liye)
```

```python
# router.py line ~38
def _build_provider(config) -> LLMProvider | None:
    if config.name == "gemini":
        return GeminiProvider(config)
    if config.name in BASE_URLS:
        return OpenAICompatProvider(config)
    return None
```

### Config — `saarthi/config.py`

```python
@dataclass
class ProviderConfig:
    name: str
    api_key: str | None
    model: str
    supports_vision: bool = False
    supports_tools: bool = True
    # extra payload, max_tokens, top_p...

    @property
    def is_available(self) -> bool:          # line ~310
        return bool(self.api_key and self.api_key.strip())
```

Helpers already hain: `_env_bool`, `_env_int`, `_env_choice`,
`_provider_tuning(name)`.
`DEFAULT_MODELS`, `DEFAULT_PROVIDER_ORDER`, `TIGHT_RATE_LIMIT_PROVIDERS`
bhi wahin hain.

### Memory — `saarthi/memory/store.py` (386 lines, plain SQLite)

```python
# Tables: facts, conversations
remember(...)         line ~136
recall(key)           line ~161
_search_sync(...)     line ~165   ->  WHERE key LIKE ? OR value LIKE ?
log_turn(...)         line ~242
history(...)          line ~287
_search_history_sync  line ~293   ->  WHERE LOWER(content) LIKE ?
build_context(max_facts=25)  line ~328  -> facts ko system prompt mein daalta hai
stats()               line ~367
prune_old_conversations(keep_days=90)  line ~379
_run(func, *args)     line ~109   -> sync DB calls ko async banata hai
```

Tools: `yaad_rakho`, `yaad_karo`, `bhool_jao`, `purani_baat_dhoondho`
(`saarthi/tools/memory_tools.py`).

### Agent loop — `saarthi/agent.py`

```python
async def run_turn(self, user_input: str) -> TurnResult:   # line ~176
    ...
    ctx = self._build_context()                            # line ~220
    tool_schemas = self.tools.schemas(available_only_for=ctx)
    while steps < self.settings.max_steps:                 # line ~227, default 25
        # brain.think_stream() -> tool_calls -> _execute_tools_parallel()
        # screenshot caching + dedupe (Phase 3) line ~296 ke aas-paas
    # line ~392: "N steps ho gaye par kaam pura nahi hua"
```

**Koi planner NAHI hai** — bas iterative tool-calling loop.

### Skills — `saarthi/skills/`

```python
# store.py
@dataclass
class SkillStep:
    action: str; params: dict; target_text: str
    target_coords: tuple[int,int] | None; notes: str

@dataclass
class Skill:
    name: str; description: str; device_kind: str = "android"
    steps: list[SkillStep]; params: list[str]
    run_count: int; success_count: int; last_run: float | None

# runner.py
async def run(...)         line ~146
async def _run_step(...)   line ~212  -> registry.execute(ToolCall(name=step.action, ...))
                                         KOI WHITELIST CHECK NAHI
async def _heal_step(...)  line ~231
async def _heal_with_llm() line ~325

# recorder.py
RECORDABLE_ACTIONS = {app_kholo, app_band_karo, text_pe_tap,
                      coordinate_pe_tap, text_likho, key_dabao,
                      scroll_karo, command_chalao}
SKIP_ACTIONS = {..., skill_chalao, skill_seekho, skills_ki_list, ...}
```

---

# 5A — ON-DEVICE LLM (OLLAMA) — YE PEHLE KARO

## Kyun sabse pehle

User abhi rate limit se ladh raha hai. Groq ke free tier mein 8000 TPM
hai aur system prompt hi ~5000 token ka hai — provider order **do baar**
badalna pada (`TIGHT_RATE_LIMIT_PROVIDERS` isi ka record hai).

Ollama se ye problem **poori tarah khatam**:
- Zero rate limit, zero cost, zero internet
- **Zero data leak** — screen ka text, notifications, sab local rehta hai
  (`redact.py` ka poora kaaran hi ye tha ki data cloud jaa raha tha)

Aur mehnat sabse kam hai — Ollama **OpenAI-compatible** endpoint deta hai
(`http://localhost:11434/v1`), to `OpenAICompatProvider` bina badle chal
jaayega.

## Kya karna hai

1. `BASE_URLS` mein entry:
   ```python
   "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/v1",
   ```
   ⚠️ `OLLAMA_HOST` env se aana chahiye — kuch log Ollama doosre port ya
   doosri machine pe chalate hain.

2. `DEFAULT_MODELS` mein: `"ollama": "qwen2.5:7b"` (ya jo bhi tool-calling
   support karta ho — **tool calling ZAROORI hai**, warna agent kaam nahi
   kar payega, sirf baat karega)

3. `Settings.load()` mein `ProviderConfig` register karo.

4. **🚨 SABSE ZARURI — `is_available` ka problem:**

   ```python
   @property
   def is_available(self) -> bool:
       return bool(self.api_key and self.api_key.strip())
   ```

   **Ollama ko API key NAHI chahiye** (local server hai, koi auth nahi).
   Iska matlab wo `available_providers` mein **kabhi aayega hi nahi** aur
   chup-chaap ignore ho jaayega.

   Ye theek karo — par **dhyan se**:
   - `is_available` ko aise badlo ki key-less local providers allowed hon
   - Par baaki providers pe purana behaviour **bilkul same** rahe (warna
     bina key wale cloud providers try honge aur har turn mein bekaar
     401 aayega)
   - Ek saaf tareeka: `ProviderConfig` pe `requires_key: bool = True`
     field, aur Ollama pe `False`. Tu behtar design soche to wo bhi theek.
   - **Regression test likho** ki bina key wala cloud provider abhi bhi
     unavailable hai.

5. **Provider order mein Ollama kahan?**
   - Default order mein daalo par **aakhir ke paas** — kyunki jab tak user
     ne Ollama install nahi kiya, uska request fail hoga aur ek bekaar
     round-trip lagega
   - **BEHTAR:** `is_available` mein ek sasta check — Ollama chal raha hai
     ya nahi. Par **startup pe network call MAT karo** (Phase 3 ka sabak —
     startup slow karna mana hai). Lazy check karo, ya user `.env` mein
     `OLLAMA_ENABLED=true` likhe.
   - Jo bhi chuno, **wajah comment mein likho**.

6. `.env.example` mein section — Ollama install kaise kare, kaunsa model
   pull kare, RAM ki zarurat kitni. Aur ye batao ki iska sabse bada fayda
   privacy + no-rate-limit hai.

7. `hardware_check.py` mein Ollama check add karo (ek naya flag ya `--keys`
   ke andar): Ollama chal raha hai? Kaunse models pulled hain? RAM kaafi
   hai? Existing `check_phone_http()` ka pattern follow karo — wo isi tarah
   ka diagnostic hai.

## Tests (5A)

- `BASE_URLS` mein `ollama` hai, aur `OLLAMA_HOST` env se override hota hai
- `_build_provider()` Ollama ke liye `OpenAICompatProvider` deta hai
- **Bina API key Ollama available hai** (behaviour test — `Settings.load()`
  se `available_providers` mein aaye)
- **REGRESSION: bina key wala CLOUD provider abhi bhi unavailable hai**
  (ye sabse zaroori test hai — warna har turn mein bekaar 401)
- Payload OpenAI format mein jaata hai (existing `FakeHTTP` use karo,
  `tests/helpers.py` mein hai)
- `supports_tools=True` hai (warna agent bekaar hai)
- Ollama band ho to **clear actionable error** mile ("ollama serve chala
  hai? `ollama list` se model check kar"), crash nahi

**Yahan RUKO aur batao.** 5A akela hi bada fayda deta hai.

---

# 5B — VECTOR MEMORY (semantic recall)

## Problem

`_search_sync()` ye karta hai:
```sql
WHERE key LIKE ? OR value LIKE ?
```

Matlab **exact substring** hi milta hai. User pooche *"wo cheez jo pichle
mahine ki thi"* — kuch nahi milega. *"bijli"* likhe to *"electricity bill"*
nahi milega.

## ⚠️ Dependency ka faisla — dhyan se socho

ChromaDB `requirements.txt` mein **commented** hai (line ~47). Wo ~200MB
laata hai (onnxruntime + tokenizers). **Pillar #3 (purana laptop, ₹0)** ke
hisaab se ye bhaari hai.

**Teen options — tu decide kar, par wajah likho:**

| Option | Fayda | Nuksaan |
|---|---|---|
| **SQLite FTS5** | **stdlib mein hai**, zero install, fast | Semantic nahi — sirf better keyword (stemming, ranking) |
| **Ollama embeddings** | Sach mein semantic, no new dep (5A mein Ollama already aa raha hai) | Ollama chalna zaroori |
| ChromaDB | Full vector DB | ~200MB, Pillar #3 pe bhaari |

**Mera suggestion: FTS5 + Ollama embeddings ka hybrid.**
- FTS5 hamesha chale (fallback, zero dep)
- Ollama ho to embeddings se semantic search bhi ho (`/v1/embeddings`
  endpoint, `nomic-embed-text` model)
- Embeddings ko SQLite mein BLOB ke roop mein rakho, cosine similarity
  pure Python/numpy se — koi vector DB nahi chahiye

Par tu behtar design soche to wo karo. **Sirf ye rule hai: bina extra
install ke bhi kuch na kuch kaam kare.**

## Kya karna hai

- `memory/store.py` mein semantic search add karo
- **Purana `LIKE` search FALLBACK ke roop mein zinda rahe** — embeddings
  na ho to bhi memory kaam kare
- `purani_baat_dhoondho` aur `yaad_karo` tools isse use karein
- Existing `remember()` / `recall()` ka **API na badle** (backward compat)
- Migration: purane facts ke embeddings lazily banao (startup pe sab
  compute karna slow hoga)

## Tests (5B)

- Semantic search kaam karta hai (fake embeddings inject karke — asli
  Ollama pe depend NAHI karna)
- **Embeddings available na ho to `LIKE` fallback chalta hai** (behaviour test)
- Purana `remember`/`recall` API bilkul same (regression)
- Khali DB pe crash nahi
- Cosine similarity ka math sahi hai (pure function, easy test)
- Migration idempotent hai (dobara chalane pe duplicate embeddings nahi)

---

# 5C — MULTI-STEP PLANNING

## Problem

`run_turn()` ka loop LLM ko har step pe poocha karta hai "ab kya?".
Koi plan nahi banta. Bade kaam pe:
- Agent bhatakta hai (ek hi cheez do baar karta hai)
- `max_steps=25` khatam ho jaate hain aur "steps khatam" milta hai
- User ko pata nahi chalta ki kitna kaam bacha hai

## Kya karna hai

Ek **halka** planner — over-engineer mat karna:

1. Task complex ho to pehle LLM se **plan** maango (3-7 steps, plain text
   list). Simple task ("paytm kholo") pe planning **skip** karo — wo ek hi
   step ka kaam hai aur extra LLM call bekaar hai.

2. Plan ko `TurnResult` mein rakho aur user ko dikhao (`saarthi/ui.py` ka
   existing pattern use karo).

3. Har step ke baad progress track karo. Plan se bhatak jaaye to
   **re-plan** karo (ek hi baar, warna infinite loop).

4. `max_steps` khatam ho to **ab batao ki kya hua aur kya bacha** — sirf
   "steps khatam" bolna bekaar hai.

## ⚠️ Dhyan

- **Extra LLM call ka cost hai.** Simple task pe planning na chale — iska
  test likho.
- Screenshot caching (Phase 3) ko mat todo.
- `tool_call` ↔ `tool_result` pairing kabhi mat todo (Phase 3 ka sabak —
  LLM API error deta hai).

## Tests (5C)

- Simple task pe planning **skip** hoti hai (extra LLM call nahi) — behaviour test
- Complex task pe plan banta hai
- Re-plan **ek hi baar** hota hai (infinite loop guard)
- `max_steps` khatam hone pe progress message aata hai (sirf "steps khatam" nahi)
- `tool_call`/`tool_result` pairing safe hai

---

# 5D — SKILL CHAINING (chhota kaam, par guard zaroori)

## Abhi kya haal hai

`_run_step()` (runner.py line ~212) `registry.execute()` ko **bina
whitelist** call karta hai. Matlab ek step jiska `action` = `"skill_chalao"`
ho, wo **nested skill chala dega**.

Par:
- Recorder aisa step **record hi nahi kar sakta** (`skill_chalao`
  `SKIP_ACTIONS` mein hai)
- **Koi recursion guard nahi hai** — hand-written chain infinite loop kar
  sakti hai
- Parameters nested skill tak pass karne ka koi tareeka nahi

## Kya karna hai

1. **🚨 RECURSION GUARD PEHLE.** Ye feature se **pehle** aana chahiye,
   warna infinite loop ban sakta hai:
   - Max depth (jaise 3)
   - Cycle detection — `A -> B -> A` pakdo
   - Depth cross ho to **saaf error**, chup-chaap fail nahi

2. Skill se skill call karne ka saaf tareeka + parameters pass karna

3. Recorder ise support kare (`SKIP_ACTIONS` se hatao **sirf tab** jab
   guard lag chuka ho)

4. `skills_ki_list` mein dikhao ki kaunsi skill kisko call karti hai

## Tests (5D)

- Skill dusri skill call kar sakti hai
- **Direct recursion (`A -> A`) pakdi jaati hai** — saaf error
- **Indirect cycle (`A -> B -> A`) pakdi jaati hai**
- Max depth cross pe saaf error, crash nahi
- Parameters nested skill tak pahunchte hain
- Purani single-level skills bilkul same chalti hain (regression)

---

# 5E — PROACTIVE SUGGESTIONS

## Abhi

Kuch nahi hai. `schedul`/`cron`/`remind` ka ek bhi match nahi. Agent
**sirf** tab chalta hai jab user bolta hai.

## Kya karna hai

1. Reminder store — SQLite mein (`memory/store.py` ka pattern follow karo,
   ya alag table). **Koi naya dependency nahi** — `asyncio` + SQLite kaafi hai.

2. CLI start pe due reminders dikhao. **Background thread se user ko
   interrupt MAT karo** — wo bahut annoying hai aur CLI output kharab
   karta hai.

3. Naye tools: `yaad_dila_do` (reminder set), `reminders_dikhao`.

4. Recurring reminders (rozana/hafte mein) — simple rakho, cron syntax mat
   banao.

## ⚠️ Dhyan

- **Notification spam se bacho.** Ek reminder ek baar dikhe, phir tab tak
  na dikhe jab tak user dismiss/snooze na kare.
- Reminder text mein sensitive data ho sakta hai — `redact.py` **use karo**
  jab wo LLM ko jaaye.
- Time zone: user ka local time use karo, UTC mein store karo.

## Tests (5E)

- Reminder set + list ho jaata hai
- Due reminder detect hota hai, future wala nahi
- Ek hi reminder do baar nahi dikhta (dedupe)
- Recurring reminder next occurrence sahi banata hai
- Khali reminder list pe crash nahi
- Reminder ka text LLM ko jaane se pehle redact hota hai (behaviour test)

---

# 6 — DOCS

1. `docs/ROADMAP.md` — Phase 5 ke jo hisse ho gaye unko ✅ mark karo
2. `.env.example` — saare naye env vars, **kyun** ke saath (is repo ka style)
3. `docs/HANDOFF.md` — status update. Naya bug mile to bug table mein row
   add karo (abhi 31 rows hain)
4. Test count sab jagah update

---

# ORDER — isi kram mein, beech mein rukna hai

```
1. 5A (Ollama)          <- PEHLE. Akela hi bada fayda. Yahan RUKO.
2. 5B (Vector memory)   <- 5A ke Ollama embeddings isme kaam aayenge
3. 5C (Planning)
4. 5D (Skill chaining)  <- recursion guard PEHLE
5. 5E (Proactive)
6. Docs
```

Ek saath sab karne ki koshish **mat** karna. 5A khatam karke batao — wo
akela hi rate limit ki problem khatam kar deta hai.

# ACCEPTANCE CRITERIA

- [ ] `python run_tests.py` — sab pass, 468 se zyada
- [ ] Har naya test bug wapas daal ke verify kiya (**batao kya verify kiya**)
- [ ] Koi naya **required** dependency nahi — sab optional, import fail pe
      feature disable ho aur clear message mile
- [ ] **REGRESSION: bina key wala cloud provider abhi bhi unavailable hai**
- [ ] Embeddings na ho to memory ka `LIKE` fallback chalta hai
- [ ] Skill chaining mein recursion guard hai (direct aur indirect dono)
- [ ] Simple task pe planning skip hoti hai
- [ ] `python cli.py` aur `python hardware_check.py --keys` chalte hain
- [ ] Purane 468 tests mein se ek bhi nahi toota
- [ ] `main` pe push

Har hisse ke baad short summary do: kya bana, kaun se test add hue, kaun
sa bug re-introduce karke verify kiya, aur kya kaam **nahi** karta
(imaandaari se — jo nahi chala wo bhi batao).
