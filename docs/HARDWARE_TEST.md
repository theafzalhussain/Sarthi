# Hardware Test — mic, speaker, phone

> **Ye kaam SIRF TU KAR SAKTA HAI.** Isliye ye guide bani hai.

---

## Ye kyun zaroori hai (imaandaari se)

SAARTHI ka Phase 1 aur Phase 2 ka code **sandbox mein bana tha** — jahan
**mic nahi tha, speaker nahi tha, phone nahi tha.**

Iska matlab:

| Cheez | Status |
|---|---|
| Logic, parsing, safety, tools, browser | ✅ **357 automated tests** se verified |
| Whisper ka int16→float32 conversion | ⚠️ Code sahi hai, par asli mic pe kabhi chala nahi |
| Porcupine ka 512-sample frame buffer | ⚠️ Same |
| TTS ki awaaz sach mein aati hai | ⚠️ Same |
| ADB se asli phone control | ⚠️ Same |

**Jo bugs asli hardware pe milenge, wo ASLI honge.** Aur unko fix karna
naya feature banane se **zyada valuable** hai.

Is project mein **8 asli bugs** mile — saare testing se. Ye pattern hai:
test karo, bug milega, fix karo, phir aage badho.

---

## Sabse aasaan tareeka (2 minute)

```bash
python hardware_check.py
```

Bas. Ye script:
- Sab check karti hai (Python, install, keys, mic, speaker, phone, browser)
- **Asli recording** leti hai aur transcribe karke dikhati hai
- **Asli awaaz** bajati hai aur puchti hai sunai di ya nahi
- Ek report banati hai jo tu **copy-paste karke dev/AI ko de sakta hai**

### Ye script SAFE hai

- ❌ Kuch **install nahi** karti
- ❌ Koi file **delete nahi** karti
- ❌ Phone pe koi **tap nahi** karti (sirf padhti hai)
- ❌ Teri **API keys print nahi** karti (sirf "mili / nahi mili")

### Sirf ek cheez test karni ho

```bash
python hardware_check.py --mic        # sirf microphone
python hardware_check.py --mic-scan  # HAR mic try karo, best batao
python hardware_check.py --stt-tune  # galat suna? best Whisper setting dhoondho
python hardware_check.py --mic-live  # voice "kuch sunai nahi diya" bole to
python hardware_check.py --mic-stream # mic se sirf 0 aa raha ho to
python hardware_check.py --speaker   # sirf awaaz
python hardware_check.py --phone     # sirf phone (ADB)
python hardware_check.py --browser   # sirf browser
python hardware_check.py --keys      # sirf keys + install

python hardware_check.py --save      # report file mein bhi save karo
```

---

## Report kaise bhejni hai

1. `python hardware_check.py` chala
2. **Poori output** copy kar (ya `--save` se `hardware_report.txt` bana)
3. Dev/AI ko bhej de

Report mein `[PASS]`, `[FAIL]`, `[SKIP]` clearly likha hota hai — usse
exact bug pakad mein aa jaata hai.

> **`[SKIP]` `[FAIL]` se ALAG hai.** Skip matlab "check nahi kar paye"
> (jaise optional package nahi hai). Fail matlab "sach mein toota hai".
> Jo verify nahi hua usko pass nahi bolte — yahi imaandaari hai.

---

## Step-by-step checklist (agar khud karna ho)

### 1. Base setup

```bash
python run_tests.py
```

**218 tests pass hone chahiye.** Ye hardware ke bina chalte hain.
Yahan kuch fail ho to **pehle wahi theek kar** — hardware ki galti nahi hai.

```bash
python cli.py
```
- [ ] Banner dikha
- [ ] Brain table mein kam se kam 1 provider `●` (green) hai
- [ ] `/status` chalta hai
- [ ] `hello` likho → jawab **English** mein aaye
- [ ] `bhai kaise ho` likho → jawab **Hinglish** mein aaye

> Ye aakhri do point **language mirroring** test karte hain — interface
> English hai par baat teri bhasha mein honi chahiye.

