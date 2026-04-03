import asyncio
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from config import API_ID, API_HASH, SOURCES, TARGET, CHECK_INTERVAL

SESSION_NAME = "data/session"
LOG_DIR = "data/logs"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# store last processed message id per channel
LAST_MESSAGES = {}


def ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def cleanup_old_logs(days=7):
    now = datetime.now()

    if not os.path.exists(LOG_DIR):
        return

    for filename in os.listdir(LOG_DIR):
        filepath = os.path.join(LOG_DIR, filename)
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if now - file_time > timedelta(days=days):
                os.remove(filepath)


def get_log_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{today}.log")


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
    text = message.text or ""

    log_line = f"[{datetime.now()}] [{chat_name}] [{msg_types}] {text}\n"

    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(log_line)


async def process_channel(entity):
    messages = await client.get_messages(entity, limit=5)

    if not messages:
        return

    messages = list(reversed(messages))  # oldest → newest

    last_id = LAST_MESSAGES.get(entity.id)

    for msg in messages:
        if last_id and msg.id <= last_id:
            continue

        print(f"=== NEW MESSAGE from {entity.id} ===")

        try:
            await log_message(msg, entity)
            await client.forward_messages(TARGET, msg)
            print("✅ Sent")
        except Exception as e:
            print("❌ Error:", e)

        LAST_MESSAGES[entity.id] = msg.id


async def main():
    ensure_log_dir()
    cleanup_old_logs()

    print(f"📂 Logs dir: {LOG_DIR}")
    print(f"📂 Session: {SESSION_NAME}")

    await client.start()

    # resolve channel entities
    entities = []
    for source in SOURCES:
        entity = await client.get_entity(source)
        print(f"✅ Source connected: {source} -> {entity.id}")
        entities.append(entity)

    print("🚀 Polling started...")

    while True:
        for entity in entities:
            await process_channel(entity)

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())