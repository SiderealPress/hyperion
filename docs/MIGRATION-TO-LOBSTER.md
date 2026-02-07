# Migration Plan: Hyperion → Lobster

## Overview

This document outlines the careful migration from `hyperion` to `lobster` naming, including directory renames and all system references.

**Critical Risk:** This system is self-modifying. The Claude session running this migration is operating FROM the very directories being renamed. Requires careful orchestration.

---

## Current State

### Directories
- `/home/admin/hyperion/` - Main codebase (now lobster repo)
- `/home/admin/hyperion-workspace/` - Working directory for Claude sessions
- `/home/admin/hyperion-config/` - Configuration backup directory

### Systemd Services
- `hyperion-router.service` - Telegram bot (Python)
- `hyperion-claude.service` - Claude Code tmux session
- `hyperion.target` - Service group target

### Key References
- Systemd service files in `/etc/systemd/system/`
- tmux socket: `-L hyperion`
- tmux session: `-s hyperion`
- MCP server: `mcp__hyperion-inbox__*`
- Environment variables: Various paths
- ~/.claude/settings.local.json - Path references

---

## Migration Strategy

### Phase 1: Preparation (While System Running)
1. Create new service files with lobster names
2. Create migration script
3. Test new paths work
4. Backup current state

### Phase 2: Quick Swap (Brief Downtime)
1. Stop current services
2. Rename directories atomically
3. Symlink old paths → new paths (backwards compat)
4. Reload systemd
5. Start new services

### Phase 3: Cleanup
1. Update all config files
2. Update Claude settings
3. Remove symlinks after testing
4. Update crontab entries

---

## Detailed Steps

### Step 1: Create New Service Files

```bash
# Create lobster-router.service
sudo tee /etc/systemd/system/lobster-router.service << 'EOF'
[Unit]
Description=Lobster Router - Telegram to Claude Code bridge
After=network.target

[Service]
Type=simple
User=admin
Group=admin
WorkingDirectory=/home/admin/lobster
Environment=PATH=/home/admin/.local/bin:/home/admin/.cargo/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/home/admin/lobster/config/config.env
ExecStart=/home/admin/lobster/.venv/bin/python /home/admin/lobster/src/bot/hyperion_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lobster-router
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Create lobster-claude.service
sudo tee /etc/systemd/system/lobster-claude.service << 'EOF'
[Unit]
Description=Lobster Claude - Always-on Claude Code session
After=network.target lobster-router.service
Wants=lobster-router.service

[Service]
Type=forking
User=admin
Group=admin
WorkingDirectory=/home/admin/lobster-workspace
Environment=PATH=/home/admin/.claude/bin:/home/admin/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/admin
ExecStart=/usr/bin/tmux -L lobster new-session -d -s lobster -c /home/admin/lobster-workspace /home/admin/lobster/scripts/claude-wrapper.exp
ExecStop=/usr/bin/tmux -L lobster kill-session -t lobster
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create lobster.target
sudo tee /etc/systemd/system/lobster.target << 'EOF'
[Unit]
Description=Lobster Services
Wants=lobster-router.service lobster-claude.service
After=network.target

[Install]
WantedBy=multi-user.target
EOF
```

### Step 2: Create Migration Script

```bash
#!/bin/bash
# /home/admin/hyperion/scripts/migrate-to-lobster.sh

set -e

echo "🦞 Starting Lobster Migration..."

# Stop old services
echo "Stopping hyperion services..."
sudo systemctl stop hyperion-claude hyperion-router hyperion.target || true

# Wait for processes to die
sleep 5

# Rename directories
echo "Renaming directories..."
mv /home/admin/hyperion /home/admin/lobster
mv /home/admin/hyperion-workspace /home/admin/lobster-workspace
mv /home/admin/hyperion-config /home/admin/lobster-config 2>/dev/null || true

# Create symlinks for backwards compatibility
echo "Creating compatibility symlinks..."
ln -sf /home/admin/lobster /home/admin/hyperion
ln -sf /home/admin/lobster-workspace /home/admin/hyperion-workspace

# Reload systemd
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Enable new services
echo "Enabling lobster services..."
sudo systemctl enable lobster-router lobster-claude lobster.target

# Disable old services (but don't remove yet)
sudo systemctl disable hyperion-router hyperion-claude hyperion.target || true

# Start new services
echo "Starting lobster services..."
sudo systemctl start lobster-router
sleep 5
sudo systemctl start lobster-claude

echo "🦞 Migration complete!"
echo "Verify with: sudo systemctl status lobster-router lobster-claude"
```

### Step 3: Update Claude Settings

After migration, update `/home/admin/.claude/settings.local.json`:
- Replace all `/home/admin/hyperion/` → `/home/admin/lobster/`
- Replace `hyperion-inbox` → `lobster-inbox` in MCP tool names
- Replace tmux references

### Step 4: Update MCP Server Registration

```bash
# Re-register MCP server with new name
claude mcp remove hyperion-inbox
claude mcp add lobster-inbox -s user -- /home/admin/lobster/.venv/bin/python /home/admin/lobster/src/mcp/inbox_server.py
```

### Step 5: Update Crontab

```bash
# Check and update crontab
crontab -l | sed 's/hyperion/lobster/g' | crontab -
```

### Step 6: Update Project Settings

Create new project directory for Claude:
```bash
mkdir -p /home/admin/.claude/projects/-home-admin-lobster-workspace
cp /home/admin/.claude/projects/-home-admin-hyperion-workspace/* \
   /home/admin/.claude/projects/-home-admin-lobster-workspace/
```

---

## Rollback Plan

If migration fails:

```bash
# Stop new services
sudo systemctl stop lobster-claude lobster-router

# Remove symlinks
rm /home/admin/hyperion /home/admin/hyperion-workspace

# Rename back
mv /home/admin/lobster /home/admin/hyperion
mv /home/admin/lobster-workspace /home/admin/hyperion-workspace

# Start old services
sudo systemctl start hyperion-router hyperion-claude
```

---

## Post-Migration Verification

1. Check services: `sudo systemctl status lobster-router lobster-claude`
2. Check tmux: `tmux -L lobster ls`
3. Check MCP: `claude mcp list`
4. Send test Telegram message
5. Verify inbox/outbox functionality

---

## Files to Update After Migration

1. `/home/admin/lobster/scripts/*.sh` - Already updated in code
2. `/home/admin/.claude/settings.local.json` - Path references
3. Crontab entries
4. Any external scripts referencing hyperion paths

---

## Estimated Downtime

- **Service interruption:** 30-60 seconds (directory rename + service restart)
- **Full stabilization:** 2-5 minutes

---

## Recommendation

Execute this migration during low-traffic hours. The migration script should be run manually (not by Claude) to avoid self-interruption issues.

**Alternative:** Have Drew SSH in and run the migration script while Claude session is stopped.