---

### 2. Microphone

```bash
pip install faster-whisper sounddevice numpy
```

**Linux pe system library bhi chahiye:**
```bash
sudo apt install libportaudio2      # Ubuntu/Debian
sudo dnf install portaudio          # Fedora
```
**Windows:** PortAudio pip ke saath aa jaata hai.
**macOS:** `brew install portaudio`

```bash
python hardware_check.py --mic
```

- [ ] Mic device list mein dikha
- [ ] Recording ke baad `peak` **500 se zyada** hai
- [ ] Whisper ne kuch transcribe kiya

#### Mic ke aam problems

| Problem | Wajah | Fix |
|---|---|---|
| `peak` 500 se kam | Mic mute hai ya galat device | System settings mein mic unmute kar, default device sahi chun |
| `No module named 'sounddevice'` | Package nahi hai | `pip install sounddevice` |
| `PortAudio library not found` | System library nahi hai | `sudo apt install libportaudio2` |
| Windows pe permission error | Mic permission nahi hai | Settings > Privacy > Microphone > allow |
| **Sirf shor sunai deta hai** | int16→float32 conversion ka bug | ⚠️ **Ye report karo** — `voice/stt.py` mein `/32768` hona chahiye |
| **`peak` 300-1500 (bahut dheema)** | Galat mic device select hai | `python hardware_check.py --mic-scan` chala — neeche padh |

#### 🗣️ Awaaz sahi aa rahi hai par GALAT suna? — `--stt-tune`

Asli case: user ne `"paytm kholo"` bola. Audio **perfect** thi
(`peak=24087`, `rms=2940`). Par Whisper ne suna:

```
Transcribe — suna: 'Kya kya ouri website, proper da yaar uca.'
```

Matlab problem **audio ki nahi, model/setting ki hai.** Do shak hote hain:
model chhota hai, ya `WHISPER_LANGUAGE` galat hai.

**Guess mat kar — measure kar:**

```bash
python hardware_check.py --stt-tune
```

Ye **ek recording** leta hai aur usi pe **saari settings** try karta hai:

```
   Expected: "paytm kholo"

      language=en    score  20%   'Kya kya ouri website, proper da yaar uca.'
      language=hi    score  85%   'paytm kholo'
      language=auto  score  85%   'paytm kholo'

   Best setting mil gayi — language=hi (85%)
```

Phir jo suggest kare wo `.env` mein daal.

**Aur ye bhi check kar:** `base` model **Hinglish pe kamzor hai.**
`--keys` chala ke dekh kitni RAM hai — 8GB+ ho to `small` use kar:

```env
WHISPER_MODEL=small
```

#### 🎤 Galat mic select ho gaya? — `--mic-scan`

Ye ASLI problem hai jo mili: Windows pe 21 input devices the, aur system
default **"Microsoft Sound Mapper - Input"** tha — ek legacy MME wrapper.
Usse recording *aati* thi par `peak` sirf **303** (32767 mein se) =
practically silence. Whisper ne khali string di.

```bash
python hardware_check.py --mic-scan
```

Ye **har mic se 1 second record** karke batata hai kaunsa sach mein
sunta hai:

```
   [0] Microsoft Sound Mapper - Input      [#...................]   303  bahut dheema
   [5] Microphone Array (Realtek(R) Audio) [########............]  4200  accha
   [9] Microphone Array (Realtek(R) Audio) [######..............]  2800  theek
```

Phir `.env` mein best wala daal — **naam se, index se nahi:**

```env
SAARTHI_MIC_DEVICE=Microphone Array (Realtek(R) Audio)
```

**Naam se kyun?** Device **index reboot pe ya USB mic nikaalne-lagane pe
badal jaata hai.** Naam usually same rehta hai. `Realtek` jaisa hissa
bhi chalega.

Mic bahut dheema hi rahe to threshold bhi kam kar sakta hai:
```env
SAARTHI_MIC_MIN_THRESHOLD=150
```

