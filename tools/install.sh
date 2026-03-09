#!/usr/bin/env bash
# Install agentforce-adlc skills, agents, and hooks to ~/.claude/
#
# Usage:
#   bash tools/install.sh
#   curl -sSL https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main/tools/install.sh | bash

set -euo pipefail

REPO_URL="https://github.com/Authoring-Agent/agentforce-adlc.git"
INSTALL_DIR="${HOME}/.claude/adlc-install"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo "agentforce-adlc installer"
echo "========================="
echo ""

# Check Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: ${PYTHON_VERSION}"

# Check if running from repo root
if [ -f "tools/install.py" ]; then
    echo "Running from project root..."
    python3 tools/install.py
    exit 0
fi

# Clone or update the repo
if [ -d "${INSTALL_DIR}" ]; then
    echo "Updating existing installation..."
    cd "${INSTALL_DIR}"
    git pull --quiet
else
    echo "Cloning repository..."
    git clone --quiet "${REPO_URL}" "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
fi

# Run the installer
python3 tools/install.py

echo -e "${GREEN}Done!${NC}"
echo ""
