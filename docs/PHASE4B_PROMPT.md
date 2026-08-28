# Phase 4B implementation prompt — Android App (Kotlin)

Ye READY-TO-PASTE prompt hai. Apne Kiro CLI / VS Code agent mein paste karo.

**4A ho chuka hai** (Python side ka HTTP client + contract + 35 tests).
**4B = Kotlin Android app** jo us contract ko implement karega.

`---` ke beech ka hissa copy karna hai.

---

SAARTHI ka Phase 4B implement karo — Android app (Kotlin) jo
AccessibilityService aur ek chhota HTTP server chalata hai, taaki laptop
ka Python agent phone ko WiFi pe control kar sake (ADB/USB cable ke bina).

## ⚠️ PEHLE YE SAMAJH LO — 4A PEHLE SE BAN CHUKA HAI

Python side **poora ho chuka hai**. Tumhe wahan kuch NAHI badalna hai
(sirf ek chhota kaam, neeche 4B.6 mein). Tumhara kaam ek Kotlin app
banana hai jo **already-defined HTTP contract** ko implement kare.

```
   LAPTOP (Python — ✅ BAN GAYA)              PHONE (Kotlin — ye banana hai)
   ───────────────────────────                ─────────────────────────────
   AccessibilityDevice(Device)   ──HTTP──>    HTTP server :8080
     saarthi/devices/accessibility.py             │
     474 lines, 35 tests                          ▼
                                            AccessibilityService
                                              (asli tap karta hai)
```

Python client `saarthi/devices/accessibility.py` mein hai. **Us file ko
padho** — usme har endpoint ka exact request/response likha hai. Kotlin
app ko bilkul wahi dena hai.

## PROJECT KE NON-NEGOTIABLE RULES

1. **Budget ₹0.** Koi paid library nahi. Free/open-source only.
2. **Min SDK 26 (Android 8)** — purane phone bhi chalein. Ye Pillar #3
   hai (budget hardware).
3. **Code comments HINGLISH mein.** UI text English mein. Ye poore
   project ka style hai.
4. **Python side ke tests todna nahi.** Kaam khatam hone pe
   `python run_tests.py` chala ke confirm karo — **462 pass** hone chahiye.
5. **Naya folder `android/`** — Python package ke andar kuch mat daalo.
6. `main` pe direct push.

## CURRENT STATE — VERIFIED, DOBARA KHOJ MAT KARO

- **462 tests pass**, ~26,000 lines Python, 40 tools
- Devices: `android` (ADB), `phone` (HTTP — 4A), `browser`, `desktop`
- `saarthi/devices/accessibility.py` — 474 lines, `AccessibilityDevice`
- `.env` mein: `SAARTHI_PHONE_URL`, `SAARTHI_PHONE_TOKEN`
- Diagnostic ready hai: `python hardware_check.py --phone` — wo URL,
  token, connection, `current_app`, aur `ui_tree` sab check karta hai

---

# 🚨 SECURITY — YE SABSE ZARURI HISSA HAI, PEHLE PADHO

Tu phone pe ek HTTP server chala raha hai jo **kisi bhi app pe tap kar
sakta hai** — banking app included. Galat bana to same WiFi pe (college,
cafe, hostel) **koi bhi tere phone ka control le lega** aur Paytm kholke
paise bhej sakta hai.

Ye MUST hain, optional NAHI:

1. **Bearer token auth har request pe.** `Authorization: Bearer <token>`
   - App khud random token generate kare (**32+ characters**,
     `SecureRandom` se — `Random` se nahi)
   - App ki screen pe dikhaye, copy button ke saath
   - Token galat/missing → HTTP **401**, aur **koi action na ho**
2. **Token compare CONSTANT-TIME karo.** Kotlin mein
   `MessageDigest.isEqual(a.toByteArray(), b.toByteArray())`.
   Simple `==` se timing attack possible hai (attacker ek-ek character
   guess kar sakta hai).
3. **Sirf PRIVATE network pe bind karo.** Server start karne se pehle
   check karo ki phone ka IP private range mein hai (`10.x`,
   `172.16-31.x`, `192.168.x`). Public IP pe **kabhi nahi**. Mobile data
   pe server start hi mat karo.
