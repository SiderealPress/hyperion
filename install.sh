#!/bin/bash
#===============================================================================
# Hyperion Bootstrap Installer
#
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/SiderealPress/hyperion/main/install.sh)
#
# This script sets up a complete Hyperion installation on a fresh VM:
# - Installs system dependencies
# - Clones the repo (if needed)
# - Walks through configuration
# - Sets up Python environment
# - Registers MCP servers with Claude
# - Installs and starts systemd services
#===============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Logging functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step() { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }

# Configuration
REPO_URL="https://github.com/SiderealPress/hyperion.git"
INSTALL_DIR="$HOME/hyperion"
WORKSPACE_DIR="$HOME/hyperion-workspace"
MESSAGES_DIR="$HOME/messages"

#===============================================================================
# Banner
#===============================================================================

echo -e "${BLUE}"
cat << 'BANNER'
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ██╗  ██╗██╗   ██╗██████╗ ███████╗██████╗ ██╗ ██████╗ ███╗   ██╗  ║
║   ██║  ██║╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██║██╔═══██╗████╗  ██║  ║
║   ███████║ ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║██║   ██║██╔██╗ ██║  ║
║   ██╔══██║  ╚██╔╝  ██╔═══╝ ██╔══╝  ██╔══██╗██║██║   ██║██║╚██╗██║  ║
║   ██║  ██║   ██║   ██║     ███████╗██║  ██║██║╚██████╔╝██║ ╚████║  ║
║   ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝  ║
║                                                               ║
║         Always-on Claude Code Message Processor               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
BANNER
echo -e "${NC}"

#===============================================================================
# Pre-flight Checks
#===============================================================================

step "Running pre-flight checks..."

# Check OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        warn "This script is designed for Ubuntu/Debian. Detected: $ID"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
    fi
else
    warn "Cannot detect OS. Proceeding anyway..."
fi

# Check if running interactively
if [ ! -t 0 ]; then
    error "This script requires interactive input."
    echo ""
    echo "Please run it like this instead:"
    echo -e "  ${CYAN}bash <(curl -fsSL https://raw.githubusercontent.com/SiderealPress/hyperion/main/install.sh)${NC}"
    echo ""
    echo "Or download and run:"
    echo -e "  ${CYAN}curl -fsSL https://raw.githubusercontent.com/SiderealPress/hyperion/main/install.sh -o install.sh${NC}"
    echo -e "  ${CYAN}bash install.sh${NC}"
    exit 1
fi

# Check sudo
if ! sudo true 2>/dev/null; then
    error "This script requires sudo access"
    exit 1
fi
success "Sudo access confirmed"

# Check internet
if ! curl -s --connect-timeout 5 https://api.github.com >/dev/null; then
    error "No internet connection"
    exit 1
fi
success "Internet connectivity confirmed"

# Check Python
if ! command -v python3 &>/dev/null; then
    warn "Python3 not found. Will install."
    NEED_PYTHON=true
else
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ $(echo "$PYTHON_VERSION < 3.9" | bc -l 2>/dev/null || echo "0") == "1" ]]; then
        warn "Python $PYTHON_VERSION found, but 3.9+ recommended"
    else
        success "Python $PYTHON_VERSION found"
    fi
fi

# Check Claude Code
if command -v claude &>/dev/null; then
    success "Claude Code found"
    CLAUDE_INSTALLED=true
else
    warn "Claude Code not found. Will install."
    CLAUDE_INSTALLED=false
fi

#===============================================================================
# Install System Dependencies
#===============================================================================

step "Installing system dependencies..."

sudo apt-get update -qq

# Essential packages
PACKAGES=(
    curl
    wget
    git
    jq
    python3
    python3-pip
    python3-venv
    cron
    expect
    tmux
)

for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        info "Installing $pkg..."
        sudo apt-get install -y -qq "$pkg"
    fi
done

success "System dependencies installed"

#===============================================================================
# Install Claude Code
#===============================================================================

if [ "$CLAUDE_INSTALLED" = false ]; then
    step "Installing Claude Code..."

    curl -fsSL https://claude.ai/install.sh | sh

    # Add to PATH for current session
    export PATH="$HOME/.claude/bin:$PATH"

    if command -v claude &>/dev/null; then
        success "Claude Code installed"
    else
        error "Claude Code installation failed"
        exit 1
    fi
