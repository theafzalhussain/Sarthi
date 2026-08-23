# Deployment — Agent kahan chalaye

"Server chahiye? 24/7 kaise chalega? Mera PC kharab ho jaayega?"

Iska poora jawab. **Short answer: abhi server ki zarurat NAHI hai.**

---

## 🔴 Pehle ek critical baat

> **Cloud server tere phone ko control NAHI kar sakta.**

```
❌ Ye kaam nahi karega:

   [Cloud server, Mumbai datacenter]
              │
              │  ADB se phone control?
              ✗  NAHI — ADB ko USB ya
              │   same WiFi network chahiye
              ▼
   [Tera phone, ghar pe]
```

ADB **USB cable ya same local network** pe kaam karta hai, internet ke through nahi.

**Matlab:** brain cloud pe reh sakta hai, par **haath tere ghar pe hone padenge.**

Iska solution [Tailscale](#tailscale--missing-piece) hai (neeche).

---

## Server ki zarurat hai bhi ya nahi?

SAARTHI **reactive** hai — tu bolta hai, wo karta hai. Aise kaam ke liye server nahi chahiye.

| Kaam | Server chahiye? |
|---|---|
| "paytm kholo" | ❌ Nahi |
| "bijli ka bill bhar de" | ❌ Nahi |
| "internet pe dhoondh" | ❌ Nahi |
| Voice se command dena | ❌ Nahi |
| **"roz subah 7 baje alarm"** | ✅ Haan — koi jagta rehna chahiye |
| **"bill due ho to batana"** | ✅ Haan — monitoring |
| **"college se ghar ka AC band kar"** | ✅ Haan — remote trigger |

👉 **90% kaam bina server ho jaata hai.** Server sirf **proactive** cheezon ke liye.

---

## Chaar deployment models

### Model A: Laptop pe on-demand ⭐ (abhi ka setup)

```bash
python cli.py          # text mode
python voice_cli.py    # voice mode
```

| | |
|---|---|
| Cost | **₹0** |
| Setup | Ho chuka hai |
| Limitation | Laptop on hona chahiye |
| Kiske liye | **Phase 1-3 — abhi tere liye yahi** |

---

### Model B: Phone pe app 🏆 (Phase 4 — asli jawab)

**Ye end goal hai. Aur isme server ki zarurat hi nahi.**

```
   Tera phone
   ├── SAARTHI app (Kotlin)
   ├── Accessibility Service  -> screen control
   ├── Foreground Service     -> 24/7 background mein zinda
   └── LLM API call           -> internet se
```

**Kyun best hai:**
- Phone **already 24/7 on** rehta hai ✅
- Phone **already tere saath** rehta hai ✅
- Phone ke andar se phone control — **koi ADB, koi network problem nahi** ✅
- Cost **₹0** ✅

> 💡 **Phone hi tera server hai.** Ye baat bahut log miss karte hain.

---

### Model C: Purana phone = home server ⭐⭐ (24/7 ke liye best)

Ghar mein purana Android phone pada hai? Wo **₹12/month ka 24/7 server** ban sakta hai.

```
   Purana phone (Termux + Linux)
   ├── SAARTHI brain + scheduler
   ├── Same WiFi -> naye phone ko ADB se control kar sakta hai ✅
   └── Bijli: 1-2W (LED bulb se bhi kam)
```

Termux se purane Android pe Linux environment chal jaata hai — **root ki zarurat nahi**
([XDA](https://www.xda-developers.com/old-android-phone-home-server-beat-raspberry-pi/),
[linux-android](https://github.com/mayukh4/linux-android)).
Idle pe phone 1-2W leta hai, jo most home-lab setups se kaafi kam hai
([XDA](https://www.xda-developers.com/old-phone-perfect-for-home-lab-heres-what-you-can-do-with-it/)).

*(Content licensing ke liye rephrase kiya gaya)*

⚠️ Phone plugged rakhna padega, thanda rakh, aur **phooli hui battery wala phone use mat kar.**

---

### Model D: Cloud VM (Oracle Always Free)

| | |
|---|---|
| Cost | **₹0 forever** (trial nahi, genuinely free) |
| Kya kar sakta | Brain, scheduler, webhooks, dashboard |
| Kya **nahi** kar sakta | ❌ Tere phone ko ADB se control (Tailscale ke bina) |

**Oracle Cloud Always Free** sabse solid free option hai. Ek update: **15 June 2026 se** ARM Ampere ka free allocation **4 OCPU/24GB se 2 OCPU/12GB** kar diya gaya
([TerminalBytes](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026/),
[Oracle docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)).

**SAARTHI ke liye 2 OCPU / 12GB bahut zyada hai.** Koi dikkat nahi.

⚠️ **Render/Railway/Glitch se bacho 24/7 ke liye** — Render ka free tier **15 minute inactivity pe sleep** ho jaata hai ([Miget](https://miget.com/blog/best-render-alternatives)). Always-on agent ke liye bekaar.

*(Content licensing ke liye rephrase kiya gaya)*

---

## Tailscale — missing piece

"Cloud phone ko control nahi kar sakta" — iska solution:

```
[Oracle cloud VM] ──┐
                    │
[Purana phone]  ────┼── Tailscale (free mesh VPN)
                    │   sab ek "virtual LAN" pe
[Tera laptop]   ────┤
                    │
[Naya phone]    ────┘
```

**Tailscale** free mesh VPN hai (personal use). Saare devices ek private network pe aa jaate hain, chahe duniya mein kahin bhi hon.

Iske baad cloud server ghar ke phone ko ADB se control kar sakta hai. Cost **₹0**.

---

## ⚡ Bijli ka kharcha — asli numbers

India mein ~₹8/unit, 24/7 chalane pe:

| Device | Power | Mahine ka bijli |
|---|---|---|
| **Purana Android phone** | 1-2W | **~₹12** 🏆 |
| Raspberry Pi | 3-5W | ~₹30 |
| **Laptop (idle)** | 15-25W | **~₹110** |
| Desktop PC | 60-100W | **~₹450+** ❌ |
| **Oracle Cloud** | — | **₹0** 🏆 |

👉 Student ke liye: **purana phone ya Oracle Cloud.** Desktop PC 24/7 bilkul mat chala.

---

## 🔧 "Mera PC kharab ho jaayega?"

Seedha jawab: **kharab nahi hoga, par nuksaan hai.**

### ✅ Jo darne ki baat NAHI hai

Modern laptops mein **Battery Management System (BMS)** hota hai jo 100% pe pahunchne ke baad battery ko current dena band kar deta hai. Purane laptops mein overheating ka risk tha, ab cut-off protection built-in hai ([HP](https://www.hp.com/us-en/shop/tech-takes/is-it-bad-to-leave-laptop-plugged-in)).

Matlab **battery phategi nahi, overcharge nahi hogi.** 👍

### ⚠️ Jo asli nuksaan hai

| Problem | Detail |
|---|---|
| **Battery degradation** | Battery ko hamesha 100% pe rakhna + garmi, dono milke capacity gira dete hain ([HP](https://www.hp.com/us-en/shop/tech-takes/is-it-bad-to-leave-laptop-plugged-in)) |
| **GARMI — sabse bada risk** | Vents band hon ya laptop band karke rakha ho to andar temperature badhta hai, jisse battery, solder joints aur capacitors ki wear tez hoti hai |
| **Fan ghisna** | 24/7 chalne se fan bearings ghiste hain |
| **SSD writes** | Log files continuously likhne se — effect chhota hai, par hai |

*(Content licensing ke liye rephrase kiya gaya)*

### 🛡️ Laptop hi use karna hai to ye kar

```
1. Charge limit 80% pe set kar
   -> BIOS/vendor software mein option hota hai
   -> Battery life double ho jaayegi

2. Laptop KHULA rakh, hard surface pe
   -> Bed/sofa pe mat rakh, vents band ho jaate hain
   -> Garmi hi asli dushman hai

3. Lid band karke chalane se bacho

4. Mahine mein ek baar vents saaf kar

5. Raat ko sleep schedule kar (2-6 baje kaam nahi hai to sula de)
```

👉 **Salah:** apna **primary laptop 24/7 mat chala.** Wo tera padhai aur coding ka tool hai. **Purana phone ₹12/month mein wahi kaam kar dega.**

---

## Recommended path

```
ABHI (Phase 1-3)
└── Model A: laptop pe on-demand
    Server NAHI chahiye. Bas python cli.py / voice_cli.py
    Cost: ₹0

Phase 4 (Android app) ← ASLI JAWAB
└── Model B: phone khud agent chalayega
    KOI SERVER NAHI
    Phone already 24/7 on hai
    Cost: ₹0

Phase 5 (proactive features chahiye tab)
└── Model C: purana phone as server + Tailscale
    Cost: ~₹12/month bijli
```

### Ek line mein

> **Tujhe server ki zarurat abhi nahi hai. Aur Phase 4 ke baad kabhi nahi padegi — kyunki tera phone hi server ban jaayega.**

---

## Aage kya add karna hai (jab zarurat pade)

`saarthi/server/` module — abhi nahi bana:

- `/chat` endpoint — phone/browser se command bhejo
- `/voice` endpoint — audio upload karke transcribe
- Scheduler — "roz 7 baje" wale kaam
- Local network ya Tailscale ke through remote access

Isse **Model C aur D dono** possible ho jaayenge, aur Phase 4 ke Android app ko backend bhi mil jaayega.

---

## Security (agar server chalaye)

Agent ke paas device access hai — server chalate waqt dhyan:

1. **Kabhi public internet pe expose mat kar.** Tailscale ya local network only.
2. **Auth lagao** — bina token koi command na bhej sake.
3. **`.env` kabhi commit mat kar** (`.gitignore` mein already hai).
4. **`SAARTHI_CONFIRM_RISKY=true` rakh** — server pe to bilkul.
5. **Logs check kar** — kya-kya command aaya, dekhta reh.
