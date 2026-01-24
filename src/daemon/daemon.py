#!/usr/bin/env python3
"""
Hyperion Daemon - Always-on Claude Code message processor

This daemon monitors the inbox and invokes Claude to process messages.
Creates its own session ID on first startup for persistent context.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Configuration
INBOX_DIR = Path.home() / "messages" / "inbox"
WORKSPACE = Path.home() / "hyperion-workspace"
SESSION_FILE = WORKSPACE / ".hyperion_session_id"
LOG_DIR = WORKSPACE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "daemon.log"

POLL_INTERVAL = 5  # seconds between checks
IDLE_POLL_INTERVAL = 10  # seconds when no messages
CLAUDE_TIMEOUT = 300  # 5 minutes max per invocation

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("hyperion")


def get_or_create_session_id() -> str:
    """Get existing session ID or create a new one on first startup."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()

    # Generate a new unique session ID
    session_id = f"hyperion-{uuid.uuid4().hex[:8]}"
    SESSION_FILE.write_text(session_id)
    log.info(f"Created new session ID: {session_id}")
    return session_id


def count_inbox_messages() -> int:
    """Count messages in inbox."""
    return len(list(INBOX_DIR.glob("*.json")))


def get_inbox_messages() -> list[dict]:
    """Read all messages from inbox."""
    messages = []
    for f in sorted(INBOX_DIR.glob("*.json")):
        try:
            messages.append(json.loads(f.read_text()))
        except Exception as e:
            log.warning(f"Failed to read {f}: {e}")
    return messages


async def process_messages(session_id: str) -> tuple[bool, str]:
    """
    Invoke Claude to process inbox messages.
    Uses a persistent session ID for shared context across invocations.
    """
    prompt = """You are Hyperion. Check your inbox and process all messages.

For each message:
1. Use check_inbox to see the messages
2. Read and understand what the user wants
3. Compose a helpful, concise response (users are on mobile)
4. Use send_reply with the correct chat_id
5. Use mark_processed to clear the message

Process ALL messages in the inbox."""

    cmd = [
        "claude",
        "-p", prompt,
        "--print",
        "--dangerously-skip-permissions",
        "--session-id", session_id,
    ]

    log.info("Invoking Claude to process messages...")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=WORKSPACE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=CLAUDE_TIMEOUT
        )

        output = stdout.decode().strip()
        errors = stderr.decode().strip()

        if proc.returncode != 0:
            log.error(f"Claude error (code {proc.returncode}): {errors}")
            return False, errors

        log.info(f"Claude completed: {output[:200]}...")
        return True, output

    except asyncio.TimeoutError:
        log.error(f"Claude timed out after {CLAUDE_TIMEOUT}s")
        try:
            proc.kill()
        except:
            pass
        return False, "Timeout"

    except Exception as e:
        log.exception(f"Error invoking Claude: {e}")
        return False, str(e)


async def daemon_loop():
    """Main daemon loop."""
    log.info("=" * 60)
    log.info("Hyperion Daemon starting...")
    log.info(f"Workspace: {WORKSPACE}")
    log.info(f"Inbox: {INBOX_DIR}")
    log.info("=" * 60)

    # Ensure directories exist
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Get or create session ID
    session_id = get_or_create_session_id()
    log.info(f"Session ID: {session_id}")

    consecutive_errors = 0
    max_errors = 5

    while True:
        loop_start = time.time()

        try:
            msg_count = count_inbox_messages()

            if msg_count > 0:
                log.info(f"📬 {msg_count} message(s) in inbox")

                success, output = await process_messages(session_id)

                if success:
                    consecutive_errors = 0
                    remaining = count_inbox_messages()
                    processed = msg_count - remaining
                    log.info(f"✅ Processed {processed}, {remaining} remaining")
                else:
                    consecutive_errors += 1
                    log.warning(f"⚠️ Failed ({consecutive_errors}/{max_errors})")

                    if consecutive_errors >= max_errors:
                        log.error("Too many errors. Sleeping 60s...")
                        await asyncio.sleep(60)
                        consecutive_errors = 0

                poll = POLL_INTERVAL
            else:
                poll = IDLE_POLL_INTERVAL

        except Exception as e:
            log.exception(f"Loop error: {e}")
            consecutive_errors += 1
            poll = POLL_INTERVAL

        elapsed = time.time() - loop_start
        sleep_time = max(poll - elapsed, 1)
        await asyncio.sleep(sleep_time)


def main():
    """Entry point."""
    try:
        asyncio.run(daemon_loop())
    except KeyboardInterrupt:
        log.info("Daemon stopped by user")
    except Exception as e:
        log.exception(f"Daemon crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