fi

# Check authentication
step "Checking Claude Code authentication..."

if ! claude auth status &>/dev/null 2>&1; then
    echo ""
    warn "Claude Code is not authenticated."
    echo ""
    echo "You need to authenticate with your Anthropic account."
    echo "This will open a browser or provide a URL to complete authentication."
    echo ""
    read -p "Press Enter to start authentication..."
    echo ""

    # Run auth login interactively
    if claude auth login; then
        success "Claude Code authenticated"
    else
        error "Authentication failed. Please try again."
        echo ""
        echo "You can manually authenticate by running:"
        echo -e "  ${CYAN}claude auth login${NC}"
        echo ""
        echo "Then re-run this installer."
        exit 1
    fi
else
    success "Claude Code already authenticated"
fi

#===============================================================================
# Clone Repository
#===============================================================================

step "Setting up Hyperion repository..."

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repository exists. Updating..."
    cd "$INSTALL_DIR"
    git pull --quiet
else
    info "Cloning repository..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

success "Repository ready at $INSTALL_DIR"

#===============================================================================
# Create Directories
#===============================================================================

step "Creating directories..."

mkdir -p "$WORKSPACE_DIR/logs"
mkdir -p "$MESSAGES_DIR"/{inbox,outbox,processed,config,audio,task-outputs}
mkdir -p "$INSTALL_DIR/scheduled-tasks"/{tasks,logs}
mkdir -p "$HOME/projects"/{personal,business}

success "Directories created"
info "  ~/projects/personal - Personal projects"
info "  ~/projects/business - Business/work projects"

#===============================================================================
# Scheduled Tasks Setup
#===============================================================================

step "Setting up scheduled tasks infrastructure..."

# Create jobs.json if it doesn't exist
JOBS_FILE="$INSTALL_DIR/scheduled-tasks/jobs.json"
if [ ! -f "$JOBS_FILE" ]; then
    echo '{"jobs": {}}' > "$JOBS_FILE"
fi

# Create run-job.sh
cat > "$INSTALL_DIR/scheduled-tasks/run-job.sh" << 'RUNJOB'
#!/bin/bash
# Hyperion Scheduled Task Executor
# Runs a scheduled job in a fresh Claude instance

set -e

# Ensure Claude is in PATH (cron doesn't inherit user PATH)
export PATH="$HOME/.claude/bin:$HOME/.local/bin:$PATH"

JOB_NAME="$1"

if [ -z "$JOB_NAME" ]; then
    echo "Usage: $0 <job-name>"
    exit 1
fi

JOBS_DIR="$HOME/hyperion/scheduled-tasks"
TASK_FILE="$JOBS_DIR/tasks/${JOB_NAME}.md"
OUTPUT_DIR="$HOME/messages/task-outputs"
LOG_DIR="$JOBS_DIR/logs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
JOBS_FILE="$JOBS_DIR/jobs.json"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

if [ ! -f "$TASK_FILE" ]; then
    echo "Error: Task file not found: $TASK_FILE"
    exit 1
fi

TASK_CONTENT=$(cat "$TASK_FILE")
LOG_FILE="$LOG_DIR/${JOB_NAME}-${TIMESTAMP}.log"

START_TIME=$(date +%s)
START_ISO=$(date -Iseconds)

echo "[$START_ISO] Starting job: $JOB_NAME" | tee "$LOG_FILE"

claude -p "$TASK_CONTENT

---

IMPORTANT: You are running as a scheduled task. When you complete your task:
1. Call write_task_output() with your results summary
2. Keep output concise - the main Hyperion instance will review this later
3. Exit after writing output - do not start a loop" \
    --dangerously-skip-permissions \
    --max-turns 15 \
    2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?

END_TIME=$(date +%s)
END_ISO=$(date -Iseconds)
DURATION=$((END_TIME - START_TIME))

echo "" | tee -a "$LOG_FILE"
echo "[$END_ISO] Job completed in ${DURATION}s with exit code: $EXIT_CODE" | tee -a "$LOG_FILE"