4. **Server DEFAULT OFF.** User app mein explicitly toggle kare. App band
   ho ya user toggle off kare to server turant band.
5. **Password/OTP field ka text KABHI mat bhejo.** `ui_tree` banate waqt:
   - `AccessibilityNodeInfo.isPassword == true` → `text` **khali** bhejo
   - `content_desc` bhi check karo (kabhi kabhi wahan leak hota hai)
   - Ye laptop side pe bhi redact hota hai, par **do jagah defense** chahiye
6. **Recording ke waqt bhi:** password field ka asli text record mat karo.
   Us step ko placeholder banao — `{"text": "{PASSWORD}"}` — taaki replay
   pe user khud bhare.
7. **`/shell` jaisa endpoint BANANA HI NAHI.** AccessibilityService se
   shell nahi chalti, aur wo endpoint banane ki koshish bhi mat karna —
   wo pura phone kholne ke barabar hai. Python side ne jaan-boojh ke
   `SHELL` capability nahi rakhi hai.
8. **Token, screen text, ya ui_tree ka data LOG mat karo** — na Logcat
   mein, na file mein. Logcat doosri apps padh sakti hain (purane
   Android pe).

---

# 4B.1 — Project setup

```
android/
├── build.gradle.kts
├── settings.gradle.kts
└── app/
    ├── build.gradle.kts
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/saarthi/agent/
        │   ├── MainActivity.kt              (Compose UI)
        │   ├── SaarthiAccessibilityService.kt
        │   ├── server/HttpServer.kt
        │   ├── server/Routes.kt
        │   ├── server/Auth.kt
        │   ├── screen/UiTreeBuilder.kt
        │   ├── screen/GestureRunner.kt
        │   ├── record/ActionRecorder.kt
        │   └── ServerService.kt             (Foreground Service)
        └── res/xml/accessibility_service_config.xml
```

| Cheez | Kya use karo |
|---|---|
| Language | Kotlin |
| UI | Jetpack Compose |
| HTTP server | **NanoHTTPD** (single file, Apache-2.0, free) |
| JSON | `org.json` (Android built-in — koi dependency nahi) |
| Background | Foreground Service (Android ka rule — notification zaroori) |
| Min SDK | 26 |

NanoHTTPD chuna kyunki wo ek chhoti si library hai, free hai, aur
Android pe bina kisi jhanjhat ke chalti hai. Ktor bhi chalega par bada
hai.

---

# 4B.2 — HTTP CONTRACT (Python client isi ka intezaar kar raha hai)