#### 🔇 Voice bole "Mic se audio nahi aa raha (sirf zeros)" — `--mic-stream`

Ye **BUG#22** hai aur ye sabse dhokebaaz bug tha. Symptom:

```
python hardware_check.py --mic       ->  peak 24087   ✅ audio aa raha hai
python voice_cli.py                 ->  "kuch sunai nahi diya"  ❌
```

Ek hi mic, ek hi awaaz, do alag jawab. `--mic-live` ne wajah pakdi:

```
[INFO] chunks: 333                    <- stream chal raha tha
[INFO] tera sabse loud chunk: 0       <- par HAR chunk zero tha
```

Wajah: PortAudio ka backend (MME / WASAPI / WDM-KS) har machine pe alag
behave karta hai. Us machine pe **blocking `stream.read()` zeros deta
tha, par callback-based stream chalta tha.** Ab code callback use karta
hai, to ye apne aap theek hona chahiye.

Phir bhi aaye to **guess mat kar — measure kar:**

```bash
python hardware_check.py --mic-stream
```

Ye **8 alag stream config** try karta hai aur peak dikhata hai:

```
   sd.rec (baseline)                      [########............]  4200  accha
   callback, blocksize=chunk              [########............]  4100  accha
   blocking read, blocksize=chunk         [....................]     0  kuch nahi
```

Jo chale, uski **exact `.env` line** bata deta hai:

```env
SAARTHI_MIC_BLOCKSIZE=0
SAARTHI_MIC_LATENCY=high
```

> **Ek zaroori farq:** voice ab `TIMEOUT` aur `NO_AUDIO` alag batata hai.
> `kuch sunai nahi diya` = mic theek hai, tu bola nahi.
> `Mic se audio nahi aa raha (sirf zeros)` = **teri galti nahi hai**,
> audio pipeline ka issue hai. Zor se bolne se kuch nahi hoga.

#### 🤖 Whisper ne kuch aisa suna jo tune bola hi nahi?

Whisper YouTube captions pe train hai. Mushkil audio pe wo apni
**training data se phrases nikaal deta hai** — audio se nahi:

```
tu bola : "paytm kholo"
suna    : "So, you know, it's a YouTube story."
```

Ye **BUG#23** tha. Khatra samajh: us text mein "YouTube" hai, to agent
**sach mein YouTube khol deta** — jabki tune paytm maanga tha.

Ab aise phrases reject ho jaate hain aur "dobara bol" aata hai. Galat
kaam karne se accha hai.

`--stt-tune` chala ke dekh ki teri awaaz pe kaunsi setting best hai —
wo `logprob` aur `no_speech` bhi dikhata hai (Whisper ko khud kitna
bharosa tha):

```bash
python hardware_check.py --stt-tune
```

**Ctrl+C mat dabana** — 3 setting try hoti hain, ~30 second lagta hai.

> **Wo aakhri wala khaas hai.** Whisper `[-1, 1]` range maangta hai, mic
> `int16` (0-32767) deta hai. Divide by 32768 zaroori hai. Code mein hai,
> par asli mic pe verify nahi hua.

---

### 3. Speaker (awaaz)

```bash
# Linux
sudo apt install espeak-ng

# Windows
pip install pyttsx3

# macOS — kuch nahi chahiye, 'say' built-in hai
```

Best quality chahiye to Piper (free):
```bash
pip install piper-tts
# Voice model: https://huggingface.co/rhasspy/piper-voices
# Phir .env mein: PIPER_MODEL=/path/to/voice.onnx
```

```bash
python hardware_check.py --speaker
```

- [ ] Kam se kam ek backend `●` hai (null ke alawa)
- [ ] Awaaz **sach mein sunai di**
- [ ] Hinglish shabd samajh aaye (Indian English accent ke liye
      `.env` mein `ESPEAK_VOICE=en-in`)

---

### 4. Phone (ADB) — sabse zyada value

Ye **sabse important** hardware test hai, kyunki poora Android control
isi pe khada hai.

**Phone pe:**
1. Settings → About phone → **Build number pe 7 baar tap**
   (Developer options unlock ho jaayega)