if [ -f "$JOBS_FILE" ]; then
    if command -v jq &> /dev/null; then
        STATUS="success"
        [ $EXIT_CODE -ne 0 ] && STATUS="failed"
        TMP_FILE=$(mktemp)
        jq --arg name "$JOB_NAME" \
           --arg last_run "$END_ISO" \
           --arg status "$STATUS" \
           '.jobs[$name].last_run = $last_run | .jobs[$name].last_status = $status' \
           "$JOBS_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$JOBS_FILE"
    fi
fi

exit $EXIT_CODE
RUNJOB
chmod +x "$INSTALL_DIR/scheduled-tasks/run-job.sh"

# Create sync-crontab.sh
cat > "$INSTALL_DIR/scheduled-tasks/sync-crontab.sh" << 'SYNCCRON'
#!/bin/bash
# Hyperion Crontab Synchronizer

set -e

JOBS_FILE="$HOME/hyperion/scheduled-tasks/jobs.json"
RUNNER="$HOME/hyperion/scheduled-tasks/run-job.sh"

if ! command -v crontab &> /dev/null; then
    echo "Warning: crontab not found. Install cron to enable scheduled tasks."
    exit 0
fi

if [ ! -f "$JOBS_FILE" ]; then
    echo "Error: Jobs file not found: $JOBS_FILE"
    exit 1
fi

MARKER="# HYPERION-SCHEDULED"
EXISTING=$(crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "$RUNNER" || true)

if command -v jq &> /dev/null; then
    CRON_ENTRIES=$(jq -r --arg runner "$RUNNER" --arg marker "$MARKER" '
        .jobs | to_entries[] |
        select(.value.enabled == true) |
        "\(.value.schedule) \($runner) \(.key) \($marker)"
    ' "$JOBS_FILE" 2>/dev/null || echo "")
else
    CRON_ENTRIES=""
fi

{
    if [ -n "$EXISTING" ]; then
        echo "$EXISTING"
    fi
    if [ -n "$CRON_ENTRIES" ]; then
        echo "$CRON_ENTRIES"
    fi
} | crontab -

echo "Crontab synchronized:"
crontab -l 2>/dev/null | grep "$MARKER" || echo "(no hyperion jobs)"
SYNCCRON
chmod +x "$INSTALL_DIR/scheduled-tasks/sync-crontab.sh"

# Enable cron service
sudo systemctl enable cron 2>/dev/null || true
sudo systemctl start cron 2>/dev/null || true

success "Scheduled tasks infrastructure ready"

#===============================================================================
# Python Environment
#===============================================================================

step "Setting up Python environment..."

cd "$INSTALL_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet mcp python-telegram-bot watchdog python-dotenv
deactivate

success "Python environment ready"

#===============================================================================
# Configuration
#===============================================================================

step "Configuring Hyperion..."

CONFIG_FILE="$INSTALL_DIR/config/config.env"
CONFIG_EXAMPLE="$INSTALL_DIR/config/config.env.example"

# Check if already configured
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ "$TELEGRAM_BOT_TOKEN" != "your_bot_token_here" ]; then
        info "Existing configuration found"
        echo ""
        echo "Current config:"
        echo "  Bot Token: ${TELEGRAM_BOT_TOKEN:0:10}...${TELEGRAM_BOT_TOKEN: -5}"
        echo "  Allowed Users: $TELEGRAM_ALLOWED_USERS"
        echo ""
        read -p "Keep existing configuration? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            NEED_CONFIG=true
        else
            NEED_CONFIG=false
        fi
    else
        NEED_CONFIG=true
    fi
else
    NEED_CONFIG=true
fi

if [ "$NEED_CONFIG" = true ]; then
    echo ""
    echo -e "${BOLD}Telegram Bot Setup${NC}"
    echo ""
    echo "You need a Telegram bot token and your user ID."
    echo ""
    echo "To get a bot token:"
    echo "  1. Open Telegram and message @BotFather"
    echo "  2. Send /newbot and follow the prompts"
    echo "  3. Copy the token (looks like: 123456789:ABCdefGHI...)"
    echo ""
    echo "To get your numeric user ID (NOT your @username):"
    echo "  1. Message @userinfobot on Telegram"
    echo "  2. It will reply with your numeric ID (e.g. 123456789)"
    echo ""
    echo -e "  ${YELLOW}Important: Your user ID is a number like 123456789${NC}"
    echo -e "  ${YELLOW}           It is NOT your @username${NC}"
    echo ""

    # Get bot token
    while true; do
        read -p "Enter your Telegram bot token: " BOT_TOKEN
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
            break
        else
            warn "Invalid token format. Should be like: 123456789:ABCdefGHI..."
        fi
    done

    # Get user ID
    while true; do
        read -p "Enter your Telegram numeric user ID: " USER_ID
        if [[ "$USER_ID" =~ ^[0-9]+$ ]]; then
            break
        elif [[ "$USER_ID" =~ ^@ ]]; then
            warn "That's your @username. You need your numeric ID."
            echo "    Message @userinfobot on Telegram to get it."
        else
            warn "Invalid user ID. Must be a number like: 123456789"
        fi
    done

    # Write config
    cat > "$CONFIG_FILE" << EOF
