# 🚀 Telegram Userbot Forwarder

Simple Telegram userbot that listens to multiple channels and forwards messages into one place.

Supports:

* Public and private channels
* Text, images, videos
* Logging with rotation (UTC)
* Docker deployment

---

## 📦 Requirements

* Docker
* Telegram account
* API_ID and API_HASH (from https://my.telegram.org)

---

## ⚙️ Configuration

Edit `config.py`:

```python
API_ID = 123456
API_HASH = "your_api_hash"

SOURCES = [
    "channel_username",
    -1001234567890,  # private channel ID
]

TARGET = "your_target_username"

CHECK_INTERVAL = 10
```

---

## 🐳 Docker Setup

### 🔹 Build image

```bash
docker build -t userbot .
```

---

# 🚀 First Run (NO session)

First time you need to login manually.

### ▶️ Run interactive container:

```bash
docker run -it \
  -v $(pwd)/data:/app/data \
  --name userbot \
  userbot
```

### 📲 What will happen:

You will be asked to enter:

* phone number
* login code (from Telegram)
* password (if 2FA enabled)

Example:

```
Please enter your phone: +123456789
Please enter the code: 12345
```

After successful login:

```
Signed in successfully
```

👉 Session will be saved in:

```
data/session.session
```

---

## 🛑 Stop container

Press:

```
Ctrl + C
```

Then remove container:

```bash
docker rm userbot
```

---

# 🚀 Next Runs (WITH session)

Now login is not required anymore.

### ▶️ Run in background:

```bash
docker run -d \
  -v $(pwd)/data:/app/data \
  --name userbot \
  --restart=always \
  userbot
```

---

## 📊 Logs

Logs are stored in:

```
data/logs/
```

### View logs:

```bash
docker logs -f userbot
```

or

```bash
cat data/logs/2026-04-05.log
```

---

## 🔄 Update application

```bash
docker rm -f userbot
docker build -t userbot .
docker run -d -v $(pwd)/data:/app/data --name userbot --restart=always userbot
```

---

## ⚠️ Notes

* Do NOT commit `config.py` with real credentials
* Session is stored in `data/` (keep it safe)
* Private channels require user access

---

## 💡 Features

* Polling-based (works without admin rights)
* Prevents duplicate messages
* Structured logging
* Docker-ready

---

## 🧠 Tips

* Use channel IDs (`-100...`) instead of links for stability
* Lower `CHECK_INTERVAL` for faster updates
* Logs are automatically cleaned after 7 days
---