Sab requests pe header: `Authorization: Bearer <token>`
Response `Content-Type: application/json`

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/health` | — | `{"ok":true,"model":"Redmi Note 12","android":"14","screen":[1080,2400],"current_app":"com.android.launcher"}` |
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

## ⚠️ `/health` mein `current_app` ZARURI hai

Ye field optional NAHI hai. **BANKING SCREENSHOT LOCK isi pe depend karta
hai.**

Python side pe `SAARTHI_BANKING_LOCK=true` ho to banking app saamne hone
pe screenshot block hota hai. Wo `current_app` se pata karta hai. Field
na aaye to Python saaf failure deta hai (jhoothi success nahi) — par
matlab lock kaam nahi karega.

`rootInActiveWindow?.packageName` se ye milta hai — sasta hai.

## `/ui_tree` ka element JSON — EXACT ye hona chahiye

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

`bounds` = `[left, top, right, bottom]` (Python side pe tuple banega).

**Rules:**
- Invisible / zero-size nodes **skip** karo
- **200 elements ka cap** — warna JSON bahut bada ho jaayega aur LLM ke
  tokens jal jaayenge (browser device mein bhi yahi cap hai)
- `isPassword == true` node ka `text` **khali** bhejo
- `AccessibilityNodeInfo` ko `recycle()` karna yaad rakho (purane Android
  pe memory leak hota hai)

## `/recorded_actions` ka JSON

```json
{
  "action": "text_pe_tap",
  "params": {"text": "Send"},
  "target_text": "Send",
  "target_coords": [540, 1460],
  "notes": "user tapped Send button in Paytm"
}
```

`action` **sirf in 8 mein se** ho (Python ka `RECORDABLE_ACTIONS`):
`app_kholo`, `app_band_karo`, `text_pe_tap`, `coordinate_pe_tap`,
`text_likho`, `key_dabao`, `scroll_karo`, `command_chalao`

Kuch aur bhejoge to Python usse skip kar dega (crash nahi karega, par
wo step kho jaayega).

## Error response format

```json
{"ok": false, "error": "clear actionable message"}
```

HTTP status: `401` token galat, `400` bad request, `500` internal,
`503` accessibility permission nahi hai.

---

# 4B.3 — AccessibilityService

## Commands execute karna

| Endpoint | Kaise |
|---|---|
| `/tap` | `dispatchGesture()` + `GestureDescription` (single point path) |
| `/swipe` | `dispatchGesture()` with a `Path` |
| `/type` | Focused node pe `ACTION_SET_TEXT`. Focus na ho to clipboard + `ACTION_PASTE` fallback |
| `/key` | `performGlobalAction(GLOBAL_ACTION_BACK / HOME / RECENTS)` |
| `/ui_tree` | `rootInActiveWindow` se recursive walk |
| `/screenshot` | `takeScreenshot()` (API 30+). Purane pe "not supported" — **imaandaari se batao, fake mat karo** |
| `/launch_app` | `PackageManager.getLaunchIntentForPackage()` |
| `/close_app` | Best-effort — Accessibility se force-stop nahi hota. Imaandaari se batao ki ye limited hai |
| `/apps` | `PackageManager.getInstalledApplications()` |
| `/notifications` | `NotificationListenerService` se (alag permission) |

**Key mapping** — Python ye naam bhejta hai: `back`, `home`, `enter`,
`recent`, `peeche`, `wapas`. Sabko handle karo (Hinglish naam bhi).

## Accessibility config

`res/xml/accessibility_service_config.xml`:
- `android:canRetrieveWindowContent="true"`
- `android:canPerformGestures="true"`
- `accessibilityEventTypes` — `typeViewClicked|typeViewTextChanged|typeWindowStateChanged|typeViewScrolled`
- `accessibilityFeedbackType="feedbackGeneric"`

---

# 4B.4 — USER KE TAPS RECORD KARNA (ye Phase 4 ka ASLI INAAM hai)

Abhi Python ka recorder sirf **agent ke apne** actions record karta hai.
Matlab "Dikha Do Mode" sach mein "dikha do" nahi hai. AccessibilityService
ke baad **user ke manual taps** record honge.

| AccessibilityEvent | Kaunsa step banao |
|---|---|
| `TYPE_VIEW_CLICKED` | `text_pe_tap` (node ka text/content_desc lo) |
| `TYPE_VIEW_TEXT_CHANGED` | `text_likho` |
| `TYPE_WINDOW_STATE_CHANGED` + package badla | `app_kholo` |
| `TYPE_VIEW_SCROLLED` | `scroll_karo` |

**Zaroori baatein:**
- Recording **sirf** `/record/start` ke baad ho, warna hamesha sab kuch
  record hota rahega (privacy + battery dono ka nuksaan)
- Clicked node ka text na mile to `coordinate_pe_tap` fallback — par
  `target_coords` ke saath, aur `target_text` khali
- **Password field ka text KABHI record mat karo** — placeholder
  `{PASSWORD}` daalo
- Duplicate events filter karo (Android ek hi tap pe multiple event
  bhejta hai) — same action + same text 300ms ke andar aaye to skip
- Recorded actions memory mein rakho, `/recorded_actions` pe do,
  `/record/stop` pe clear na karo (Python pull karega phir)

Python side already ready hai — `phone_se_seekho` tool ye data leke
`Skill` bana deta hai. `skills/store.py` aur `runner.py` mein **kuch nahi
badalna**.

---

# 4B.5 — Compose UI (3 screens)

**1. Home**
- Server ON/OFF toggle (default OFF)
- Phone ka `IP:PORT` **bada** dikhao (user isse `.env` mein daalega)
- Token dikhao + copy button
- Connection status: "koi client nahi" / "laptop juda hua"
- Warning: "Ye sirf apne WiFi pe chalao. Public WiFi pe kabhi nahi."

**2. Permissions**
- AccessibilityService enable karne ka button (system settings pe le jaaye)
- NotificationListener permission button
- Har permission ka status (✓ / ✗) aur **kya kaam nahi karega** wo batao

**3. Recording ("Dikha Do")**
- Start/Stop button
- Live list — kaunse actions capture hue (user dekh sake)
- Clear button
- Hint: "Jo kaam sikhana hai wo dhire-dhire karo"

---

# 4B.6 — Python side ka ek chhota kaam

Ek cheez pending hai: `AccessibilityDevice` mein `close_app()` full
force-stop nahi kar sakta (Accessibility ki limitation hai). Uske
docstring mein ye **imaandaari se likho** — warna user sochega bug hai.

Baaki Python side mein **kuch nahi badalna**.

---

# 4B.7 — Testing

⚠️ **Ye alag codebase hai — `python run_tests.py` isse test nahi kar
sakta.** 4A ke 35 tests hi contract ki guarantee hain.

`docs/PHASE4B_TEST.md` banao — manual checklist:

1. App install, Accessibility permission do
2. Server ON, IP + token note karo
3. Laptop `.env` mein daalo:
   ```env
   SAARTHI_PHONE_URL=http://192.168.1.5:8080
   SAARTHI_PHONE_TOKEN=<app se copy>
   ```
4. **`python hardware_check.py --phone`** — ye already bana hua hai aur
   URL, token, connection, `current_app`, `ui_tree` sab check karta hai.
   Sab PASS aana chahiye.
5. `python cli.py` → "phone pe youtube kholo"
6. **Galat token** daal ke dekho — clear 401 error aana chahiye
7. **Security test:** doosre device se `curl http://<phone-ip>:8080/ui_tree`
   (bina token) — **401 aana chahiye, data NAHI**
