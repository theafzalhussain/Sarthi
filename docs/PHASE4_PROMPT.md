# Phase 4 implementation prompt — Android App

Ye READY-TO-PASTE prompt hai. Apne Kiro CLI / VS Code agent mein paste karo.

**Phase 4 do hisson mein hai. 4A PEHLE karo — wo akela bhi poora kaam hai
aur bina phone ke test ho jaata hai. 4B (Kotlin app) uske baad.**

`---` ke beech ka hissa copy karna hai.

---

SAARTHI repo mein Phase 4 implement karo — Android app + AccessibilityService,
taaki ADB/USB cable ki zarurat khatam ho jaaye.

## PEHLE YE PADHO — project ke non-negotiable rules

1. **Budget ₹0.** Koi paid dependency nahi. Python side pe koi NAYA pip
   package nahi — `httpx` already hai, wahi use karo.
2. **Python 3.9+ compatible.**
3. **Code comments HINGLISH mein.** UI text English mein. Ye style mat badlo.
4. **Safety layer CHHUNA NAHI** — `saarthi/tools/safety.py` jaisa hai waisa.
   OTP/PIN/password type karne ka hard block, aur final payment button na
   dabane ka rule — dono jaise hain waise rehne do.
5. **Tests stdlib `unittest` se**, pytest nahi. `python run_tests.py`.
6. **HAR naya test bug WAPAS daal ke VERIFY karo:** test likho, fix ulta
   karo, confirm karo test FAIL hota hai, phir fix wapas lagao. Jo test bug
   ke saath bhi pass ho jaaye wo bekaar hai — is repo mein aisa TEEN baar
   ho chuka hai.
7. **Source-inspection test likhne ho to AST use karo, plain text search
   NAHI.** Do baar aisa hua ki test COMMENT pe match kar gaya (comment mein
   hi likha tha "aisa mat karo") aur galat fail/pass diya.
8. Khatam hone pe `python run_tests.py`, test count `README.md` /
   `docs/HANDOFF.md` / `docs/UPDATE.md` / `docs/HARDWARE_TEST.md` mein
   update, aur `main` pe direct push.

## CURRENT STATE — VERIFIED HAI, DOBARA KHOJ MAT KARO

- **386 tests pass**, ~24,000 lines Python, 9 LLM providers, 39 tools
- Devices: `android` (ADB), `browser` (Playwright), `desktop` (pyautogui)
- Phase 1, 2, 3 complete

### Device abstraction — `saarthi/devices/base.py`

```python
class Capability(str, Enum):
    TAP, SWIPE, TYPE, KEY, SCREENSHOT, UI_TREE, LAUNCH_APP,
    LIST_APPS, CLOSE_APP, SHELL, FILES, NOTIFICATIONS, CLIPBOARD, DEVICE_INFO

@dataclass
class ActionResult:
    ok: bool
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)
    # .success() / .failure() constructors hain
    # Devices KABHI exception nahi throw karte — structured result dete hain

@dataclass
class UIElement:
    text: str = ""
    content_desc: str = ""        # accessibility label
    resource_id: str = ""
    class_name: str = ""
    clickable: bool = False
    editable: bool = False
    enabled: bool = True
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)   # (left, top, right, bottom)
    # properties: .center -> (x, y),  .label,  .matches(query)

class Device(ABC):
    kind: str
    capabilities: set[Capability]
    # ABSTRACT: is_available(), info()
    # Override karne wale (default "unsupported" dete hain):
    #   tap(x, y), swipe(x1, y1, x2, y2, duration_ms), type_text(text),
    #   press_key(key), screenshot(), ui_tree(), launch_app(app),
    #   close_app(app), list_apps(), run_shell(command), read_notifications()
    # Base class pe BANE HUE (inhe override karne ki zarurat nahi):
    #   can(capability), find_element(query), tap_text(text)
    # Sab methods async hain.
```

`screenshot()` ko `ActionResult.data["image_b64"]` dena hota hai.
`ui_tree()` ko `ActionResult.data["elements"]` = `list[UIElement]` dena hota hai.

### Skill format — `saarthi/skills/store.py` (YE BADALNA NAHI HAI)

