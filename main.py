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

# runtime state (ephemeral)
RUNTIME_SOURCES = []
RUNTIME_ENTITIES = []
CURRENT_TARGET = None


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

    write_log(
        "INFO",
        f"New message detected from entity_id={chat.id} "
        f"[{chat_name}] [{msg_types}] msg_id={message.id}"
    )


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
    # --- Forward-based dedup (PRIMARY) ---
    if msg.forward:
        fwd = msg.forward

        # Use original source (important for cross-channel forwards)
        if hasattr(fwd, "from_id") and hasattr(fwd.from_id, "channel_id") and fwd.channel_post:
            return f"fwd:{fwd.from_id.channel_id}:{fwd.channel_post}"

        # Fallback (older cases)
        if fwd.chat and fwd.channel_post:
            return f"fwd:{fwd.chat.id}:{fwd.channel_post}"

    # --- Content-based dedup (FALLBACK) ---
    parts = []

    if msg.text:
        parts.append(msg.text.strip())

    # Use media IDs
    if msg.photo:
        parts.append(f"photo:{msg.photo.id}")

    if msg.video:
        parts.append(f"video:{msg.video.id}")

    if msg.document:
        parts.append(f"doc:{msg.document.id}")

    base = "|".join(parts)

    return "hash:" + hashlib.sha256(base.encode("utf-8")).hexdigest()


# ================= HELPERS =================

def get_entity_type(entity):
    if hasattr(entity, "broadcast") and entity.broadcast:
        return "channel"
    if hasattr(entity, "megagroup") and entity.megagroup:
        return "group"
    return "user"


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

        try:
            await log_message(msg, entity)
            await client.forward_messages(CURRENT_TARGET, msg)
            write_log("INFO", f"Message msg_id={msg.id} forwarded successfully")

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
        "help\n"
        "list-sources\n"
        "get-info <input>\n"
        "add-source <input>\n"
        "remove-source <input>\n"
        "set-target <input>\n"
        "get-log DD-MM-YYYY\n"
        "list-logs"
    )


@client.on(events.NewMessage)
async def handle_commands(event):
    try:
        if event.chat_id != TARGET_ID:
            return

        text = event.raw_text.strip().lower()

        # -------- help --------
        if text == "help":
            await event.reply(get_commands_text())

        # -------- list-sources --------
        elif text == "list-sources":
            if not RUNTIME_ENTITIES:
                await event.reply("No sources configured")
                return

            lines = []
            for e in RUNTIME_ENTITIES:
                lines.append(f"[{e.title}] & [{get_channel_id(e)}]")

            await event.reply("\n".join(lines))

        # -------- get-info --------
        elif text.startswith("get-info"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply("Usage: get-info <input>")
                return

            source_input = parts[1]

            try:
                entity = await client.get_entity(source_input)
                entity_type = get_entity_type(entity)

                if entity_type in ("channel", "group"):
                    channel_id = get_channel_id(entity)
                    response = (
                        f"[source:{source_input}] -> "
                        f"[entity_id:{entity.id}] "
                        f"[channel_id:{channel_id}] "
                        f"[type:{entity_type}] "
                        f"[name:{entity.title}]"
                    )
                else:
                    response = (
                        f"[source:{source_input}] -> "
                        f"[entity_id:{entity.id}] "
                        f"[type:{entity_type}] "
                        f"[name:{getattr(entity, 'first_name', 'unknown')}]"
                    )

                await event.reply(response)

            except Exception:
                await event.reply(f"❌ Failed to resolve: {source_input}")

        # -------- add-source --------
        elif text.startswith("add-source"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply("Usage: add-source <input>")
                return

            source_input = parts[1]

            try:
                entity = await client.get_entity(source_input)

                if entity.id in [e.id for e in RUNTIME_ENTITIES]:
                    await event.reply("Already exists")
                    return

                RUNTIME_ENTITIES.append(entity)
                RUNTIME_SOURCES.append(source_input)

                await event.reply(f"Added: {entity.title}")

            except Exception:
                await event.reply("❌ Failed to add source")

        # -------- remove-source --------
        elif text.startswith("remove-source"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply("Usage: remove-source <input>")
                return

            source_input = parts[1]

            try:
                entity = await client.get_entity(source_input)

                RUNTIME_ENTITIES[:] = [e for e in RUNTIME_ENTITIES if e.id != entity.id]
                LAST_MESSAGES.pop(entity.id, None)

                await event.reply(f"Removed: {entity.title}")

            except Exception:
                await event.reply("❌ Failed to remove source")

        # -------- set-target --------
        elif text.startswith("set-target"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await event.reply("Usage: set-target <input>")
                return

            target_input = parts[1]

            try:
                entity = await client.get_entity(target_input)

                global CURRENT_TARGET
                CURRENT_TARGET = entity.id

                await event.reply(f"Target changed to: {getattr(entity, 'title', 'user')}")

            except Exception:
                await event.reply("❌ Failed to change target")

        # -------- get-log --------
        elif text.startswith("get-log"):
            parts = text.split()

            if len(parts) < 2:
                await event.reply("Usage: get-log DD-MM-YYYY")
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

            await event.reply("\n".join(files[-20:]))


        # -------- fallback --------
        else:
            await event.reply("❓ Unknown command. Use 'help' to see available commands.")

    except Exception as e:
        write_log("ERROR", f"Command error: {e}")


# ================= POLLING =================

async def polling_loop():
    while True:
        for entity in list(RUNTIME_ENTITIES):
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

    global TARGET_ID, CURRENT_TARGET

    target_entity = await client.get_entity(TARGET)
    TARGET_ID = target_entity.id
    CURRENT_TARGET = TARGET_ID

    write_log("INFO", f"Resolved TARGET_ID: {TARGET_ID}")

    # Load initial sources into runtime
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
                        await client.forward_messages(CURRENT_TARGET, msg)
                        write_log("INFO", f"Init message msg_id={msg.id} forwarded successfully")

                        MESSAGE_CACHE[key] = datetime.utcnow().timestamp()

                    except Exception as e:
                        write_log("ERROR", str(e))

                LAST_MESSAGES[entity.id] = msg.id

            RUNTIME_ENTITIES.append(entity)
            RUNTIME_SOURCES.append(source)

            log_separator()

        except Exception as e:
            write_log("ERROR", f"Failed to connect source {source}: {e}")

    write_log("INFO", "Polling started")

    await polling_loop()


if __name__ == "__main__":
    asyncio.run(main())