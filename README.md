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
CACHE_TTL = 86400
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
* No message loss (`min_id` based fetching)
* Smart deduplication (forward + content hash)
* Runtime source management (add/remove without restart)
* Telegram command interface (no SSH required)
* Structured logging with message types
* Docker-ready

---

## 🧠 Tips

* Use channel IDs (`-100...`) instead of links for stability
* Lower `CHECK_INTERVAL` for faster updates
* Logs are automatically cleaned after 7 days
---


---

## 🤖 Commands (via Telegram)

You can control the bot directly from your `TARGET` chat (e.g. your main account).

⚠️ All changes are **runtime-only** and will be reset after bot restart.

---

### 📜 Available commands:

```
commands
list-sources
get-info <input>
add-source <input>
remove-source <input>
set-target <input>
get-log DD-MM-YYYY
list-logs
```

---

### 📂 List sources

```
list-sources
```

Shows all currently active sources:

```
Channel Name | -1001234567890
```

---

### 🔍 Get info about entity

```
get-info some_channel
get-info https://t.me/channel
get-info -1001234567890
```

Returns:

```
[source:input] -> [entity_id:...] [channel_id:...] [type:...] [name:...]
```

Useful for debugging and getting `channel_id`.

---

### ➕ Add source (runtime)

```
add-source some_channel
```

Adds new channel to monitoring without restart.

---

### ➖ Remove source (runtime)

```
remove-source some_channel
```

Stops listening to the channel.

---

### 🎯 Change target (runtime)

```
set-target some_chat
```

Changes destination where messages are forwarded.

---

### 📄 Get log file

```
get-log 05-04-2026
```

Bot will send the requested log file.

---

### 📂 List logs

```
list-logs
```

Shows available log files.

---

### ℹ️ Show commands

```
commands
```

Displays all available commands.

---

## 🧾 Logging

Logs are stored per day in UTC:

```
data/logs/DD-MM-YYYY.log
```

Each message contains:

* Source channel
* Message type (TEXT / PICTURE / VIDEO / FILE / UNKNOWN)

Example:

```
[source:channel_name] [TEXT]
```

---

## 🔁 Deduplication

The bot prevents duplicate messages using two strategies:

1. **Forward metadata (primary)**  
   Detects original message via Telegram forward info  
   (prevents duplicates across channels)

2. **Content hash (fallback)**  
   Prevents duplicates if message is copied manually

---

## ⚡ Reliability

* Uses `min_id` instead of `limit`
* Ensures no message loss between polling cycles
* Works correctly even if multiple messages arrive at once

---

## 🧠 Notes

* No admin rights required — works as userbot
* Commands work directly in Telegram (no SSH needed)
* Cache is stored in `data/message_cache.json`
* Old cache entries are automatically cleaned using TTL

---