```python
@dataclass
class SkillStep:
    action: str                                    # tool ka naam
    params: dict = field(default_factory=dict)
    target_text: str = ""                          # PRIMARY: text se dhoondo
    target_coords: tuple[int, int] | None = None   # FALLBACK: coordinates
    notes: str = ""

@dataclass
class Skill:
    name: str
    description: str = ""
    device_kind: str = "android"
    steps: list[SkillStep] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    run_count / success_count / last_run
```

### Recorder whitelist — `saarthi/skills/recorder.py`

```python
RECORDABLE_ACTIONS = {
    "app_kholo", "app_band_karo", "text_pe_tap", "coordinate_pe_tap",
    "text_likho", "key_dabao", "scroll_karo", "command_chalao",
}
```

### Device registration — `saarthi/devices/manager.py`

`DeviceManager.setup_defaults()` — Phase 3 ke baad multi-phone enumeration
karta hai (`list_adb_serials()`, `SAARTHI_ANDROID_SERIAL` pin, `android` alias
backward compat ke liye). Naya device isi function mein register hoga.

### Config — `saarthi/config.py`

Helpers already hain: `_env_bool`, `_env_int`, `_env_choice(key, allowed, default)`.
Naye settings inhi patterns se, aur `.env.example` mein document karo (is repo
ka style hai ki har setting ke saath **kyun** likha jaata hai).

---

# ARCHITECTURE — ye pehle samajh lo, warna galat cheez banegi

## Python agent phone pe NAHI chal sakta

SAARTHI ~24,000 lines Python hai — asyncio, httpx, faster-whisper. Chaquopy
ya Kivy se ise Android pe le jaana mahine ka kaam hai aur faster-whisper
wahan chalega hi nahi. **Agent laptop pe hi rahega.**

## To phone ka fayda kya?

Abhi phone control karne ke liye **ADB + USB cable** chahiye. Wo hatana hai.

## Sahi design: PHONE = SERVER, LAPTOP = CLIENT

```
   LAPTOP (Python agent)                    PHONE (Kotlin app)
   ─────────────────────                    ──────────────────
   AccessibilityDevice(Device)  ──HTTP──>   HTTP server (localhost:8080)
     .tap(x, y)                 POST /tap        │
     .ui_tree()                 GET  /ui_tree    ▼
     .tap_text("Send")                      AccessibilityService
                                              (asli tap karta hai)
```

**Ye direction (phone server, laptop client) JAAN-BOOJH KE hai:**

- Ye **ADB ka exact mirror** hai — laptop se phone ko command jaati hai.
  Isliye naya `AccessibilityDevice` `AndroidDevice` ka **drop-in
  replacement** hai.
- `saarthi/agent.py`, tools, skills, self-healing — **kisi mein ek line
  nahi badlegi**. Ye existing Device abstraction ka poora faayda hai.
- Python side pe koi naya dependency nahi — `httpx` already use hota hai.
- Ulta karne (laptop server, phone poll kare) se latency aur complexity
  dono badhti hai, aur `Device` interface fit nahi hoti.

## Faayde

| Abhi (ADB) | Phase 4 ke baad |
|---|---|
| USB cable ya `adb connect` pairing | Sirf WiFi, ek baar token daalo |
| `adb` install karna padta hai | Kuch install nahi |
| Developer options + USB debugging ON | Sirf Accessibility permission |
| `uiautomator dump` slow hai (~1-2s) | AccessibilityService turant deta hai |
| Sirf agent ke actions record hote hain | **User ke manual taps bhi record honge** |

---

# 🚨 SECURITY — YE SABSE ZARURI HISSA HAI, PEHLE PADHO

Tu phone pe ek HTTP server chala raha hai jo **kisi bhi app pe tap kar
sakta hai** — banking app included. Agar wo khula reh gaya to koi bhi same
WiFi pe (college, cafe, hostel) tere phone ko control kar sakta hai.

**Ye MUST hain, optional NAHI:**

1. **Shared token auth.** Har request mein `Authorization: Bearer <token>`
   header. Token app khud generate kare (random, 32+ char), app ki screen
   pe dikhaye, user `.env` mein `SAARTHI_PHONE_TOKEN` mein daale. Token
   galat/missing ho to `401`, aur koi action na ho.
2. **Token compare CONSTANT-TIME karo** — Python side pe `secrets.compare_digest`.
3. **Sirf private network pe bind karo.** Public IP pe kabhi nahi. App mein
   check karo ki WiFi private range mein hai (10.x, 172.16-31.x, 192.168.x).