# Hyperion Configuration
# Generated by installer on $(date)

# Telegram Bot
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOWED_USERS=$USER_ID
EOF

    success "Configuration saved"
fi

#===============================================================================
# GitHub MCP Server (Optional)
#===============================================================================

step "GitHub Integration (Optional)..."

echo ""
echo -e "${BOLD}GitHub MCP Server Setup${NC}"
echo ""
echo "The GitHub MCP server lets Hyperion:"
echo "  - Read and manage GitHub issues & PRs"
echo "  - Browse repositories and code"
echo "  - Access project boards"
echo "  - Monitor GitHub Actions workflows"
echo ""
read -p "Set up GitHub integration? [y/N] " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "You need a GitHub Personal Access Token (PAT)."
    echo ""
    echo "To create one:"
    echo "  1. Go to https://github.com/settings/tokens"
    echo "  2. Click 'Generate new token (classic)'"
    echo "  3. Select scopes: repo, read:org, read:project"
    echo "  4. Copy the generated token"
    echo ""

    read -p "Enter your GitHub PAT (or press Enter to skip): " GITHUB_PAT

    if [ -n "$GITHUB_PAT" ]; then
        # Add GitHub MCP server to Claude Code
        if command -v claude &> /dev/null; then
            claude mcp add-json github "{\"type\":\"http\",\"url\":\"https://api.githubcopilot.com/mcp\",\"headers\":{\"Authorization\":\"Bearer $GITHUB_PAT\"}}" --scope user 2>/dev/null
            success "GitHub MCP server configured"

            # Save PAT to config (optional, for reference)
            if [ -f "$CONFIG_FILE" ]; then
                echo "" >> "$CONFIG_FILE"
                echo "# GitHub Integration" >> "$CONFIG_FILE"
                echo "GITHUB_PAT_CONFIGURED=true" >> "$CONFIG_FILE"
            fi
        else
            warn "Claude Code not found. Configure GitHub MCP manually after install:"
            echo "  claude mcp add-json github '{\"type\":\"http\",\"url\":\"https://api.githubcopilot.com/mcp\",\"headers\":{\"Authorization\":\"Bearer YOUR_PAT\"}}'"
        fi
    else
        info "Skipped GitHub integration. You can set it up later:"
        echo "  claude mcp add-json github '{\"type\":\"http\",\"url\":\"https://api.githubcopilot.com/mcp\",\"headers\":{\"Authorization\":\"Bearer YOUR_PAT\"}}'"
    fi
else
    info "Skipped GitHub integration. You can set it up later - see README.md"
fi

#===============================================================================
# Generate Service Files
#===============================================================================

step "Generating systemd service files..."

# Get actual paths
PYTHON_PATH="$INSTALL_DIR/.venv/bin/python"
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

# Router service
cat > "$INSTALL_DIR/services/hyperion-router.service" << EOF
[Unit]
Description=Hyperion Router - Telegram to Claude Code bridge
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$INSTALL_DIR/config/config.env
ExecStart=$PYTHON_PATH $INSTALL_DIR/src/bot/hyperion_bot.py
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=hyperion-router

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Claude service (tmux-based always-on model)
cat > "$INSTALL_DIR/services/hyperion-claude.service" << EOF
[Unit]
Description=Hyperion Claude - Always-on Claude Code session
After=network.target hyperion-router.service
Wants=hyperion-router.service

[Service]
Type=forking
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$WORKSPACE_DIR
Environment=PATH=$HOME/.claude/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=$HOME
ExecStart=/usr/bin/tmux -L hyperion new-session -d -s hyperion -c $WORKSPACE_DIR $INSTALL_DIR/scripts/claude-wrapper.exp
ExecStop=/usr/bin/tmux -L hyperion kill-session -t hyperion
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

