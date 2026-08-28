# Phone pe SAARTHI kaise chalayein

Do raaste hain. **Raasta A** aaj hi 5 minute mein chal jaata hai.
**Raasta B** (app) mein cable nahi chahiye, par ek baar build karna padta hai.

---

# 🚀 RAASTA A — Aaj hi, ADB se (5 minute)

Ye **already bana hua hai** (Phase 1-3). Sirf phone pe ek setting ON karni hai.

## 1. Phone pe Developer Options kholo

1. **Settings → About phone** (ya *About device*)
2. **Build number** dhoondho
3. Uspe **7 baar tap** karo
4. "You are now a developer!" aa jaayega

> Xiaomi/Redmi pe: *Settings → About phone → MIUI version* pe 7 tap
> Samsung pe: *Settings → About phone → Software information → Build number*

## 2. USB Debugging ON karo

**Settings → System → Developer options → USB debugging** → ON

Xiaomi pe ek extra: **USB debugging (Security settings)** bhi ON karna padta hai.

## 3. Cable lagao

⚠️ **Data cable chahiye.** Charging-only cable se kaam NAHI hoga. Agar
laptop phone ko detect na kare, pehle doosra cable try karo.

Phone pe popup aayega: **"Allow USB debugging?"** → **Allow** dabao
(aur "Always allow from this computer" tick kar do).

## 4. Laptop pe check karo

```powershell
cd C:\Sarthi
python hardware_check.py --phone
```

`[PASS] Phone connected` aa jaaye to ho gaya.

`adb` na mile to ye chalao:
```powershell
winget install Google.PlatformTools
```

## 5. Chala ke dekho

```powershell
python cli.py
```
Phir bol: `phone pe youtube kholo`

## 6. (Optional) Cable hatao — WiFi pe chalao

Ek baar cable se connect karke:
```powershell
adb tcpip 5555
adb shell ip route            # phone ka IP dekho
adb connect <phone-ka-IP>:5555
```
Ab cable nikaal de. Agent mein `phone_wifi_se_jodo` tool bhi hai.

⚠️ Reboot ke baad ye dobara karna padega.

---

# 📱 RAASTA B — Android app (cable ki zarurat nahi)

Ye Phase 4B hai. Ek baar app build karke phone pe daalni hai.

## Kya chahiye

| Cheez | Kyun | Size |
|---|---|---|
| **JDK 17** | Gradle chalane ke liye | ~180 MB |
| **Android SDK** | App compile karne ke liye | ~600 MB (sirf cmdline tools) |

**Android Studio ki zarurat NAHI hai** — repo mein Gradle wrapper hai.
Par agar Android Studio already installed hai to **wahi sabse aasan hai**,
neeche "Option B2" dekh.

---

## Option B1 — Bina Android Studio (command line)

### 1. JDK 17 install

```powershell
winget install EclipseAdoptium.Temurin.17.JDK
```

Naya PowerShell kholo, phir check:
```powershell
java -version
```
`17.x.x` dikhna chahiye.

### 2. Android SDK (command line tools)

```powershell
winget install Google.AndroidStudio
```

Ya sirf cmdline tools (chhota):
1. https://developer.android.com/studio#command-line-tools-only se ZIP download
2. `C:\Android\cmdline-tools\latest\` mein extract karo
3. PowerShell mein:

```powershell
$env:ANDROID_HOME = "C:\Android"
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Android", "User")
cd C:\Android\cmdline-tools\latest\bin
.\sdkmanager.bat "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

Licenses accept karo (`y` dabao).

### 3. App build karo

```powershell
cd C:\Sarthi\android
.\gradlew.bat assembleDebug
```

Pehli baar mein 5-10 minute lagega (Gradle + dependencies download honge).

APK yahan banegi:
```
C:\Sarthi\android\app\build\outputs\apk\debug\app-debug.apk
```

### 4. Phone pe install

