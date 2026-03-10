#!/bin/bash
# ============================================================================
# agentforce-adlc Installer for Claude Code
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main/tools/install.sh | bash
# ============================================================================
set -euo pipefail

GITHUB_RAW="https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main"
INSTALL_PY_URL="${GITHUB_RAW}/tools/install.py"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

# Colors
if [[ -t 1 ]] && [[ "${TERM:-}" != "dumb" ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

print_step()    { echo -e "${BLUE}▶${NC} $1"; }
print_success() { echo -e "  ${GREEN}✓${NC} $1"; }
print_warning() { echo -e "  ${YELLOW}⚠${NC} $1"; }
print_error()   { echo -e "  ${RED}✗${NC} $1"; }

echo -e "${BOLD}agentforce-adlc installer${NC}"
echo ""

# Check Python 3.10+
print_step "Checking for Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+..."

if ! command -v python3 &>/dev/null; then
    print_error "Python 3 not found. Install Python 3.10+ and try again."
    exit 1
fi

version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
major=${version%%.*}
minor=${version#*.}; minor=${minor%%.*}

if [[ "$major" -lt "$MIN_PYTHON_MAJOR" ]] || \
   [[ "$major" -eq "$MIN_PYTHON_MAJOR" && "$minor" -lt "$MIN_PYTHON_MINOR" ]]; then
    print_error "Python $version found, but ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ required"
    exit 1
fi
print_success "Python $version"

# Check Claude Code directory
print_step "Checking for Claude Code..."
if [[ ! -d "$HOME/.claude" ]]; then
    print_error "Claude Code not found (~/.claude/ missing)"
    echo "  Install Claude Code first: npm install -g @anthropic-ai/claude-code"
    exit 1
fi
print_success "Claude Code found"

# Check sf CLI (optional)
print_step "Checking for Salesforce CLI (optional)..."
if command -v sf &>/dev/null; then
    sf_version=$(sf --version 2>/dev/null | head -1)
    print_success "Salesforce CLI: $sf_version"
else
    print_warning "Salesforce CLI not found (install later: npm install -g @salesforce/cli)"
fi

# Download and run Python installer
print_step "Downloading installer..."
tmp_installer="/tmp/adlc-install-$$.py"

if ! curl -fsSL "$INSTALL_PY_URL" -o "$tmp_installer"; then
    print_error "Failed to download installer"
    rm -f "$tmp_installer"
    exit 1
fi
print_success "Installer downloaded"

print_step "Running installation..."
echo ""
python3 "$tmp_installer" --force --called-from-bash
result=$?

rm -f "$tmp_installer"
exit $result
