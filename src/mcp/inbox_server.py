#!/usr/bin/env python3
"""
Hyperion Inbox MCP Server

Provides tools for Claude Code to interact with the message queue:
- check_inbox: Get new messages from all sources
- send_reply: Send a reply back to the original source
- list_sources: List available message sources
- get_message: Get a specific message by ID
- mark_processed: Mark a message as processed
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Directories
BASE_DIR = Path.home() / "messages"
INBOX_DIR = BASE_DIR / "inbox"
OUTBOX_DIR = BASE_DIR / "outbox"
PROCESSED_DIR = BASE_DIR / "processed"
CONFIG_DIR = BASE_DIR / "config"
TASKS_FILE = BASE_DIR / "tasks.json"

# Ensure directories exist
for d in [INBOX_DIR, OUTBOX_DIR, PROCESSED_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Initialize tasks file if needed
if not TASKS_FILE.exists():
    TASKS_FILE.write_text(json.dumps({"tasks": [], "next_id": 1}, indent=2))

# Source configurations
SOURCES = {
    "telegram": {
        "name": "Telegram",
        "enabled": True,
    },
}

server = Server("hyperion-inbox")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="check_inbox",
            description="Check for new messages in the inbox from all sources (Telegram, SMS, Signal, etc.). Returns unprocessed messages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Filter by source (telegram, sms, signal). Leave empty for all sources.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to return. Default 10.",
                        "default": 10,
                    },
                },
            },
        ),
        Tool(
            name="send_reply",
            description="Send a reply to a message. The reply will be routed back to the original source (Telegram, SMS, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "integer",
                        "description": "The chat ID to reply to (from the original message).",
                    },
                    "text": {
                        "type": "string",
                        "description": "The reply text to send.",
                    },
                    "source": {
                        "type": "string",
                        "description": "The source to reply via (telegram, sms, signal). Default: telegram.",
                        "default": "telegram",
                    },
                },
                "required": ["chat_id", "text"],
            },
        ),
        Tool(
            name="mark_processed",
            description="Mark a message as processed and move it out of the inbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The message ID to mark as processed.",
                    },
                },
                "required": ["message_id"],
            },
        ),
        Tool(
            name="list_sources",
            description="List all available message sources and their status.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_stats",
            description="Get inbox statistics: message counts, sources, etc.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # Task Management Tools
        Tool(
            name="list_tasks",
            description="List all tasks with their status. Tasks are shared across all Hyperion sessions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: pending, in_progress, completed, or all (default).",
                        "default": "all",
                    },
                },
            },
        ),
        Tool(
            name="create_task",
            description="Create a new task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Brief title for the task.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of what needs to be done.",
                    },
                },
                "required": ["subject"],
            },
        ),
        Tool(
            name="update_task",
            description="Update a task's status or details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The task ID to update.",
                    },
                    "status": {
                        "type": "string",
                        "description": "New status: pending, in_progress, or completed.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "New subject (optional).",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description (optional).",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_task",
            description="Get details of a specific task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The task ID to retrieve.",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="delete_task",
            description="Delete a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The task ID to delete.",
                    },
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if name == "check_inbox":
        return await handle_check_inbox(arguments)
    elif name == "send_reply":
        return await handle_send_reply(arguments)
    elif name == "mark_processed":
        return await handle_mark_processed(arguments)
    elif name == "list_sources":
        return await handle_list_sources(arguments)
    elif name == "get_stats":
        return await handle_get_stats(arguments)
    elif name == "list_tasks":
        return await handle_list_tasks(arguments)
    elif name == "create_task":
        return await handle_create_task(arguments)
    elif name == "update_task":
        return await handle_update_task(arguments)
    elif name == "get_task":
        return await handle_get_task(arguments)
    elif name == "delete_task":
        return await handle_delete_task(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_check_inbox(args: dict) -> list[TextContent]:
    """Check for new messages in inbox."""
    source_filter = args.get("source", "").lower()
    limit = args.get("limit", 10)

    messages = []
    for f in sorted(INBOX_DIR.glob("*.json")):
        try:
            with open(f) as fp:
                msg = json.load(fp)
                if source_filter and msg.get("source", "").lower() != source_filter:
                    continue
                msg["_filename"] = f.name
                messages.append(msg)
                if len(messages) >= limit:
                    break
        except Exception as e:
            continue

    if not messages:
        return [TextContent(type="text", text="📭 No new messages in inbox.")]

    # Format messages nicely
    output = f"📬 **{len(messages)} new message(s):**\n\n"
    for msg in messages:
        source = msg.get("source", "unknown").upper()
        user = msg.get("user_name", msg.get("username", "Unknown"))
        text = msg.get("text", "(no text)")
        ts = msg.get("timestamp", "")
        msg_id = msg.get("id", msg.get("_filename", ""))
        chat_id = msg.get("chat_id", "")

        output += f"---\n"
        output += f"**[{source}]** from **{user}**\n"
        output += f"Chat ID: `{chat_id}` | Message ID: `{msg_id}`\n"
        output += f"Time: {ts}\n\n"
        output += f"> {text}\n\n"

    output += "---\n"
    output += "Use `send_reply` to respond, `mark_processed` when done."

    return [TextContent(type="text", text=output)]


async def handle_send_reply(args: dict) -> list[TextContent]:
    """Send a reply to a message."""
    chat_id = args.get("chat_id")
    text = args.get("text", "")
    source = args.get("source", "telegram").lower()

    if not chat_id or not text:
        return [TextContent(type="text", text="Error: chat_id and text are required.")]

    # Create reply file in outbox
    reply_id = f"{int(time.time() * 1000)}_{source}"
    reply_data = {
        "id": reply_id,
        "source": source,
        "chat_id": chat_id,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    outbox_file = OUTBOX_DIR / f"{reply_id}.json"
    with open(outbox_file, "w") as f:
        json.dump(reply_data, f, indent=2)

    return [TextContent(type="text", text=f"✅ Reply queued for {source} (chat {chat_id}):\n\n{text[:100]}{'...' if len(text) > 100 else ''}")]


async def handle_mark_processed(args: dict) -> list[TextContent]:
    """Mark a message as processed."""
    message_id = args.get("message_id", "")

    if not message_id:
        return [TextContent(type="text", text="Error: message_id is required.")]

    # Find the message file
    found = None
    for f in INBOX_DIR.glob("*.json"):
        if message_id in f.name:
            found = f
            break
        try:
            with open(f) as fp:
                msg = json.load(fp)
                if msg.get("id") == message_id:
                    found = f
                    break
        except:
            continue

    if not found:
        return [TextContent(type="text", text=f"Message not found: {message_id}")]

    # Move to processed
    dest = PROCESSED_DIR / found.name
    found.rename(dest)

    return [TextContent(type="text", text=f"✅ Message marked as processed: {message_id}")]


async def handle_list_sources(args: dict) -> list[TextContent]:
    """List available message sources."""
    output = "📡 **Message Sources:**\n\n"
    for key, source in SOURCES.items():
        status = "✅ Enabled" if source["enabled"] else "❌ Disabled"
        output += f"- **{source['name']}** ({key}): {status}\n"

    return [TextContent(type="text", text=output)]


async def handle_get_stats(args: dict) -> list[TextContent]:
    """Get inbox statistics."""
    inbox_count = len(list(INBOX_DIR.glob("*.json")))
    outbox_count = len(list(OUTBOX_DIR.glob("*.json")))
    processed_count = len(list(PROCESSED_DIR.glob("*.json")))

    # Count by source
    source_counts = {}
    for f in INBOX_DIR.glob("*.json"):
        try:
            with open(f) as fp:
                msg = json.load(fp)
                src = msg.get("source", "unknown")
                source_counts[src] = source_counts.get(src, 0) + 1
        except:
            continue

    output = "📊 **Inbox Statistics:**\n\n"
    output += f"- Inbox: {inbox_count} messages\n"
    output += f"- Outbox: {outbox_count} pending replies\n"
    output += f"- Processed: {processed_count} total\n\n"

    if source_counts:
        output += "**By Source:**\n"
        for src, count in source_counts.items():
            output += f"- {src}: {count}\n"

    return [TextContent(type="text", text=output)]


# =============================================================================
# Task Management Handlers
# =============================================================================

def load_tasks() -> dict:
    """Load tasks from file."""
    try:
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    except:
        return {"tasks": [], "next_id": 1}


def save_tasks(data: dict) -> None:
    """Save tasks to file."""
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def handle_list_tasks(args: dict) -> list[TextContent]:
    """List all tasks."""
    status_filter = args.get("status", "all").lower()
    data = load_tasks()
    tasks = data.get("tasks", [])

    if status_filter != "all":
        tasks = [t for t in tasks if t.get("status", "").lower() == status_filter]

    if not tasks:
        return [TextContent(type="text", text="📋 No tasks found.")]

    # Group by status
    pending = [t for t in tasks if t.get("status") == "pending"]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    completed = [t for t in tasks if t.get("status") == "completed"]

    output = "📋 **Tasks:**\n\n"

    if in_progress:
        output += "**🔄 In Progress:**\n"
        for t in in_progress:
            output += f"  #{t['id']} {t['subject']}\n"
        output += "\n"

    if pending:
        output += "**⏳ Pending:**\n"
        for t in pending:
            output += f"  #{t['id']} {t['subject']}\n"
        output += "\n"

    if completed:
        output += "**✅ Completed:**\n"
        for t in completed:
            output += f"  #{t['id']} {t['subject']}\n"
        output += "\n"

    output += f"---\nTotal: {len(tasks)} task(s)"

    return [TextContent(type="text", text=output)]


async def handle_create_task(args: dict) -> list[TextContent]:
    """Create a new task."""
    subject = args.get("subject", "").strip()
    description = args.get("description", "").strip()

    if not subject:
        return [TextContent(type="text", text="Error: subject is required.")]

    data = load_tasks()
    task_id = data.get("next_id", 1)

    task = {
        "id": task_id,
        "subject": subject,
        "description": description,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    data["tasks"].append(task)
    data["next_id"] = task_id + 1
    save_tasks(data)

    return [TextContent(type="text", text=f"✅ Task #{task_id} created: {subject}")]


async def handle_update_task(args: dict) -> list[TextContent]:
    """Update a task."""
    task_id = args.get("task_id")
    if task_id is None:
        return [TextContent(type="text", text="Error: task_id is required.")]

    data = load_tasks()
    task = None
    for t in data["tasks"]:
        if t["id"] == task_id:
            task = t
            break

    if not task:
        return [TextContent(type="text", text=f"Error: Task #{task_id} not found.")]

    # Update fields
    if "status" in args:
        status = args["status"].lower()
        if status in ["pending", "in_progress", "completed"]:
            task["status"] = status
        else:
            return [TextContent(type="text", text=f"Error: Invalid status '{status}'. Use: pending, in_progress, completed")]

    if "subject" in args:
        task["subject"] = args["subject"]

    if "description" in args:
        task["description"] = args["description"]

    task["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_tasks(data)

    status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(task["status"], "")
    return [TextContent(type="text", text=f"{status_emoji} Task #{task_id} updated: {task['subject']} [{task['status']}]")]


async def handle_get_task(args: dict) -> list[TextContent]:
    """Get task details."""
    task_id = args.get("task_id")
    if task_id is None:
        return [TextContent(type="text", text="Error: task_id is required.")]

    data = load_tasks()
    task = None
    for t in data["tasks"]:
        if t["id"] == task_id:
            task = t
            break

    if not task:
        return [TextContent(type="text", text=f"Error: Task #{task_id} not found.")]

    status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(task["status"], "")

    output = f"📋 **Task #{task['id']}**\n\n"
    output += f"**Subject:** {task['subject']}\n"
    output += f"**Status:** {status_emoji} {task['status']}\n"
    if task.get("description"):
        output += f"\n**Description:**\n{task['description']}\n"
    output += f"\n**Created:** {task.get('created_at', 'N/A')}\n"
    output += f"**Updated:** {task.get('updated_at', 'N/A')}\n"

    return [TextContent(type="text", text=output)]


async def handle_delete_task(args: dict) -> list[TextContent]:
    """Delete a task."""
    task_id = args.get("task_id")
    if task_id is None:
        return [TextContent(type="text", text="Error: task_id is required.")]

    data = load_tasks()
    original_len = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

    if len(data["tasks"]) == original_len:
        return [TextContent(type="text", text=f"Error: Task #{task_id} not found.")]

    save_tasks(data)
    return [TextContent(type="text", text=f"🗑️ Task #{task_id} deleted.")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
