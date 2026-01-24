# Hyperion

Always-on Claude Code message processor with Telegram integration.

## One-Line Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/SiderealPress/hyperion/main/install.sh)
```

## Overview

Hyperion transforms a server into an always-on Claude Code hub that:

- **Processes messages 24/7** via Telegram (SMS/Signal planned)
- **Maintains persistent context** across restarts
- **Auto-restarts on failure** via systemd
- **Provides unified CLI** for management

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    HYPERION DAEMON                          │
│         (Always-on Claude Code with Max subscription)       │
│                                                             │
│   MCP Server: hyperion-inbox                                │
│   - Message queue management                                │
│   - Task tracking                                           │
└─────────────────────────────────────────────────────────────┘
                              ↑↓
               ~/messages/inbox/ ←→ ~/messages/outbox/
                              ↑↓
┌─────────────────────────────────────────────────────────────┐
│              TELEGRAM BOT                                   │
│   Writes incoming messages to inbox                         │
│   Watches outbox and sends replies                          │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Debian 12+ or Ubuntu 22.04+
- Claude Code authenticated (Max subscription)
- Telegram bot token (from @BotFather)
- Your Telegram user ID (from @userinfobot)

## Manual Install

```bash
git clone https://github.com/SiderealPress/hyperion.git
cd hyperion
bash install.sh
```

## CLI Commands

```bash
hyperion start      # Start all services
hyperion stop       # Stop all services
hyperion restart    # Restart services
hyperion status     # Show status
hyperion logs       # Show logs (follow mode)
hyperion inbox      # Check pending messages
hyperion outbox     # Check pending replies
hyperion stats      # Show statistics
hyperion test       # Create test message
hyperion help       # Show help
```

## Directory Structure

```
~/hyperion/                    # Repository
├── src/
│   ├── bot/hyperion_bot.py    # Telegram bot
│   ├── daemon/daemon.py       # Claude daemon
│   ├── mcp/inbox_server.py    # MCP server
│   └── cli                    # CLI tool
├── services/                  # systemd units
├── config/                    # Configuration
└── install.sh                 # Bootstrap installer

~/messages/                    # Runtime data
├── inbox/                     # Incoming messages
├── outbox/                    # Outgoing replies
└── processed/                 # Archive

~/hyperion-workspace/          # Claude workspace
├── CLAUDE.md                  # System context
└── logs/                      # Log files
```

## MCP Tools

The hyperion-inbox MCP server provides:

### Message Queue
- `check_inbox(source?, limit?)` - Get new messages
- `send_reply(chat_id, text, source?)` - Send a reply
- `mark_processed(message_id)` - Mark message handled
- `list_sources()` - List available channels
- `get_stats()` - Inbox statistics

### Task Management
- `list_tasks(status?)` - List all tasks
- `create_task(subject, description?)` - Create task
- `update_task(task_id, status?, ...)` - Update task
- `get_task(task_id)` - Get task details
- `delete_task(task_id)` - Delete task

## Services

| Service | Description |
|---------|-------------|
| `hyperion-router` | Telegram bot |
| `hyperion-daemon` | Claude Code processor |

Manual control:
```bash
sudo systemctl status hyperion-router
sudo journalctl -u hyperion-router -f
```

## Security

- Bot restricted to allowed user IDs only
- Credentials stored in config.env (gitignored)
- No hardcoded secrets in code

## License

MIT
