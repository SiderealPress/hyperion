#!/usr/bin/env python3
"""
Hyperion Daemon v2 - Persistent Claude Code session

This daemon maintains a persistent Claude Code session that:
- Has full context about the Hyperion system
- Remembers conversation history across restarts
- Processes messages from all channels
- Uses a fixed session ID for continuity
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
SESSION_FILE = WORKSPACE / ".hyperion_session"
LOG_DIR = WORKSPACE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "daemon.log"

POLL_INTERVAL = 5  # seconds between checks
IDLE_POLL_INTERVAL = 10  # seconds when no messages
CLAUDE_TIMEOUT = 300  # 5 minutes max per invocation

# Fixed session ID for persistence (deterministic UUID)
HYPERION_SESSION_ID = "a1b2c3d4-5678-90ab-cdef-hyperion0001"

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


def get_session_id() -> str:
    """Get or create the persistent session ID."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()

    # Generate a deterministic session ID
    session_id = str(uuid.uuid5(
        uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"),
        f"hyperion-daemon-{os.uname().nodename}"
    ))
    SESSION_FILE.write_text(session_id)
    return session_id


def count_inbox_messages() -> int:
    """Count messages in inbox."""
    return len(list(INBOX_DIR.glob("*.json")))


def is_first_run() -> bool:
    """Check if this is the first run (no session file)."""
    return not SESSION_FILE.exists()


async def initialize_session(session_id: str) -> bool:
    """
    Initialize the Hyperion session with full context.
    Called on first run to establish the persistent session.
    """
    log.info("Initializing Hyperion session...")

    init_prompt = """You are now initializing as Hyperion.

Read the CLAUDE.md file in your workspace to understand your role and capabilities.

After reading, confirm you understand:
1. Your role as an always-on message processor
2. How to use the inbox MCP tools
3. The message flow from Telegram to you and back

Then check your inbox for any pending messages and process them.

Say "Hyperion initialized and ready" when done."""

    cmd = [
        "claude",
        "-p", init_prompt,
        "--print",
        "--session-id", session_id,
        "--allowedTools", ",".join([
            "mcp__hyperion-inbox__check_inbox",
            "mcp__hyperion-inbox__send_reply",
            "mcp__hyperion-inbox__mark_processed",
            "mcp__hyperion-inbox__get_stats",
            "mcp__hyperion-inbox__list_sources",
            "Read",
            "Glob",
            "Grep",
        ]),
    ]

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
        log.info(f"Initialization output: {output[:500]}")

        return proc.returncode == 0

    except Exception as e:
        log.exception(f"Initialization failed: {e}")
        return False


async def process_messages(session_id: str) -> tuple[bool, str]:
    """
    Invoke Claude to process inbox messages.
    Uses --continue to maintain conversation history.
    """
    prompt = """Check your inbox for new messages. For each message:
1. Read and understand what the user wants
2. Compose a helpful, concise response
3. Use send_reply with the correct chat_id
4. Use mark_processed to clear the message

Process ALL messages in the inbox."""

    cmd = [
        "claude",
        "-p", prompt,
        "--print",
        "--session-id", session_id,
        "--allowedTools", ",".join([
            "mcp__hyperion-inbox__check_inbox",
            "mcp__hyperion-inbox__send_reply",
            "mcp__hyperion-inbox__mark_processed",
            "mcp__hyperion-inbox__get_stats",
            "Read",
            "Write",
            "Bash",
        ]),
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
    log.info("Hyperion Daemon v2 starting...")
    log.info(f"Workspace: {WORKSPACE}")
    log.info(f"Inbox: {INBOX_DIR}")
    log.info("=" * 60)

    # Ensure directories exist
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Get or create session ID
    first_run = is_first_run()
    session_id = get_session_id()
    log.info(f"Session ID: {session_id}")
    log.info(f"First run: {first_run}")

    # Initialize on first run
    if first_run:
        success = await initialize_session(session_id)
        if not success:
            log.error("Failed to initialize session. Retrying in 30s...")
            await asyncio.sleep(30)
            # Try once more
            success = await initialize_session(session_id)
            if not success:
                log.error("Initialization failed twice. Starting anyway...")

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
