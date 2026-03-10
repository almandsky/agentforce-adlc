#!/bin/bash
# ============================================================================
# agentforce-adlc Installer
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main/tools/install.sh | bash
#   curl -sSL ... | bash -s -- --target cursor
# ============================================================================
set -euo pipefail

GITHUB_RAW="https://raw.githubusercontent.com/almandsky/agentforce-adlc/main"
INSTALL_PY_URL="${GITHUB_RAW}/tools/install.py"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

# Parse --target flag
TARGET=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            TARGET="$2"
            shift 2
            ;;
        --target=*)
            TARGET="${1#*=}"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

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

# Check for at least one supported IDE directory
print_step "Checking for supported IDE..."

EFFECTIVE_TARGET="$TARGET"
has_claude=false
has_cursor=false

[[ -d "$HOME/.claude" ]] && has_claude=true
[[ -d "$HOME/.cursor" ]] && has_cursor=true

if [[ -n "$EFFECTIVE_TARGET" ]]; then
    # User specified a target — validate it exists
    case "$EFFECTIVE_TARGET" in
        claude)
            if ! $has_claude; then
                print_error "Claude Code not found (~/.claude/ missing)"
                echo "  Install Claude Code first: npm install -g @anthropic-ai/claude-code"
                exit 1
            fi
            print_success "Claude Code found"
            ;;
        cursor)
            if ! $has_cursor; then
                print_error "Cursor not found (~/.cursor/ missing)"
                echo "  Install Cursor first: https://www.cursor.com/"
                exit 1
            fi
            print_success "Cursor found"
            ;;
        both)
            if ! $has_claude && ! $has_cursor; then
                print_error "Neither Claude Code nor Cursor found"
                echo "  Install at least one: Claude Code or Cursor"
                exit 1
            fi
            $has_claude && print_success "Claude Code found"
            $has_cursor && print_success "Cursor found"
            ! $has_claude && print_warning "Claude Code not found (~/.claude/ missing), will skip"
            ! $has_cursor && print_warning "Cursor not found (~/.cursor/ missing), will skip"
            ;;
        *)
            print_error "Unknown target: $EFFECTIVE_TARGET (use claude, cursor, or both)"
            exit 1
            ;;
    esac
else
    # Auto-detect
    if $has_claude || $has_cursor; then
        $has_claude && print_success "Claude Code found"
        $has_cursor && print_success "Cursor found"
    else
        print_error "Neither Claude Code (~/.claude/) nor Cursor (~/.cursor/) found"
        echo "  Install Claude Code: npm install -g @anthropic-ai/claude-code"
        echo "  Install Cursor: https://www.cursor.com/"
        exit 1
    fi
fi

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

# Build command with optional --target
cmd=(python3 "$tmp_installer" --force --called-from-bash)
if [[ -n "$TARGET" ]]; then
    cmd+=(--target "$TARGET")
fi

"${cmd[@]}"
result=$?

rm -f "$tmp_installer"
exit $result