success "Service files generated"

#===============================================================================
# Install Services
#===============================================================================

step "Installing systemd services..."

sudo cp "$INSTALL_DIR/services/hyperion-router.service" /etc/systemd/system/
sudo cp "$INSTALL_DIR/services/hyperion-claude.service" /etc/systemd/system/
sudo systemctl daemon-reload

success "Services installed"

#===============================================================================
# Register MCP Server
#===============================================================================

step "Registering MCP server with Claude..."

# Remove existing registration if present
claude mcp remove hyperion-inbox 2>/dev/null || true

# Add new registration
if claude mcp add hyperion-inbox -s user -- "$PYTHON_PATH" "$INSTALL_DIR/src/mcp/inbox_server.py" 2>/dev/null; then
    success "MCP server registered"
else
    warn "MCP server registration may have failed. Check with: claude mcp list"
fi

#===============================================================================
# Install CLI
#===============================================================================

step "Installing hyperion CLI..."

# Remove any existing symlink or file
sudo rm -f /usr/local/bin/hyperion
sudo cp "$INSTALL_DIR/src/cli" /usr/local/bin/hyperion
sudo chmod +x /usr/local/bin/hyperion

success "CLI installed"

#===============================================================================
# Create Workspace Context
#===============================================================================

step "Creating workspace context..."

cat > "$WORKSPACE_DIR/CLAUDE.md" << 'EOF'
# Hyperion System Context

You are **Hyperion**, an always-on AI assistant. You process messages from Telegram and respond to users.

## Your Responsibilities

1. **Monitor inbox**: Use `check_inbox` to see new messages
2. **Respond helpfully**: Compose thoughtful replies
3. **Send replies**: Use `send_reply` with the correct `chat_id`
4. **Mark processed**: Use `mark_processed` after handling messages

## Available Tools (MCP)

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

### Scheduled Jobs (Cron Tasks)
- `create_scheduled_job(name, schedule, context)` - Create scheduled job
- `list_scheduled_jobs()` - List all scheduled jobs
- `get_scheduled_job(name)` - Get job details
- `update_scheduled_job(name, schedule?, context?, enabled?)` - Update job
- `delete_scheduled_job(name)` - Delete scheduled job
- `check_task_outputs(since?, limit?, job_name?)` - Check job outputs
- `write_task_output(job_name, output, status?)` - Write job output

## Behavior Guidelines

- Be concise (users are on mobile)
- Be helpful (answer directly)
- Check inbox regularly
- Maintain conversation context
EOF

success "Workspace context created"

#===============================================================================
# Start Services
#===============================================================================

step "Starting Hyperion services..."

echo ""
read -p "Start Hyperion services now? [Y/n] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    sudo systemctl enable hyperion-router hyperion-claude
    sudo systemctl start hyperion-router
    sleep 2
    sudo systemctl start hyperion-claude

    sleep 3

    echo ""
    if systemctl is-active --quiet hyperion-router; then
        success "Telegram bot: running"
    else
        warn "Telegram bot: not running (check logs)"
    fi

    if tmux -L hyperion has-session -t hyperion 2>/dev/null; then
        success "Claude session: running in tmux"
    else
        warn "Claude session: not running (check with: hyperion attach)"
    fi
else
    info "Services not started. Start manually with: hyperion start"
fi

#===============================================================================
# Done
#===============================================================================

echo ""
echo -e "${GREEN}"
cat << 'DONE'
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║              HYPERION INSTALLATION COMPLETE!                  ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
DONE
echo -e "${NC}"

echo "Test it by sending a message to your Telegram bot!"
echo ""
echo -e "${BOLD}Commands:${NC}"
echo "  hyperion status    Check service status"
echo "  hyperion logs      View logs"
echo "  hyperion inbox     Check pending messages"
echo "  hyperion start     Start all services"
echo "  hyperion stop      Stop all services"
echo "  hyperion help      Show all commands"
echo ""
echo -e "${BOLD}Directories:${NC}"
echo "  $INSTALL_DIR        Repository"
echo "  $WORKSPACE_DIR      Claude workspace"
echo "  $MESSAGES_DIR       Message queues"
echo ""
