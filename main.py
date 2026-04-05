import asyncio
import os
import json
import hashlib
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH, SOURCES, TARGET, CHECK_INTERVAL, CACHE_TTL

SESSION_NAME = "data/session"
LOG_DIR = "data/logs"
CACHE_FILE = "data/message_cache.json"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

LAST_MESSAGES = {}
MESSAGE_CACHE = {}
TARGET_ID = None


# ================= LOG =================

def ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def cleanup_old_logs(days=7):
    now = datetime.utcnow()

    if not os.path.exists(LOG_DIR):
        return

    for filename in os.listdir(LOG_DIR):
        filepath = os.path.join(LOG_DIR, filename)
        if os.path.isfile(filepath):
            file_time = datetime.utcfromtimestamp(os.path.getmtime(filepath))
            if now - file_time > timedelta(days=days):
                os.remove(filepath)


def get_log_file():
    today = datetime.utcnow().strftime("%d-%m-%Y")
    return os.path.join(LOG_DIR, f"{today}.log")


def write_log(level, message):
    timestamp = datetime.utcnow().isoformat() + "Z"
    log_line = f"[{timestamp}] [{level}] {message}\n"

    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(log_line)


def log_separator():
    write_log("INFO", "-" * 70)


def get_channel_id(entity):
    return int(f"-100{entity.id}")


def get_message_types(message):
    types = []

    if message.text:
        types.append("TEXT")

    if message.photo:
        types.append("PICTURE")

    if message.video:
        types.append("VIDEO")

    if message.document:
        types.append("FILE")

    if not types:
        types.append("UNKNOWN")

    return "+".join(types)


async def log_message(message, chat):
    chat_name = getattr(chat, "username", None) or getattr(chat, "title", "unknown")
    msg_types = get_message_types(message)

    write_log("INFO", f"[{chat_name}] [{msg_types}]")


# ================= CACHE =================

def load_cache():
    global MESSAGE_CACHE

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            MESSAGE_CACHE = json.load(f)


def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(MESSAGE_CACHE, f)


def cleanup_cache():
    now = datetime.utcnow().timestamp()

    keys_to_delete = [
        key for key, ts in MESSAGE_CACHE.items()
        if now - ts > CACHE_TTL
    ]

    for key in keys_to_delete:
        del MESSAGE_CACHE[key]


# ================= DEDUP =================

def get_message_key(msg):
    if msg.forward and msg.forward.chat and msg.forward.channel_post:
        return f"fwd:{msg.forward.chat.id}:{msg.forward.channel_post}"

    base = ""

    if msg.text:
        base += msg.text.strip()

    if msg.media:
        base += str(type(msg.media))

    return "hash:" + hashlib.sha256(base.encode("utf-8")).hexdigest()


# ================= PROCESS =================

async def process_channel(entity):
    last_id = LAST_MESSAGES.get(entity.id, 0)

    messages = await client.get_messages(entity, min_id=last_id)

    if not messages:
        return

    messages = list(reversed(messages))

    for msg in messages:
        key = get_message_key(msg)

        if key in MESSAGE_CACHE:
            write_log("INFO", f"Duplicate skipped (msg_id={msg.id})")
            LAST_MESSAGES[entity.id] = msg.id
            continue

        write_log("INFO", f"New message detected from entity_id={entity.id}")

        try:
            await log_message(msg, entity)
            await client.forward_messages(TARGET_ID, msg)
            write_log("INFO", "Message forwarded successfully")

            MESSAGE_CACHE[key] = datetime.utcnow().timestamp()

        except FloodWaitError as e:
            write_log("ERROR", f"FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds)

        except Exception as e:
            write_log("ERROR", f"Failed to forward message: {e}")

        LAST_MESSAGES[entity.id] = msg.id


# ================= COMMANDS =================

def get_commands_text():
    return (
        "📜 Available commands:\n\n"
        "commands\n"
        "give-log DD-MM-YYYY\n"
        "list-logs"
    )


@client.on(events.NewMessage)
async def handle_commands(event):
    try:
        if event.chat_id != TARGET_ID:
            return

        text = event.raw_text.strip().lower()

        # -------- commands --------
        if text == "commands":
            await event.reply(get_commands_text())

        # -------- give-log --------
        elif text.startswith("give-log"):
            parts = text.split()

            if len(parts) < 2:
                await event.reply("Usage: give-log DD-MM-YYYY")
                return

            date_str = parts[1]
            log_file = os.path.join(LOG_DIR, f"{date_str}.log")

            if os.path.exists(log_file):
                await client.send_file(
                    TARGET_ID,
                    log_file,
                    caption=f"📄 Log file for {date_str}"
                )
                write_log("INFO", f"Log sent via command: {date_str}")
            else:
                await event.reply(f"❌ Log not found: {date_str}")

        # -------- list-logs --------
        elif text == "list-logs":
            if not os.path.exists(LOG_DIR):
                await event.reply("No logs directory found")
                return

            files = sorted(os.listdir(LOG_DIR))

            if not files:
                await event.reply("No logs available")
                return

            logs = "\n".join(files[-20:])
            await event.reply(f"📂 Available logs:\n\n{logs}")

    except Exception as e:
        write_log("ERROR", f"Command error: {e}")


# ================= POLLING =================

async def polling_loop(entities):
    while True:
        for entity in entities:
            try:
                await process_channel(entity)
            except Exception as e:
                write_log("ERROR", f"Error processing channel {entity.id}: {e}")

        cleanup_cache()
        save_cache()

        await asyncio.sleep(CHECK_INTERVAL)


# ================= MAIN =================

async def main():
    ensure_log_dir()
    cleanup_old_logs()
    load_cache()

    write_log("INFO", "=" * 70)
    write_log("INFO", "BOT STARTED")
    write_log("INFO", f"Time: {datetime.utcnow().isoformat()}Z")
    write_log("INFO", f"Sources count: {len(SOURCES)}")
    write_log("INFO", f"TARGET: {TARGET}")
    write_log("INFO", f"Logs dir: {LOG_DIR}")
    write_log("INFO", f"Session: {SESSION_NAME}")
    write_log("INFO", "=" * 70)

    await client.start()

    global TARGET_ID
    target_entity = await client.get_entity(TARGET)
    TARGET_ID = target_entity.id

    write_log("INFO", f"Resolved TARGET_ID: {TARGET_ID}")

    entities = []

    for source in SOURCES:
        try:
            entity = await client.get_entity(source)

            channel_id = get_channel_id(entity)

            write_log(
                "INFO",
                f"[source:{source}] -> [entity_id:{entity.id}] [channel_id:{channel_id}] [name:{entity.title}]"
            )

            last_msg = await client.get_messages(entity, limit=1)

            if last_msg:
                msg = last_msg[0]

                key = get_message_key(msg)

                if key not in MESSAGE_CACHE:
                    try:
                        await log_message(msg, entity)
                        await client.forward_messages(TARGET_ID, msg)
                        write_log("INFO", "Initial message sent")

                        MESSAGE_CACHE[key] = datetime.utcnow().timestamp()

                    except Exception as e:
                        write_log("ERROR", str(e))

                LAST_MESSAGES[entity.id] = msg.id

            entities.append(entity)
            log_separator()

        except Exception as e:
            write_log("ERROR", f"Failed to connect source {source}: {e}")

    write_log("INFO", "Polling started")

    await polling_loop(entities)


if __name__ == "__main__":
    asyncio.run(main())