8. **Banking lock test:** `.env` mein `SAARTHI_BANKING_LOCK=true`, phone pe
   Paytm kholo, phir `python cli.py` mein "screenshot lo" — **block hona
   chahiye**
9. **Recording test:** `/record/start`, phone pe khud 3-4 tap karo,
   `python cli.py` mein `phone_se_seekho` chalao — skill banni chahiye

---

# ⚠️ GOOGLE PLAY — ye README aur ROADMAP mein saaf likho

**Ye app Google Play pe publish NAHI ho sakti.** Google Play autonomous
accessibility agents allow nahi karta. Personal use / sideload bilkul
theek hai. Isko product banake bechne ka plan mat banana.

---

# ORDER — isi kram mein karo, ek saath sab nahi

1. **Project skeleton + Compose UI + permissions screen** — pehle ye chale
2. **HTTP server + auth (`/health` sirf)** — `hardware_check.py --phone`
   se verify karo ki PASS aata hai. **Yahan ruko aur batao.**
3. **Read endpoints** — `/ui_tree`, `/screenshot`, `/apps`, `/notifications`
4. **Action endpoints** — `/tap`, `/swipe`, `/type`, `/key`, `/launch_app`
5. **Recording** — `/record/*`, `/recorded_actions`
6. Docs + manual test checklist

Step 2 ke baad rukna zaroori hai — us waqt tak auth aur connectivity
verify ho jaayegi, jo sabse zyada galat hone wali cheez hai.

# ACCEPTANCE CRITERIA

- [ ] `python run_tests.py` — **462 pass** (Python side toota nahi)
- [ ] `python hardware_check.py --phone` — saare check PASS
- [ ] Bina token request → **401**, koi data nahi
- [ ] Token `MessageDigest.isEqual` se compare hota hai (`==` se nahi)
- [ ] Token `SecureRandom` se banta hai, 32+ chars
- [ ] Public/mobile-data network pe server start nahi hota
- [ ] `/health` mein `current_app` aata hai
- [ ] Password field ka text `/ui_tree` mein khali aata hai
- [ ] `/shell` jaisa koi endpoint NAHI hai
- [ ] Token/screen text Logcat mein nahi jaata
- [ ] `docs/PHASE4B_TEST.md` bana hai
- [ ] Google Play warning README aur ROADMAP mein hai
- [ ] `main` pe push ho gaya

Khatam hone pe short summary do: kya bana, kya manually test kiya, aur
kya abhi kaam nahi karta (imaandaari se — jo nahi chala wo bhi batao).
