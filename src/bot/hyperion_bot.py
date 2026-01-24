#!/usr/bin/env python3
"""
Hyperion Bot v2 - File-based message passing to master Claude session

Instead of spawning Claude processes, this bot:
1. Writes incoming messages to ~/messages/inbox/
2. Watches ~/messages/outbox/ for replies
3. Sends replies back to Telegram

The master Claude session processes inbox messages and writes to outbox.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuration from environment
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = [int(x) for x in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip()]

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
if not ALLOWED_USERS:
    raise ValueError("TELEGRAM_ALLOWED_USERS environment variable is required")

INBOX_DIR = Path.home() / "messages" / "inbox"
OUTBOX_DIR = Path.home() / "messages" / "outbox"
AUDIO_DIR = Path.home() / "messages" / "audio"

# Ensure directories exist
INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Logging
LOG_DIR = Path.home() / "hyperion-workspace" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "telegram-bot.log"),
    ],
)
log = logging.getLogger("hyperion")

# Global reference to the bot app and event loop for sending replies
bot_app = None
main_loop = None


class OutboxHandler(FileSystemEventHandler):
    """Watches outbox for reply files and sends them via Telegram."""

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.json'):
            # Schedule on the bot's event loop from watchdog thread
            if bot_app and main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.process_reply(event.src_path),
                    main_loop
                )

    async def process_reply(self, filepath):
        try:
            await asyncio.sleep(0.1)  # Brief delay to ensure file is written
            with open(filepath, 'r') as f:
                reply = json.load(f)

            chat_id = reply.get('chat_id')
            text = reply.get('text', '')

            if chat_id and text and bot_app:
                await bot_app.bot.send_message(chat_id=chat_id, text=text)
                log.info(f"Sent reply to {chat_id}: {text[:50]}...")

            # Remove processed file
            os.remove(filepath)

        except Exception as e:
            log.error(f"Error processing reply {filepath}: {e}")


def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USERS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    await update.message.reply_text(
        f"👋 Hey {user.first_name}!\n\n"
        "I'm Hyperion. Messages you send here go to the master Claude session.\n\n"
        "The session will process them and reply back here."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if not is_authorized(user.id):
        log.warning(f"Unauthorized: {user.id}")
        return

    msg_id = f"{int(time.time() * 1000)}_{message.message_id}"

    # Handle voice messages
    if message.voice:
        await handle_voice_message(update, context, msg_id)
        return

    text = message.text
    if not text:
        return

    # Create message file in inbox
    msg_data = {
        "id": msg_id,
        "source": "telegram",
        "chat_id": message.chat_id,
        "user_id": user.id,
        "username": user.username,
        "user_name": user.first_name,
        "text": text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    inbox_file = INBOX_DIR / f"{msg_id}.json"
    with open(inbox_file, 'w') as f:
        json.dump(msg_data, f, indent=2)

    log.info(f"Wrote message to inbox: {msg_id}")

    # Send acknowledgment
    await message.reply_text("📨 Message received. Processing...")


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: str):
    """Handle voice messages: download audio and save to inbox with metadata."""
    user = update.effective_user
    message = update.message
    voice = message.voice

    try:
        # Download voice file from Telegram
        file = await context.bot.get_file(voice.file_id)
        audio_filename = f"{msg_id}.ogg"
        audio_path = AUDIO_DIR / audio_filename

        await file.download_to_drive(audio_path)
        log.info(f"Downloaded voice message to: {audio_path}")

        # Create message file in inbox with voice metadata
        msg_data = {
            "id": msg_id,
            "source": "telegram",
            "type": "voice",
            "chat_id": message.chat_id,
            "user_id": user.id,
            "username": user.username,
            "user_name": user.first_name,
            "text": "[Voice message - pending transcription]",
            "audio_file": str(audio_path),
            "audio_duration": voice.duration,
            "audio_mime_type": voice.mime_type or "audio/ogg",
            "file_id": voice.file_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        inbox_file = INBOX_DIR / f"{msg_id}.json"
        with open(inbox_file, 'w') as f:
            json.dump(msg_data, f, indent=2)

        log.info(f"Wrote voice message to inbox: {msg_id}")
        await message.reply_text("🎤 Voice message received. Transcribing...")

    except Exception as e:
        log.error(f"Error handling voice message: {e}")
        await message.reply_text("❌ Failed to process voice message.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Error: {context.error}", exc_info=context.error)


async def run_bot():
    global bot_app, main_loop

    log.info("Starting Hyperion Bot v2 (file-based)...")
    log.info(f"Inbox: {INBOX_DIR}")
    log.info(f"Outbox: {OUTBOX_DIR}")

    # Store the event loop for the outbox watcher
    main_loop = asyncio.get_running_loop()

    # Set up outbox watcher
    observer = Observer()
    observer.schedule(OutboxHandler(), str(OUTBOX_DIR), recursive=False)
    observer.start()
    log.info("Watching outbox for replies...")

    # Create bot application
    bot_app = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_handler(MessageHandler(filters.VOICE, handle_message))
    bot_app.add_error_handler(error_handler)

    # Initialize and start
    await bot_app.initialize()
    await bot_app.start()
    log.info("Bot is now polling...")

    try:
        await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        observer.stop()
        observer.join()


def main():
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