2. Settings → Developer options → **USB Debugging ON**
3. USB cable laga — **charging-only cable se kaam nahi hoga**
4. Phone pe popup aayega → **Allow**

**Laptop pe:**
```bash
python hardware_check.py --phone
```

- [ ] `adb installed` PASS
- [ ] `Phone connected` PASS
- [ ] `Device info padha` PASS
- [ ] **`Screen padh sakte hain (ui_tree)` PASS** ← ye sabse zaroori hai

> **`ui_tree` fail hua to bata dena.** Uske bina `text_pe_tap` aur
> **self-healing dono kaam nahi karenge** — sirf blind coordinates
> bachenge, jo BUG#3 ki wajah se khatarnak hai.

#### Phone ke aam problems

| Problem | Fix |
|---|---|
| `adb: command not found` | [Platform Tools](https://developer.android.com/tools/releases/platform-tools) download kar, folder PATH mein daal |
| `unauthorized` | Phone pe Allow dabao. Na aaye to Developer options → Revoke USB debugging authorizations |
| `offline` | Cable nikaal ke dobara laga, ya phone restart kar |
| Koi device nahi | Doosra USB cable try kar (data cable chahiye), doosra port try kar |
| Xiaomi/Redmi pe kaam nahi | Developer options mein **"USB debugging (Security settings)"** bhi ON karna padta hai |

#### Cable ke bina (WiFi se)

```bash
python cli.py
# phir bol: "phone ko wifi se jodo"
```
Pehli baar USB chahiye hoga, uske baad cable ki zarurat nahi.

---

### 5. Asli kaam ka test

Ab jo asli kaam karke dekh:

```bash
python cli.py
```

| Bol ke dekh | Kya hona chahiye |
|---|---|
| `youtube pe tere bin gaana chala do` | Naya tab khule, **video CHALE** (search karke ruke nahi) |
| `play tere bin on youtube` | Same, par jawab **English** mein |
| `mere phone me kya notifications hain` | Phone se notifications aayein |
| `laptop pe batao kitni disk space bachi hai` | Sahi command chale (Windows pe `dir`, Linux pe `df`) |
| `screenshot lo aur batao screen pe kya hai` | Screenshot le, vision model padhe |

**Voice mode:**
```bash
python voice_cli.py --check     # setup diagnostic
python voice_cli.py --once      # ek baar bol ke test
python voice_cli.py             # pura loop
```

---

## Jo bug mile, wo aise report kar

Achhi bug report mein 4 cheezein hoti hain:

```
1. KYA BOLA/KIYA:
   "youtube pe tere bin chala do"

2. KYA HONA CHAHIYE THA:
   Video chalna chahiye tha

3. KYA HUA:
   Search page khula, phir ruk gaya. Video nahi chala.

4. OUTPUT (poora copy-paste, ANSI codes ke saath bhi theek hai):
   │ ▸ website_kholo(url=youtube, search=tere bin)
   │ ✓ Agent ke browser mein naya tab khola
   saarthi  Search kar diya, pehla video chala le
```

Aur saath mein `python hardware_check.py --save` ki report bhej de.

> **API keys kabhi mat bhejna.** `hardware_check.py` ki report mein keys
> nahi hoti — wo safe hai. Par apni `.env` file ka screenshot **kabhi
> mat bhejna.** Is project mein **teen baar** keys galti se share ho chuki
> hain aur revoke karni padi.

---

## Quick reference

```bash
python run_tests.py                  # 218 tests, hardware ke bina
python hardware_check.py             # sab hardware check + report
python hardware_check.py --save      # report file mein
python cli.py                        # text mode
python voice_cli.py --check          # voice setup diagnostic
```

| Command | Kab |
|---|---|
| `/status` | Sab kuch ek jagah |
| `/devices` | Phone connect nahi ho raha |
| `/models` | `model_not_found` error aaye |
| `/retry` | Provider hat gaya ho |
| `/browser` | Tab switch ho raha ho |
