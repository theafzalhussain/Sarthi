# Phase 3 implementation prompt

Ye file ek READY-TO-PASTE prompt hai. Isko apne Kiro CLI / VS Code agent
mein paste kar do, wo Phase 3 implement kar dega.

Neeche wali poori cheez copy karni hai (`---` ke beech ka hissa).

---

SAARTHI repo mein Phase 3 (phone polish) implement karo. Teen kaam hain:
screenshot caching, multi-phone support, aur retry logic.

## PEHLE YE PADHO — project ke non-negotiable rules

1. **Budget ₹0.** Koi paid dependency nahi, koi naya pip package nahi.
   Sirf Python stdlib + jo pehle se `requirements.txt` mein hai.
2. **Python 3.9+ compatible** rehna hai (user Windows pe 3.14 chala raha
   hai, par purane laptop support karna hai — Pillar #3).
3. **Code comments HINGLISH mein.** Ye poore codebase ka style hai. UI
   text English mein. Ye mat badlo.
4. **Safety layer ko CHHUNA NAHI.** `saarthi/tools/safety.py` aur uske
   hard blocks jaise hain waise rehne do. Feature add karo, brake mat
   hatao.
5. **Tests stdlib `unittest` se.** pytest nahi (zero new deps).
   `python run_tests.py` se chalte hain.
6. **HAR naya test bug WAPAS daal ke VERIFY karo.** Test likhne ke baad
   fix ko ulta karo, confirm karo ki test FAIL hota hai, phir fix wapas
   lagao. Jo test bug ke saath bhi pass ho jaaye wo bekaar hai — is repo
   mein aisa do baar ho chuka hai.
7. Kaam khatam hone pe `python run_tests.py` chalao, test count
   `README.md`, `docs/HANDOFF.md`, `docs/UPDATE.md`, `docs/HARDWARE_TEST.md`
   mein update karo, aur `main` branch pe direct push karo.

## Current state — ye VERIFIED hai, dobara khoj mat karo

- 362 tests pass (`python run_tests.py`)
- 9 LLM providers, 39 tools, 3 devices (android/browser/desktop)
- Agent loop: `saarthi/agent.py` → `Agent.run_turn()`, line ~169.
  Plan-Act-Observe loop line ~220: `while steps < self.settings.max_steps:`
- Screenshot inject hone ki jagah: `saarthi/agent.py` line ~293:
  ```python
  image_b64 = result.data.get("image_b64")
  if image_b64:
      self.messages.append(Message.tool_result(content or "screenshot liya", call.id))
      self.messages.append(Message.user("Ye screen ka screenshot hai — ...", image_b64=image_b64))
  ```
- `Message` class `saarthi/brain/types.py` mein: `Message.user(content, image_b64=None)`,
  `Message.tool_result(content, tool_call_id)`, property `has_image`.
- ADB wrapper: `saarthi/devices/android.py`
  - `AndroidDevice.__init__(..., serial: str | None = None)` line ~121
  - `self.serial` line ~129
  - `_build_args()` line ~135 — **`["-s", serial]` already inject karta hai**
  - `_adb_raw(args, timeout=30.0)` line ~142 — ye ek hi jagah hai jahan
    subprocess chalta hai. `_adb()` aur `_shell()` isi ko call karte hain.
  - `is_available()` line ~205 — `adb devices` parse karta hai, serial match karta hai
- Device registration: `saarthi/devices/manager.py` → `DeviceManager.setup_defaults()`.
  Abhi sirf ye teen line hain:
  ```python
  self.register(DesktopDevice(name="desktop"))
  self.register(AndroidDevice(name="android", adb_path=self.settings.adb_path))
  self.register(BrowserDevice(name="browser"))
  ```
  **Serial kahin pass nahi hota** — yahi 3b ka kaam hai.
- Config: `saarthi/config.py`. Helpers already hain: `_env_bool`, `_env_int`,
  `_env_choice(key, allowed, default)`. `adb_path` line ~350,
  `default_device` line ~351, `max_steps` line ~327.
  Naye settings inhi patterns se add karo, aur `.env.example` mein
  document karo (ye repo `.env.example` ko seriously leta hai).

---

## 3a. SCREENSHOT CACHING (sabse zyada faayda, pehle ye karo)

### Problem

`Agent.run_turn()` ke loop mein har screenshot ek naya
`Message.user(image_b64=...)` append karta hai aur **kabhi hataya nahi
jaata**. Ek turn mein 6 screenshot liye to chhathi LLM call mein saare 6
images jaate hain. Tokens monotonically badhte hain aur free tier ki rate
limit lag jaati hai.

Abhi iska sirf ek ilaaj hai — prompt mein likha hai "screenshot_lo zyada
tokens khaata hai, pehle screen_padho try kar". Wo guzarish hai, guarantee
nahi.

### Kya karna hai

Do cheezein, dono `saarthi/agent.py` mein:

**1. Purane screenshots evict karo.** Sirf latest N images message list
mein rakho (default 2). Purane image message ko hata ke uski jagah plain
text placeholder daal do, jaise:
`"(purana screenshot hata diya — tokens bachane ke liye)"`

**2. Same screen dobara mat bhejo (dedupe).** `hashlib.sha256` se
`image_b64` ka hash nikaalo. Agar pichhle screenshot se bilkul same hai,
to naya image message append hi mat karo — sirf tool_result mein bata do
`"screen mein koi badlav nahi (same screenshot)"`. Agent aksar bina kuch
badle dobara screenshot le leta hai; ye us waste ko poora khatam karta hai.

### ⚠️ YE GALTI MAT KARNA — API contract todega

`Message.tool_result(content, call.id)` messages ko **kabhi mat hatao ya
badlo.** Har `tool_call` ka ek matching `tool_result` hona ZARURI hai,
warna LLM API error dega ("tool_call_id without response").

Evict sirf alag wale `Message.user(..., image_b64=...)` messages ko karna
hai. Ye do alag messages hain — dhyan se dekh lo line ~293 pe.

### Config (`saarthi/config.py` + `.env.example`)

- `SAARTHI_MAX_SCREENSHOTS` — default `2`. `0` = image bhejna hi band
  (sirf text), useful jab provider vision support na kare.
- `SAARTHI_SCREENSHOT_DEDUPE` — default `true`.

### Tests (`tests/` mein, naya file ya existing mein add)

- Teen screenshot append karne pe message list mein **sirf 2** image
  messages bache
- Har `tool_call` ka `tool_result` still maujood hai (contract test —
  ye sabse zaroori hai)
- Same `image_b64` dobara dene pe naya image message NAHI banta
- Alag `image_b64` pe banta hai
- `SAARTHI_MAX_SCREENSHOTS=0` pe koi image message nahi
- Evicted message ki jagah placeholder text hai (chup-chaap gayab nahi)

---

## 3b. MULTI-PHONE SUPPORT

### Problem

`_build_args()` mein `["-s", serial]` ka code **already likha hai**, par
`setup_defaults()` kabhi serial pass nahi karta. Do phone laga do to `adb`
khud confuse hota hai ya galat phone pe kaam kar deta hai.

### Kya karna hai

1. `saarthi/devices/android.py` mein ek **sync** helper banao:
   `list_adb_serials(adb_path: str, timeout: float = 3.0) -> list[str]`
   - `subprocess.run([adb_path, "devices"], timeout=...)` se serials nikaalo
   - Sirf wo lo jinki state `device` hai (`offline` / `unauthorized` chhod do)
   - adb na mile ya timeout ho to **khali list**, crash NAHI
   - Sync kyun: `setup_defaults()` sync hai, `_adb_raw` async hai

2. `DeviceManager.setup_defaults()` mein serials enumerate karke register karo:
   - `android-<serial>` naam se har phone
   - **`android` naam BHI kaam karta rahe** (pehla/default phone). Ye
     backward compatibility ke liye ZARURI hai — `saarthi/lang/lexicon.py`
     ka `detect_target_device` "android" return karta hai, prompts mein
     "android" likha hai, aur existing tests "android" dhoondhte hain.
   - Ek bhi phone na mile to abhi jaisa hi ek `android` register karo
     (behaviour badalna nahi chahiye)

3. `SAARTHI_ANDROID_SERIAL` env — ek phone pin karne ke liye. Set ho to
   sirf wahi use ho.

4. Startup pe do se zyada phone mile to user ko batao (`saarthi/ui.py` ka
   existing pattern use karo) — kaunse serial mile aur kaise chunna hai.

### ⚠️ Dhyan

- Startup **slow nahi hona chahiye.** `adb devices` pe 3 second ka timeout
  lagao. adb installed na ho (bahut common) to turant khali list.
- `DeviceManager.get(name)` name-then-kind lookup karta hai — verify karo
  ki `android-ABC123` aur `android` dono resolve hote hain.

### Tests

- `list_adb_serials()` fake `adb devices` output parse karta hai (subprocess
  mock/fake karo, asli adb par depend NAHI karna — sandbox mein adb nahi hoga)
- `offline` / `unauthorized` devices skip hote hain
- adb missing pe khali list, koi exception nahi
- Do serial pe `android`, `android-<s1>`, `android-<s2>` teeno register
- Zero serial pe purana behaviour (ek `android`)
- `SAARTHI_ANDROID_SERIAL` set ho to wahi chuna jaata hai
- `_build_args()` serial set hone pe `-s <serial>` daalta hai, warna nahi

---

## 3c. RETRY LOGIC

### Problem

`_adb_raw()` ek baar chalti hai. Timeout hai (30s, screenshot pe 45s) par
koi retry nahi. Phone thoda slow ho ya screen load na hui ho to poora task
marr jaata hai.

### 🚨 YE SABSE ZARURI HISSA HAI — BLANKET RETRY MAT LAGANA

**Har ADB command retry karna SAFE NAHI HAI.**

`input tap` retry hua to **do baar tap** hoga. Payment screen pe wo do
baar paisa bhej sakta hai. `input text` retry hua to text do baar type
hoga. Ye asli nuksaan hai, theoretical nahi.

Isliye retry ke liye **WHITELIST** banao — sirf idempotent / read-only
commands. Bilkul waise jaise `saarthi/skills/recorder.py` mein
`RECORDABLE_ACTIONS` whitelist hai.

**Retry karo (padhne wale, safe):**
- `devices`
- `shell getprop ...`
- `shell wm size`
- `shell dumpsys ...`
- `exec-out screencap -p`
- `shell uiautomator dump ...` aur uska `cat`
- `shell pm list packages ...`

**Retry KABHI NAHI (state badalte hain):**
- `shell input tap ...`
- `shell input swipe ...`
- `shell input text ...`
- `shell input keyevent ...`
- `shell am start ...` / `am force-stop ...`
- `shell monkey ...`
- `shell rm ...`
- koi bhi cheez jo `run_shell()` se user/LLM ne bheji ho — wo arbitrary
  hai, uska idempotent hona guarantee nahi

Default **deny** rakho: jo whitelist mein nahi hai, retry nahi hoga.
Whitelist match karne ka tareeka aisa likho ki `_build_args` ke `-s serial`
prefix se farak na pade.

### Kya karna hai

- `_adb_raw()` mein retry + backoff (jaise 0.5s, phir 1.0s)
- Retry sirf tab jab (a) command whitelisted ho, AUR (b) failure
  retry-worthy ho — timeout ya non-zero exit. Jo error permanent hai
  (`device not found`, `unauthorized`) usme retry bekaar hai, usse turant
  fail karo.
- `SAARTHI_ADB_RETRIES` env, default `2`, `0` = retry band
- Retry hone pe `log.warning` — chup-chaap retry karna debugging narak
  bana deta hai

### Tests

- Whitelisted command timeout pe retry hoti hai aur `SAARTHI_ADB_RETRIES`
  baar hoti hai
- **`input tap` retry NAHI hoti — ye sabse zaroori test hai.** Explicitly
  assert karo ki attempt count exactly 1 hai
- `input text` / `input swipe` / `input keyevent` bhi retry nahi hote
- Permanent error (`device not found`) pe retry nahi
- Retry ke baad success ho to `ActionResult.ok` True
- `SAARTHI_ADB_RETRIES=0` pe ek hi attempt
- Serial ke saath bhi whitelist sahi match karti hai (`-s ABC123 shell input tap`
  retry nahi honi chahiye)
- Subprocess fake/mock karo — asli adb par depend nahi

---

## 4. Docs update karo

1. **`docs/ROADMAP.md` STALE HAI — theek karo.**
   Wo kehta hai "Phase 3 = Browser device banao", jabki
   `saarthi/devices/browser.py` (771 lines, Playwright) **already ban chuka
   hai** — `tap_text` override, `ui_tree`, `screenshot`, `fill_field`,
   tab-hijack protection sab hai. Browser wale hisse ko ✅ mark karo aur
   Phase 3 ko in teen kaamon ke baad complete mark karo.

2. `.env.example` mein saare naye env vars document karo — is repo ka
   style hai ki har setting ke saath samjhaya jaata hai ki **kyun** hai.

3. `docs/HANDOFF.md` mein status update karo (tools/tests/features count).

4. Test count sab jagah update karo.

## 5. Acceptance criteria

- [ ] `python run_tests.py` — sab pass, 361 se zyada
- [ ] Har naya test bug wapas daal ke verify kiya (ye batao ki kya verify kiya)
- [ ] `python cli.py` chalta hai, koi import error nahi
- [ ] `python hardware_check.py --keys` chalta hai
- [ ] adb installed na ho to bhi kuch nahi tootta (sandbox/CI case)
- [ ] `input tap` retry na hone ka explicit test hai
- [ ] `tool_call` ↔ `tool_result` pairing ka test hai
- [ ] `main` pe push ho gaya

Kaam khatam hone pe short summary do: kya badla, kaun se test add hue,
aur kaun sa bug re-introduce karke verify kiya.