4. **Server DEFAULT OFF.** User app mein explicitly toggle karke chalu kare.
   App band ho ya screen off ho to server band ho jaaye (ya user ka chuna
   hua timeout).
5. **Screen text mein password/OTP aa sakta hai.** `ui_tree` sab padh leta
   hai. Us data ko **kabhi log mat karo** — na phone pe, na laptop pe.
   `class_name` mein password field ho ya `editable` + masked ho to uska
   `text` khali bhejo.
6. **Existing safety layer phone side pe BHI lagao.** `/type` endpoint pe
   OTP/PIN/password type karne ka block wahi rehna chahiye jo
   `saarthi/tools/safety.py` mein hai. Do jagah defense honi chahiye —
   laptop pe aur phone pe.
7. **`/shell` jaisa endpoint BANANA HI NAHI.** AccessibilityService se
   shell nahi chalti, aur wo endpoint banane ki koshish bhi mat karna —
   wo pura phone kholne ke barabar hai.

Ye sab prompt ke tests mein bhi cover hona chahiye.

---

# PART 4A — PYTHON SIDE (ye PEHLE karo)

Ye akela bhi poora, useful increment hai. Aur **bina phone ke test ho
jaata hai** — isliye pehle ye. Ye HTTP contract define karta hai jo baad
mein Kotlin app implement karega.

## 4A.1 — Naya device adapter

Naya file: `saarthi/devices/accessibility.py`

```python
class AccessibilityDevice(Device):
    kind = "android"          # ADB wala bhi "android" hai — jaan-boojh ke
    capabilities = {TAP, SWIPE, TYPE, KEY, SCREENSHOT, UI_TREE,
                    LAUNCH_APP, CLOSE_APP, LIST_APPS, NOTIFICATIONS,
                    DEVICE_INFO}
    # SHELL capability NAHI — AccessibilityService se shell nahi chalti.
    # Ye important hai: agent ko `command_chalao` phone pe offer hi nahi hoga.
```

- `httpx.AsyncClient` se baat karo (already dependency hai)
- Har method `ActionResult` return kare, **exception kabhi na phenke**
- Timeout: normal actions 10s, `screenshot` 20s
- Phone na mile / token galat ho to **clear actionable error** do
  (`ActionResult.failure("Phone se connection nahi hua — app khula hai? token sahi hai?")`)

## 4A.2 — HTTP CONTRACT (ye exact rakhna — Kotlin app isi ko implement karega)