**Cable se (aasan):**
```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

**Ya bina cable:** APK ko WhatsApp/Telegram se apne aap ko bhej de, ya
Google Drive pe daal ke phone se download kar. Phone pe "Unknown sources"
allow karna padega.

---

## Option B2 — Android Studio ke saath (sabse aasan)

1. Android Studio kholo
2. **File → Open** → `C:\Sarthi\android` folder chuno
3. Gradle sync khud ho jaayega (pehli baar 5-10 min)
4. Phone cable se lagao (USB debugging ON — upar Raasta A ka step 1-3)
5. Upar device dropdown mein apna phone chuno
6. **Run ▶** dabao

App phone pe install ho ke khul jaayegi.

---

# ⚙️ App setup (build ke baad)

## 1. Permissions do

App khulegi, "Permissions" screen pe jao:

- **Accessibility** → button dabao → system settings khulega →
  **SAARTHI Phone** dhoondho → **ON** karo
  > Android warning dikhayega ("full control of your device") — ye normal
  > hai, AccessibilityService ko yahi permission chahiye tap karne ke liye
- **Notifications** → allow karo (server ON/OFF dikhane ke liye)
- **Notification access** (optional) → sirf `notifications_padho` ke liye

## 2. Server ON karo

Home screen pe **toggle ON** karo. Ye dikhega:

```
http://192.168.1.5:8080
Token: xR9mK2pL...
```

⚠️ **Dono note kar lo.**

## 3. Laptop pe .env mein daalo

```powershell
cd C:\Sarthi
notepad .env
```

```env
SAARTHI_PHONE_URL=http://192.168.1.5:8080
SAARTHI_PHONE_TOKEN=<app se copy kiya hua token>
```

## 4. Verify karo

```powershell
python hardware_check.py --phone
```

Ye sab PASS aana chahiye:
```
[PASS] Phone URL set hai
[PASS] Phone token — mil gaya (32 chars)
[PASS] Phone se connection — model=..., android=...
[PASS] current_app support
[PASS] Screen padh sakte hain (ui_tree) — 47 elements
```

## 5. Chalao

```powershell
python cli.py
```
Bol: `phone pe youtube kholo`

---

# 🔒 Security — ye zaroor padho

App tere phone pe ek HTTP server chalata hai jo **kisi bhi app pe tap
kar sakta hai** — banking app bhi.

**Jo protection lagi hui hai:**

| Cheez | Kaise |
|---|---|
| Token auth | Har request pe. Bina token → 401, koi action nahi |
| Constant-time compare | `MessageDigest.isEqual` — timing attack se bachao |
| Sirf private WiFi | Public IP / mobile data pe server **start hi nahi hota** |
| Default OFF | Tu khud toggle karta hai. App band = server band |
| Password field | Uska text kabhi nahi bhejta |
| OTP/PIN/CVV | `/type` pe blocked — phone side pe bhi, laptop side pe bhi |
| `/shell` endpoint | **Banaya hi nahi gaya** |
| Logging | Koi `Log.*` call nahi — token/screen text leak nahi hota |

**Phir bhi ye rules follow kar:**

1. **Public WiFi pe server ON mat karna** — college, cafe, hostel, airport.
   Apne ghar ke WiFi pe hi.
2. **Kaam khatam ho to server OFF kar do.** Chalu chhodne ki zarurat nahi.
3. **Token kisi ko mat bhejna.** Screenshot mein bhi na aaye.
4. Token leak lage to app mein data clear karke naya generate karwa lo.

**Extra lock chahiye to** `.env` mein:
```env
SAARTHI_BANKING_LOCK=true
```
Isse agent Paytm/PhonePe/GPay/bank apps **kholega hi nahi**, aur banking
screen ka screenshot bhi nahi lega.

⚠️ Par isse `"paytm kholo"` aur `"bijli ka bill bhar do"` bhi band ho
jaayenge. Faisla tera.

---

# ⚠️ Google Play

**Ye app Google Play pe publish NAHI ho sakti.** Google autonomous
accessibility agents allow nahi karta. Personal use / sideload theek hai.
Isko bech ne ka plan mat banana.

---

# Problem aaye to

| Problem | Kya karo |
|---|---|
| `adb` phone detect nahi karta | Doosra cable (data cable chahiye), phone pe "Allow" dabao, Xiaomi pe "USB debugging (Security settings)" bhi ON |
| App mein "Private WiFi nahi mila" | Mobile data pe ho — WiFi se connect karo |
| `hardware_check --phone` connection fail | Phone aur laptop same WiFi pe? IP badal gaya? (WiFi reconnect pe badalta hai) App mein server ON hai? |
| 401 error | Token galat — app se dobara copy karo |
| `ui_tree` 0 elements deta hai | Accessibility permission nahi di |
| `gradlew.bat` "JAVA_HOME not set" | JDK 17 install karo, naya PowerShell kholo |
| Build "SDK location not found" | `ANDROID_HOME` set karo, ya `android/local.properties` mein `sdk.dir=C:\\Android` likho |

Kuch aur aaye to poora error message bhej dena.

---

# Kaunsa raasta chuno?

**Pehle Raasta A karo.** Wajah:

- 5 minute ka kaam, aur **already bana hua hai**
- Usse pata chalega ki phone automation tere phone pe sach mein chalta
  hai ya nahi
- Jo bug milenge wo asli honge, aur app banane se pehle theek ho jaayenge
- App (Raasta B) ka code **abhi kisi asli phone pe chala nahi hai** — wo
  pehli baar tere phone pe hi chalega, aur pehli baar mein kuch bug
  nikalna normal hai

Voice ke saath yahi hua tha: code "ban gaya" tha, par asli machine pe
chalane se **8 asli bug** nikle jo sandbox mein kabhi na milte.
