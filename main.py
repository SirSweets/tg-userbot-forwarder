import asyncio
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from config import API_ID, API_HASH, SOURCES, TARGET, CHECK_INTERVAL

SESSION_NAME = "data/session"
LOG_DIR = "data/logs"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

LAST_MESSAGES = {}


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
    today = datetime.utcnow().strftime("%Y-%m-%d")
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
    text = message.text or ""

    write_log("INFO", f"[{chat_name}] [{msg_types}] {text}")


async def process_channel(entity):
    messages = await client.get_messages(entity, limit=5)

    if not messages:
        return

    messages = list(reversed(messages))

    last_id = LAST_MESSAGES.get(entity.id)

    for msg in messages:
        if last_id and msg.id <= last_id:
            continue

        write_log("INFO", f"New message detected from entity_id={entity.id}")

        try:
            await log_message(msg, entity)
            await client.forward_messages(TARGET, msg)
            write_log("INFO", "Message forwarded successfully")
        except Exception as e:
            write_log("ERROR", f"Failed to forward message: {e}")

        LAST_MESSAGES[entity.id] = msg.id


async def main():
    ensure_log_dir()
    cleanup_old_logs()

    # 🔥 START BANNER
    write_log("INFO", "=" * 70)
    write_log("INFO", "BOT STARTED")
    write_log("INFO", f"Time: {datetime.utcnow().isoformat()}Z")
    write_log("INFO", f"Sources count: {len(SOURCES)}")
    write_log("INFO", f"TARGET: {TARGET}")
    write_log("INFO", f"Logs dir: {LOG_DIR}")
    write_log("INFO", f"Session: {SESSION_NAME}")
    write_log("INFO", "=" * 70)

    await client.start()

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

                write_log("INFO", f"Initial message from entity_id={entity.id}")

                try:
                    await log_message(msg, entity)
                    await client.forward_messages(TARGET, msg)
                    write_log("INFO", "Initial message sent")
                except Exception as e:
                    write_log("ERROR", f"Failed to send initial message: {e}")

                LAST_MESSAGES[entity.id] = msg.id

            entities.append(entity)

            # 🔥 separator between channels
            log_separator()

        except Exception as e:
            write_log("ERROR", f"Failed to connect source {source}: {e}")

    write_log("INFO", "Polling started")

    while True:
        for entity in entities:
            try:
                await process_channel(entity)
            except Exception as e:
                write_log("ERROR", f"Error processing channel {entity.id}: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())