import asyncio
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from config import API_ID, API_HASH, SOURCES, TARGET

# Path for Docker volume
SESSION_NAME = "data/session"
LOG_DIR = "data/logs"

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


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


def get_message_types(event):
    types = []

    if event.message.text:
        types.append("TEXT")

    if event.message.photo:
        types.append("PICTURE")

    if event.message.video:
        types.append("VIDEO")

    if event.message.document:
        types.append("FILE")

    if not types:
        types.append("UNKNOWN")

    return "+".join(types)


async def log_event(event):
    chat = await event.get_chat()
    chat_name = getattr(chat, "username", None) or getattr(chat, "title", "unknown")

    msg_types = get_message_types(event)
    text = event.message.text or ""

    log_line = f"[{datetime.now()}] [{chat_name}] [{msg_types}] {text}\n"

    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(log_line)


@client.on(events.NewMessage(chats=SOURCES))
async def handler(event):
    try:
        await log_event(event)
        await client.forward_messages(TARGET, event.message)
        print("✅ sended")
    except Exception as e:
        print("❌ Error:", e)


async def main():
    ensure_log_dir()
    cleanup_old_logs()

    print(f"📂 Logs dir: {LOG_DIR}")
    print(f"📂 Session: {SESSION_NAME}")

    await client.start()
    print("🚀 Bot started and listening...")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())