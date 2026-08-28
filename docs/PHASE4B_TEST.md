# Phase 4B — Android App Manual Test Checklist

Ye automated nahi ho sakta (asli phone chahiye). Har release/sideload se pehle ye verify karo.

---

## Prerequisites

- Android phone (min API 26 / Android 8.0)
- Phone aur laptop SAME private WiFi pe
- APK sideload: `adb install app-debug.apk`

---

## 1. Installation & First Launch

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 1.1 | APK install karo | Install success, launcher mein "SAARTHI Phone" blue S icon | [ ] |
| 1.2 | App kholo | Home screen — server OFF, START button | [ ] |
| 1.3 | 3 tabs visible: Home, Permissions, Recording | TabRow correct | [ ] |

---

## 2. Permissions

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 2.1 | Permissions tab — initial state | Accessibility=OFF, Notification=OFF | [ ] |
| 2.2 | Accessibility "Open" dabao | System Accessibility Settings khule | [ ] |
| 2.3 | SAARTHI ON karo | Wapas app: "ON — connected" green text | [ ] |
| 2.4 | Notification "Open" dabao | Notification Listener Settings khule | [ ] |
| 2.5 | SAARTHI ON karo | Wapas app: "ON — connected" green text | [ ] |
| 2.6 | Dono ON ke baad | Dono "Done" (disabled) dikhe | [ ] |

---

## 3. Server Start/Stop

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 3.1 | START SERVER dabao | Card green, "SERVER ON", IP:8080 dikhe | [ ] |
| 3.2 | Token card visible | 32-char alphanumeric token | [ ] |
| 3.3 | COPY TOKEN dabao | Toast "Token copied!", clipboard mein token | [ ] |
| 3.4 | .env hint card | Correct format SAARTHI_PHONE_URL + TOKEN | [ ] |
| 3.5 | Notification tray | "SAARTHI Server — ON — http://..." ongoing | [ ] |
| 3.6 | STOP SERVER dabao | Card grey, "SERVER OFF", notification gone | [ ] |
| 3.7 | App kill → reopen → START | SAME token (persistence check) | [ ] |

---

## 4. Security Tests (SABSE ZARURI)

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 4.1 | `curl http://<ip>:8080/health` (bina token) | 401 `{"ok":false,"error":"unauthorized"}` | [ ] |
| 4.2 | `curl -H "Authorization: Bearer WRONG" http://<ip>:8080/health` | 401 unauthorized | [ ] |
| 4.3 | `curl -H "Authorization: Bearer <sahi-token>" http://<ip>:8080/health` | 200 `{"ok":true,...}` | [ ] |
| 4.4 | Mobile data pe (WiFi off) server start try karo | Start FAIL — "Private WiFi nahi mila" | [ ] |
| 4.5 | `/type` with `{"text":"123456"}` | 403 — "6-digit OTP" blocked | [ ] |
| 4.6 | `/type` with `{"text":"my otp is 4521"}` | 403 — OTP pattern blocked | [ ] |
| 4.7 | `/type` with `{"text":"upi pin 1234"}` | 403 — PIN blocked | [ ] |
| 4.8 | Password field focus → `/ui_tree` | `text` field EMPTY for password node | [ ] |
| 4.9 | Doosre device se bina token request | 401, koi data nahi | [ ] |
| 4.10 | Logcat mein token search karo | Token NAHI milna chahiye | [ ] |

---

## 5. HTTP Endpoints

`.env` mein set karo:
```
SAARTHI_PHONE_URL=http://<phone-ip>:8080
SAARTHI_PHONE_TOKEN=<token>
```

