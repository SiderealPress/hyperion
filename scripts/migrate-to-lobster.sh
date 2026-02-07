#!/bin/bash
# Lobster Migration Script
# Run as: bash /home/admin/hyperion/scripts/migrate-to-lobster.sh

set -e

echo "🦞 Starting Lobster Migration..."
echo ""

# Step 1: Create new service files
echo "Step 1: Creating lobster service files..."

sudo tee /etc/systemd/system/lobster-router.service > /dev/null << 'EOF'
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

sudo tee /etc/systemd/system/lobster-claude.service > /dev/null << 'EOF'
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

sudo tee /etc/systemd/system/lobster.target > /dev/null << 'EOF'
[Unit]
Description=Lobster Services
Wants=lobster-router.service lobster-claude.service
After=network.target

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Service files created"

# Step 2: Stop old services
echo ""
echo "Step 2: Stopping hyperion services..."
sudo systemctl stop hyperion-claude hyperion-router hyperion.target 2>/dev/null || true
sleep 3

# Kill any remaining tmux sessions
tmux -L hyperion kill-server 2>/dev/null || true
echo "✓ Services stopped"

# Step 3: Rename directories
echo ""
echo "Step 3: Renaming directories..."
if [ -d /home/admin/hyperion ] && [ ! -L /home/admin/hyperion ]; then
    mv /home/admin/hyperion /home/admin/lobster
    echo "✓ hyperion → lobster"
fi

if [ -d /home/admin/hyperion-workspace ] && [ ! -L /home/admin/hyperion-workspace ]; then
    mv /home/admin/hyperion-workspace /home/admin/lobster-workspace
    echo "✓ hyperion-workspace → lobster-workspace"
fi

if [ -d /home/admin/hyperion-config ] && [ ! -L /home/admin/hyperion-config ]; then
    mv /home/admin/hyperion-config /home/admin/lobster-config 2>/dev/null || true
    echo "✓ hyperion-config → lobster-config"
fi

# Step 4: Create symlinks for backwards compatibility
echo ""
echo "Step 4: Creating compatibility symlinks..."
ln -sf /home/admin/lobster /home/admin/hyperion
ln -sf /home/admin/lobster-workspace /home/admin/hyperion-workspace
echo "✓ Symlinks created"

# Step 5: Update Claude project directory
echo ""
echo "Step 5: Updating Claude project settings..."
mkdir -p /home/admin/.claude/projects/-home-admin-lobster-workspace/memory
if [ -d /home/admin/.claude/projects/-home-admin-hyperion-workspace ]; then
    cp -r /home/admin/.claude/projects/-home-admin-hyperion-workspace/* \
          /home/admin/.claude/projects/-home-admin-lobster-workspace/ 2>/dev/null || true
fi
echo "✓ Claude project directory created"

# Step 6: Update settings.local.json
echo ""
echo "Step 6: Updating Claude settings..."
if [ -f /home/admin/.claude/settings.local.json ]; then
    sed -i 's|/home/admin/hyperion/|/home/admin/lobster/|g' /home/admin/.claude/settings.local.json
    sed -i 's|~/hyperion/|~/lobster/|g' /home/admin/.claude/settings.local.json
    sed -i 's|hyperion-inbox|lobster-inbox|g' /home/admin/.claude/settings.local.json
    sed -i 's|tmux -L hyperion|tmux -L lobster|g' /home/admin/.claude/settings.local.json
    sed -i 's|-t hyperion|-t lobster|g' /home/admin/.claude/settings.local.json
    echo "✓ settings.local.json updated"
fi

# Step 7: Update crontab
echo ""
echo "Step 7: Updating crontab..."
crontab -l 2>/dev/null | sed 's|/home/admin/hyperion/|/home/admin/lobster/|g' | sed 's|~/hyperion/|~/lobster/|g' | crontab - 2>/dev/null || true
echo "✓ Crontab updated"

# Step 8: Reload systemd and enable new services
echo ""
echo "Step 8: Configuring systemd..."
sudo systemctl daemon-reload
sudo systemctl disable hyperion-router hyperion-claude hyperion.target 2>/dev/null || true
sudo systemctl enable lobster-router lobster-claude lobster.target
echo "✓ Systemd configured"

# Step 9: Start new services
echo ""
echo "Step 9: Starting lobster services..."
sudo systemctl start lobster-router
sleep 5
sudo systemctl start lobster-claude

echo ""
echo "========================================="
echo "🦞 MIGRATION COMPLETE!"
echo "========================================="
echo ""
echo "Verification commands:"
echo "  sudo systemctl status lobster-router"
echo "  sudo systemctl status lobster-claude"
echo "  tmux -L lobster ls"
echo ""
echo "New paths:"
echo "  /home/admin/lobster/"
echo "  /home/admin/lobster-workspace/"
echo ""
echo "Symlinks (backwards compat):"
echo "  /home/admin/hyperion → /home/admin/lobster"
echo "  /home/admin/hyperion-workspace → /home/admin/lobster-workspace"
echo ""
