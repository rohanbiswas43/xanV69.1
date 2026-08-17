# 📖 Complete Setup Guide — XAUUSDT.P Bot

---

## 🖥️ PART 1 — Apne PC pe Chalao (Local)

### Step 1 — Python Install karo

**Windows:**
1. https://python.org/downloads pe jao
2. Latest Python 3.11 download karo
3. Install karo — **"Add Python to PATH"** checkbox zaroor tick karo ✅

**Verify karo** — CMD open karo aur type karo:
```
python --version
```
Output aana chahiye: `Python 3.11.x`

---

### Step 2 — Bot Files Download Karo

1. Is guide ke sath diye gaye files download karo:
   - `bot.py`
   - `requirements.txt`
   - `Procfile`

2. Ek folder banao, jaise `C:\xauusd-bot\`
3. Teeno files us folder mein rakho

---

### Step 3 — Telegram Bot Token Lo

1. Telegram open karo
2. **@BotFather** search karo
3. `/newbot` send karo
4. Bot ka naam daalo (jaise: `My Gold Bot`)
5. Username daalo jo `bot` pe khatam ho (jaise: `mygold_alert_bot`)
6. BotFather ek **token** dega — copy karo!
   ```
   Token dikhta hai aisa:  1234567890:ABCdefGHI_jklMNOpqrSTU
   ```

---

### Step 4 — Dependencies Install Karo

CMD/Terminal open karo aur bot folder mein jao:

```cmd
cd C:\xauusd-bot

pip install -r requirements.txt
```

Wait karo jab tak sab install ho jaye (2-3 minutes).

---

### Step 5 — Token Set Karo aur Run Karo

**Windows CMD:**
```cmd
set BOT_TOKEN=1234567890:ABCdefGHI_jklMNOpqrSTU

python bot.py
```

**Mac / Linux Terminal:**
```bash
export BOT_TOKEN="1234567890:ABCdefGHI_jklMNOpqrSTU"

python bot.py
```

Terminal mein dikhega:
```
🤖 Bot started | Binance XAUUSDT.P | interval=60s
```

---

### Step 6 — Test karo

1. Telegram mein apna bot (@username) dhundo
2. `/start` bhejo
3. `/price` bhejo — Binance se live price aana chahiye!

> ⚠️ **Note:** Jab tak terminal band nahi karte, bot chalta rahega.
> PC band karne pe bot ruk jayega.

---

## ☁️ PART 2 — 24/7 Free Cloud Pe Chalao (Railway.app)

Railway.app pe FREE mein bot 24 ghante chalao.
**Sirf ek GitHub account chahiye.**

---

### Step 1 — GitHub Account Banao (pehle se hai toh skip karo)

1. https://github.com jao
2. "Sign up" karo — free hai
3. Email verify karo

---

### Step 2 — GitHub Pe Bot Upload Karo

1. https://github.com/new jao
2. Repository name: `xauusd-bot`
3. **Private** rakho ✅ (token safe rahega)
4. "Create repository" click karo

GitHub aapko commands dega. CMD mein:
```cmd
cd C:\xauusd-bot

git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/AAPKA_USERNAME/xauusd-bot.git
git push -u origin main
```

> GitHub aapka username/password maangega — apna GitHub login daalo.

---

### Step 3 — Railway.app Account Banao

1. https://railway.app jao
2. **"Login with GitHub"** click karo
3. GitHub se authorize karo

---

### Step 4 — New Project Banao

1. Railway dashboard mein **"New Project"** click karo
2. **"Deploy from GitHub repo"** select karo
3. `xauusd-bot` repo select karo
4. **"Deploy Now"** click karo

---

### Step 5 — BOT_TOKEN Set Karo (IMPORTANT!)

1. Railway project mein **"Variables"** tab click karo
2. **"+ New Variable"** click karo
3. Daalo:
   - **Name:** `BOT_TOKEN`
   - **Value:** `1234567890:ABCdefGHI_jklMNOpqrSTU` (apna token)
4. **"Add"** click karo
5. Railway automatically redeploy karega

---

### Step 6 — Verify karo ki chal raha hai

1. Railway mein **"Deployments"** tab click karo
2. Latest deployment click karo
3. **"View Logs"** mein dikhna chahiye:
   ```
   🤖 Bot started | Binance XAUUSDT.P | interval=60s
   ```

**Done! 🎉 Ab aapka bot 24/7 chalta rahega!**

---

## 🔧 Common Problems & Solutions

| Problem | Solution |
|---|---|
| `pip not found` | Python install karo with PATH checkbox |
| `ModuleNotFoundError` | `pip install -r requirements.txt` dobara chalao |
| `BOT_TOKEN not set` | `set BOT_TOKEN=...` command chalao pehle |
| Bot respond nahi kar raha | Check karo terminal mein error toh nahi |
| Railway deploy fail | Logs check karo, BOT_TOKEN set hai? |

---

## 💰 Railway Free Plan Details

- **$5 free credit** har month milta hai
- Ek simple bot ke liye kaafi hai (~24/7 chalta hai)
- Agar credit khatam ho, **$5 add karo** (~₹415) next month ke liye
- Ya phir doosre free option: **Render.com**

---

## ⚡ Quick Reference — Bot Commands

| Command | Kya karta hai |
|---|---|
| `/price` | Live Binance price, mark, bid/ask, funding rate |
| `/chart 1h` | 1H candle chart (15m, 4h, 1d bhi kaam karta hai) |
| `/alert 4100` | Alert jab price $4100 pe pahunche |
| `/alert 3950 support` | Alert with note |
| `/alerts` | Sabhi active alerts dekhna |
| `/cancel 3` | Alert #3 hatao |
| `/zone 3950 4000 support` | Green zone chart pe |
| `/zone 4100 4150 resistance red` | Red zone chart pe |
| `/live` | Har 60 second pe price update toggle |
| `/help` | Poori list |

