# Hyperion Hub - Product Requirements Document

## Overview

Hyperion Hub is a secure, self-hosted personal server environment for running Claude Code with integrated messaging capabilities. It provides a hardened Linux server setup optimized for power users who want persistent AI agent sessions with multi-channel communication.

## Problem Statement

Running Claude Code as a persistent agent with messaging integrations requires significant manual configuration: shell environment, terminal multiplexing, MCP servers, security hardening, and credential management. Users need a reproducible, secure setup that "just works."

## Solution

A single setup script that transforms a fresh Debian/Ubuntu server into a fully-configured Claude Code hub with:

- **Messaging integrations** via MCP servers (Telegram, Signal, Twilio SMS)
- **Persistent sessions** via tmux with agent-optimized layouts
- **Power-user shell** via zsh + oh-my-zsh + Powerlevel10k
- **Security hardening** via UFW firewall, fail2ban, and SSH lockdown

## Core Features

| Feature | Description |
|---------|-------------|
| Claude Code | Native binary with MCP server configuration |
| Telegram MCP | Send/receive messages through Telegram API |
| Signal MCP | Encrypted messaging via signal-cli |
| Twilio SMS | Text message integration |
| tmux layouts | Pre-configured agent, dev, and monitor modes |
| zsh environment | Aliases, functions, and productivity plugins |
| Security | Firewall, intrusion prevention, SSH hardening |

## Target Users

- Developers running persistent Claude Code sessions
- Users wanting AI agents with messaging reach-back
- Power users comfortable with terminal-based workflows

## Non-Goals

- GUI/web interface
- Multi-user support
- Container orchestration
- Cloud provider integrations

## Success Metrics

- Setup completes in <10 minutes on fresh server
- Agent sessions persist across SSH disconnects
- MCP servers connect without manual intervention
- Security scans pass basic hardening checks

## Architecture

```
┌─────────────────────────────────────────────┐
│              Hyperion Hub                    │
├─────────────────────────────────────────────┤
│  tmux sessions                              │
│  ├── agent (Claude Code + MCP env)         │
│  ├── dev (Claude + terminal panes)         │
│  └── monitor (htop + logs + status)        │
├─────────────────────────────────────────────┤
│  MCP Servers                                │
│  ├── telegram-mcp (Python/Telethon)        │
│  ├── signal-mcp (signal-cli)               │
│  └── twilio-sms (Node.js)                  │
├─────────────────────────────────────────────┤
│  Security Layer                             │
│  ├── UFW (SSH only by default)             │
│  ├── fail2ban (brute-force prevention)     │
│  └── SSH hardening (no root, key-only)     │
└─────────────────────────────────────────────┘
```

## Quick Start

```bash
# Run setup
bash setup.sh

# Configure credentials
nano ~/mcp-servers/config/.env.master

# Start agent session
agent
```