| # | Endpoint | Test | Expected | Pass? |
|---|----------|------|----------|-------|
| 5.1 | GET /health | curl | `{"ok":true,"model":"...","android":"...","screen":[w,h],"current_app":"..."}` | [ ] |
| 5.2 | POST /tap | `{"x":540,"y":1200}` | `{"ok":true}`, phone pe tap dikhe | [ ] |
| 5.3 | POST /swipe | `{"x1":540,"y1":1500,"x2":540,"y2":500,"duration_ms":300}` | `{"ok":true}`, swipe ho | [ ] |
| 5.4 | POST /type | Text field focus + `{"text":"hello"}` | Text type ho | [ ] |
| 5.5 | POST /key | `{"key":"back"}` | Back press | [ ] |
| 5.6 | POST /key | `{"key":"peeche"}` (Hinglish) | Back press | [ ] |
| 5.7 | POST /key | `{"key":"home"}` | Home screen | [ ] |
| 5.8 | POST /key | `{"key":"wapas"}` | Back press | [ ] |
| 5.9 | GET /ui_tree | — | JSON `{"elements":[...]}`, max 200 | [ ] |
| 5.10 | GET /screenshot | — | `{"ok":true,"image_b64":"..."}` (API 30+) | [ ] |
| 5.11 | POST /launch_app | `{"app":"com.android.chrome"}` | Chrome khule | [ ] |
| 5.12 | POST /launch_app | `{"app":"chrome"}` (fuzzy) | Chrome khule | [ ] |
| 5.13 | POST /close_app | `{"app":"com.android.chrome"}` | Home pe jaaye | [ ] |
| 5.14 | GET /apps | — | `{"apps":["com.x",...]}` sorted list | [ ] |
| 5.15 | GET /notifications | — | `{"notifications":[...]}` | [ ] |

---

## 6. Recording ("Dikha Do")

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 6.1 | Recording tab → START | "RECORDING..." status | [ ] |
| 6.2 | Koi app kholo | "app_kholo" action list mein | [ ] |
| 6.3 | Button tap karo | "text_pe_tap" with button text | [ ] |
| 6.4 | Text field mein likho | "text_likho" with text | [ ] |
| 6.5 | Password field mein likho | "text_likho" text="{PASSWORD}" | [ ] |
| 6.6 | Scroll karo | "scroll_karo" action | [ ] |
| 6.7 | Same button 2 baar fast tap (< 300ms) | Sirf 1 entry (dedup) | [ ] |
| 6.8 | STOP dabao | Recording ruke | [ ] |
| 6.9 | GET /recorded_actions | Same actions JSON mein (clear nahi hua) | [ ] |
| 6.10 | POST /record/stop (again) | Actions still available (stop clears nahi) | [ ] |
| 6.11 | Clear button dabao | List empty | [ ] |

---

## 7. Python Integration (Full Flow)

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 7.1 | `.env` set karo | SAARTHI_PHONE_URL + TOKEN | [ ] |
| 7.2 | `python hardware_check.py --phone` | All checks PASS — connection, current_app, ui_tree | [ ] |
| 7.3 | `python cli.py` → "phone pe chrome kholo" | Chrome phone pe khule | [ ] |
| 7.4 | Screenshot + tap based task | Agent screenshot le, ui_tree padhe, tap kare | [ ] |
| 7.5 | `python run_tests.py` | 468 tests PASS (Python side toota nahi) | [ ] |

---

## 8. Banking Lock Test

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 8.1 | `.env` mein `SAARTHI_BANKING_LOCK=true` | — | [ ] |
| 8.2 | Phone pe Paytm/banking app kholo | /health mein `current_app` = banking package | [ ] |
| 8.3 | `python cli.py` → "screenshot lo" | BLOCKED — banking lock active | [ ] |

---

## 9. Edge Cases

| # | Step | Expected | Pass? |
|---|------|----------|-------|
| 9.1 | WiFi disconnect while server ON | Graceful — requests fail, no crash | [ ] |
| 9.2 | Accessibility OFF while server ON | Endpoints → 503 "service chalu nahi" | [ ] |
| 9.3 | Screen lock → command bhejo | Commands still work (a11y background mein) | [ ] |
| 9.4 | API < 30 pe /screenshot | Clear error (not fake success) | [ ] |
| 9.5 | 200+ elements wali screen → /ui_tree | Max 200, no crash | [ ] |

---

## Notes

- **Google Play pe publish NAHI ho sakta** — autonomous a11y agents policy violation.
  Sirf personal use / sideload.
- Screenshot sirf API 30+ (Android 11+) pe kaam karta hai.
- `/close_app` sirf home pe le jaata hai — Accessibility se force-stop nahi hota (limitation).
- Token restart ke baad same rehta hai (SharedPreferences).
- `/shell` jaisa endpoint NAHI hai, KABHI nahi banega.