Sab requests pe header: `Authorization: Bearer <token>`

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{"ok":true,"model":"Redmi","android":"14","screen":[1080,2400]}` |
| POST | `/tap` | `{"x":500,"y":900}` | `{"ok":true}` |
| POST | `/swipe` | `{"x1":..,"y1":..,"x2":..,"y2":..,"duration_ms":300}` | `{"ok":true}` |
| POST | `/type` | `{"text":"hello"}` | `{"ok":true}` |
| POST | `/key` | `{"key":"back"}` | `{"ok":true}` |
| GET | `/ui_tree` | — | `{"elements":[ ... ]}` |
| GET | `/screenshot` | — | `{"image_b64":"..."}` |
| POST | `/launch_app` | `{"app":"paytm"}` | `{"ok":true}` |
| POST | `/close_app` | `{"app":"paytm"}` | `{"ok":true}` |
| GET | `/apps` | — | `{"apps":["com.x", ...]}` |
| GET | `/notifications` | — | `{"notifications":[{"app":..,"title":..,"text":..}]}` |
| POST | `/record/start` | — | `{"ok":true}` |
| POST | `/record/stop` | — | `{"ok":true}` |
| GET | `/recorded_actions` | — | `{"actions":[ ... ]}` |

**`/ui_tree` ka element JSON `UIElement` se EXACTLY match kare:**

```json
{
  "text": "Send Money",
  "content_desc": "",
  "resource_id": "com.paytm:id/send_btn",
  "class_name": "android.widget.Button",
  "clickable": true,
  "editable": false,
  "enabled": true,
  "bounds": [120, 1400, 960, 1520]
}
```

`bounds` = `[left, top, right, bottom]` — Python side pe tuple banega.

**`/recorded_actions` ka JSON `SkillStep` se map ho:**

```json
{
  "action": "text_pe_tap",
  "params": {"text": "Send"},
  "target_text": "Send",
  "target_coords": [540, 1460],
  "notes": "user tapped Send button in Paytm"
}
```

`action` sirf `RECORDABLE_ACTIONS` mein se ho. Kuch aur aaye to Python side
usse **skip** kare (crash na kare) aur `log.warning` de.

## 4A.3 — Config aur registration

`.env` mein:
```env
SAARTHI_PHONE_URL=http://192.168.1.5:8080
SAARTHI_PHONE_TOKEN=<app se copy karo>
```

`DeviceManager.setup_defaults()` mein:
- `SAARTHI_PHONE_URL` set ho to `AccessibilityDevice` register karo naam
  `phone` se, **aur** use `android` alias do agar koi ADB phone nahi mila
- ADB phone bhi ho aur URL bhi ho to **dono** register ho (naam alag:
  `android` vs `phone`). User dono use kar sake.
- URL set na ho to **kuch na badle** — abhi jaisa behaviour rahe

⚠️ `setup_defaults()` **sync** hai. Wahan koi network call **mat** karo —
availability lazily `is_available()` mein check hogi. Startup slow karna
mana hai (Phase 3 mein yahi galti se bacha gaya tha).

## 4A.4 — Skill import

Naya tool: `phone_se_seekho` (ya existing `skill_seekho` extend karo) —
`GET /recorded_actions` se actions laakar `Skill` banaye aur `SkillStore`
mein save kare.

Ye Phase 4 ka **asli inaam** hai: abhi recorder sirf **agent ke apne**
actions record karta hai. Iske baad **user ke manual taps** record honge.
`skills/store.py` aur `skills/runner.py` mein **kuch nahi badlega** — bas
ek naya recorder source aayega.

## 4A.5 — Tests (bina phone ke, MUST)

Fake HTTP server banao — `tests/helpers.py` mein `FakeHTTP` already hai,
usse dekho aur wahi pattern follow karo.

**Contract tests:**
- `/ui_tree` ka JSON `UIElement` mein sahi parse hota hai, `bounds` tuple banta hai
- `tap_text("Send")` → `ui_tree` call karta hai, element dhoondhta hai, uske
  `center` pe `/tap` bhejta hai (base class ka `tap_text` reuse hona chahiye)
- `screenshot()` `data["image_b64"]` deta hai
- Unknown `action` wale recorded action **skip** hote hain, crash nahi
- Malformed JSON pe `ActionResult.failure`, exception NAHI
- Phone offline (connection error) pe clear actionable error message

**Security tests (ye sabse zaroori):**
- Har request mein `Authorization: Bearer <token>` header jaata hai
- Token missing ho to device **request hi na bheje** — clear error de
- `401` response pe actionable error ("token galat hai — app mein dekh")
- `secrets.compare_digest` use hota hai (AST se check karo, text se nahi)
- **`SHELL` capability set mein NAHI hai** — explicitly assert karo
- `run_shell()` call karne pe "unsupported" mile

**Registration tests:**
- `SAARTHI_PHONE_URL` set ho to `phone` register hota hai
- Set na ho to purana behaviour bilkul same (regression test)
- `setup_defaults()` mein **koi network call nahi hoti** — startup slow na ho
  (AST se ya fake se verify karo)

## 4A.6 — Docs

- `.env.example` mein naye vars, **security warning ke saath** (token kyun
  zaroori hai, public WiFi ka khatra)
- `docs/ROADMAP.md` mein Phase 4A ko ✅ mark karo
- `docs/HANDOFF.md` mein architecture diagram add karo (phone=server, laptop=client)
  aur wajah likho

---

# PART 4B — ANDROID APP (Kotlin) — 4A ke BAAD

⚠️ **Ye alag codebase hai.** `python run_tests.py` isse test nahi kar
sakta. Isliye 4A ke tests hi contract ki guarantee hain.

Repo mein naya folder: `android/` (Python package ke andar mat daalna)

## Tech

| Cheez | Kya use karo |
|---|---|
| Language | Kotlin |
| UI | Jetpack Compose |
| Screen control | **AccessibilityService** |
| HTTP server | NanoHTTPD (single file, Apache-2.0, free) ya Ktor |
| Background | Foreground Service (notification ke saath — Android ka rule) |
| Notifications padhna | NotificationListenerService |
| Min SDK | 26 (Android 8) — purane phone bhi chalein, Pillar #3 |

## Screens (Compose)

1. **Home** — server ON/OFF toggle, phone ka IP:port bada dikhao, token
   dikhao (copy button ke saath), connection status
2. **Permissions** — AccessibilityService enable karne ka button (system
   settings pe le jaaye), NotificationListener permission
3. **Recording** — "Dikha Do" mode: start/stop, aur record hue actions ki
   live list (user dekh sake kya capture hua)

## AccessibilityService ka kaam

**Commands execute karna:**
- `tap(x, y)` → `dispatchGesture()` ke saath `GestureDescription`
- `swipe` → `dispatchGesture()` with path
- `type_text` → focused node pe `ACTION_SET_TEXT`, ya
  `AccessibilityNodeInfo.performAction(ACTION_PASTE)` clipboard ke saath
- `press_key` → `performGlobalAction(GLOBAL_ACTION_BACK / HOME / RECENTS)`
- `ui_tree` → `rootInActiveWindow` se recursive walk, `UIElement` JSON banao
- `screenshot` → `takeScreenshot()` (API 30+); purane pe MediaProjection
  ya "not supported" — imaandaari se batao

**User ke taps sunna (asli inaam):**
- `AccessibilityEvent.TYPE_VIEW_CLICKED` → `text_pe_tap` step banao
- `TYPE_VIEW_TEXT_CHANGED` → `text_likho` step
- `TYPE_WINDOW_STATE_CHANGED` + package badla → `app_kholo` step
- Scroll events → `scroll_karo`

**⚠️ Recording ke waqt bhi safety:**
- Password/OTP field (`isPassword == true`) ka text **kabhi record mat karo**
- Us step ko placeholder banao: `{"action":"text_likho","params":{"text":"{PASSWORD}"}}`
  taaki replay pe user khud bhare

## `ui_tree` build karte waqt

- Invisible / zero-size nodes skip karo
- 200 elements ka cap rakho (browser device mein bhi yahi hai) — warna JSON
  bahut bada ho jaayega aur LLM tokens jal jaayenge
- `isPassword` node ka `text` khali bhejo (`content_desc` bhi check karo)

## Testing (manual, kyunki automated nahi ho sakta)

`docs/PHASE4_TEST.md` banao — step by step manual checklist:
1. App install, permissions do
2. Server ON, IP + token note karo
3. Laptop pe `.env` mein daalo
4. `python hardware_check.py --phone` (isko extend karo taaki
   `SAARTHI_PHONE_URL` bhi check kare — ADB ke saath saath)
5. `python cli.py` → "phone pe paytm kholo"
6. Galat token daal ke dekho — clear error aana chahiye

## ⚠️ Google Play

**Publish nahi kar sakte.** Google Play autonomous accessibility agents
allow nahi karta. Personal use / sideload bilkul theek hai. README aur
ROADMAP mein ye saaf likho taaki koi baad mein galat plan na bana le.

---

# ORDER — isi kram mein karo

1. **4A.1 – 4A.5** — Python device adapter + contract + tests.
   Ye khatam hone pe `python run_tests.py` green hona chahiye.
   **Yahan rukо aur mujhe batao.** Ye akela hi ek complete increment hai.
2. 4A.6 docs
3. **Phir** 4B (Kotlin app) — alag commit, alag folder

Ek saath sab karne ki koshish mat karo. 4A bina phone ke verify ho jaata
hai; 4B ke liye asli phone chahiye.

# ACCEPTANCE CRITERIA (4A ke liye)

- [ ] `python run_tests.py` — sab pass, 386 se zyada
- [ ] Har naya test bug wapas daal ke verify kiya (batao kya verify kiya)
- [ ] `SAARTHI_PHONE_URL` set na ho to **purana behaviour bilkul same**
      (regression test hona chahiye)
- [ ] `AccessibilityDevice` mein `SHELL` capability NAHI hai — test hai
- [ ] Token missing/galat ka test hai
- [ ] `setup_defaults()` mein koi network call nahi — test hai
- [ ] `python cli.py` aur `python hardware_check.py --keys` chalte hain
- [ ] `main` pe push ho gaya

Khatam hone pe short summary do: kya badla, kaun se test add hue, kaun sa
bug re-introduce karke verify kiya, aur kya abhi bhi pending hai.
