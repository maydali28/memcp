#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# MemCP Hook Manager — Install, remove, or check auto-save hooks
# ──────────────────────────────────────────────────────────────────────
#
# Usage:
#   bash scripts/setup-hooks.sh install   # Merge hooks into ~/.claude/settings.json
#   bash scripts/setup-hooks.sh remove    # Remove MemCP hooks from settings
#   bash scripts/setup-hooks.sh status    # Check if hooks are installed
#
# Options:
#   --quiet     Suppress interactive prompts (auto-confirm)
#   --help      Show this help message
#
set -euo pipefail

# ── Colors & Symbols ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

CHECK="${GREEN}✔${NC}"
CROSS="${RED}✘${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${BLUE}ℹ${NC}"
ARROW="${CYAN}→${NC}"

# ── Helpers ───────────────────────────────────────────────────────────
print_ok()   { echo -e "  ${CHECK} $1"; }
print_fail() { echo -e "  ${CROSS} $1"; }
print_warn() { echo -e "  ${WARN} $1"; }
print_info() { echo -e "  ${INFO} $1"; }
print_arrow(){ echo -e "  ${ARROW} $1"; }

ask_yes_no() {
    local prompt="$1" default="${2:-y}"
    if [[ "${QUIET:-false}" == "true" ]]; then
        [[ "$default" == "y" ]]
        return
    fi
    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi
    echo -en "  ${CYAN}?${NC} $prompt"
    read -r answer
    answer="${answer:-$default}"
    [[ "$answer" =~ ^[Yy] ]]
}

# ── Paths ─────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS_FILE="${HOME}/.claude/settings.json"
TEMPLATE_FILE="${PROJECT_DIR}/hooks/snippets/settings.json"
PYTHON_CMD="${PYTHON_CMD:-python3}"

# ── Detect MemCP hooks ───────────────────────────────────────────────
hooks_are_installed() {
    [[ -f "$SETTINGS_FILE" ]] || return 1
    command -v "$PYTHON_CMD" &>/dev/null || return 1

    $PYTHON_CMD -c "
import json, sys
try:
    settings = json.load(open('${SETTINGS_FILE}'))
    hooks = settings.get('hooks', {})
    for event_type in hooks:
        for entry in hooks[event_type]:
            for hook in entry.get('hooks', []):
                cmd = hook.get('command', '')
                if 'pre_compact_save' in cmd or 'auto_save_reminder' in cmd or 'reset_counter' in cmd:
                    sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

# ── Install ──────────────────────────────────────────────────────────
do_install() {
    echo -e "\n  ${BOLD}MemCP Auto-Save Hooks${NC}"
    echo ""
    echo -e "  Hooks protect your context from being lost:"
    echo -e "    ${BOLD}PreCompact${NC}      — Forces save before /compact"
    echo -e "    ${BOLD}Reminders${NC}       — Progressive save reminders (10/20/30 turns)"
    echo -e "    ${BOLD}Counter Reset${NC}   — Resets reminder counter after saves"
    echo ""

    if [[ ! -f "$TEMPLATE_FILE" ]]; then
        print_fail "Hook template not found at hooks/snippets/settings.json"
        print_info "Ensure you are running from the MemCP project root"
        return 1
    fi

    if hooks_are_installed; then
        print_info "MemCP hooks are already installed in ~/.claude/settings.json"
        if ! ask_yes_no "Reinstall (overwrite existing MemCP hooks)?" "n"; then
            print_ok "Keeping existing hooks"
            return 0
        fi
        # Remove existing hooks first, then re-add
        _merge_remove
    fi

    if ! ask_yes_no "Merge auto-save hooks into ~/.claude/settings.json?" "y"; then
        print_info "Skipping hooks — you can run this later with:"
        echo -e "    ${DIM}bash scripts/setup-hooks.sh install${NC}"
        return 0
    fi

    _merge_install
}

_merge_install() {
    mkdir -p "${HOME}/.claude"

    if $PYTHON_CMD -c "
import json, os

settings_file = '$SETTINGS_FILE'
template_file = '$TEMPLATE_FILE'

existing = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file) as f:
            existing = json.load(f)
    except (json.JSONDecodeError, IOError):
        existing = {}

with open(template_file) as f:
    template = json.load(f)

template_hooks = template.get('hooks', {})
existing_hooks = existing.get('hooks', {})

for event_type, entries in template_hooks.items():
    if event_type not in existing_hooks:
        existing_hooks[event_type] = []
    for new_entry in entries:
        new_matcher = new_entry.get('matcher', '')
        new_commands = set()
        for h in new_entry.get('hooks', []):
            new_commands.add(h.get('command', ''))
        already_exists = False
        for existing_entry in existing_hooks[event_type]:
            if existing_entry.get('matcher', '') == new_matcher:
                existing_commands = set()
                for h in existing_entry.get('hooks', []):
                    existing_commands.add(h.get('command', ''))
                if new_commands.issubset(existing_commands):
                    already_exists = True
                    break
        if not already_exists:
            existing_hooks[event_type].append(new_entry)

existing['hooks'] = existing_hooks

with open(settings_file, 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
" 2>/dev/null; then
        print_ok "Hooks merged into ~/.claude/settings.json"
    else
        print_fail "Could not merge hooks automatically"
        print_info "Manually merge hooks from hooks/snippets/settings.json into ~/.claude/settings.json"
        print_info "See docs/HOOKS.md for details"
        return 1
    fi
}

# ── Remove ───────────────────────────────────────────────────────────
do_remove() {
    echo -e "\n  ${BOLD}Remove MemCP Hooks${NC}"
    echo ""

    if ! hooks_are_installed; then
        print_info "No MemCP hooks found in ~/.claude/settings.json"
        return 0
    fi

    print_info "MemCP hooks detected in ~/.claude/settings.json"

    if ! ask_yes_no "Remove MemCP hooks from ~/.claude/settings.json?" "y"; then
        print_info "Keeping existing hooks"
        return 0
    fi

    _merge_remove
}

_merge_remove() {
    if ! command -v "$PYTHON_CMD" &>/dev/null; then
        print_fail "Python 3 not found — cannot modify settings"
        return 1
    fi

    if $PYTHON_CMD -c "
import json, os

settings_file = '$SETTINGS_FILE'
with open(settings_file) as f:
    settings = json.load(f)

hooks = settings.get('hooks', {})
memcp_commands = {'pre_compact_save', 'auto_save_reminder', 'reset_counter', 'memcp'}

for event_type in list(hooks.keys()):
    filtered = []
    for entry in hooks[event_type]:
        is_memcp = False
        for hook in entry.get('hooks', []):
            cmd = hook.get('command', '')
            if any(mc in cmd for mc in memcp_commands):
                is_memcp = True
                break
        matcher = entry.get('matcher', '')
        if 'memcp' in matcher:
            is_memcp = True
        if not is_memcp:
            filtered.append(entry)
    if filtered:
        hooks[event_type] = filtered
    else:
        del hooks[event_type]

if hooks:
    settings['hooks'] = hooks
else:
    settings.pop('hooks', None)

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
" 2>/dev/null; then
        print_ok "MemCP hooks removed from ~/.claude/settings.json"
    else
        print_fail "Failed to remove hooks (manual edit needed)"
        print_info "Edit ~/.claude/settings.json and remove MemCP hook entries"
        return 1
    fi
}

# ── Status ───────────────────────────────────────────────────────────
do_status() {
    echo -e "\n  ${BOLD}MemCP Hook Status${NC}"
    echo ""

    if [[ ! -f "$SETTINGS_FILE" ]]; then
        print_info "No ~/.claude/settings.json found"
        print_info "Run: bash scripts/setup-hooks.sh install"
        return 0
    fi

    if hooks_are_installed; then
        print_ok "MemCP hooks are installed in ~/.claude/settings.json"

        # Show details
        if command -v "$PYTHON_CMD" &>/dev/null; then
            $PYTHON_CMD -c "
import json

with open('$SETTINGS_FILE') as f:
    settings = json.load(f)

hooks = settings.get('hooks', {})
memcp_commands = {'pre_compact_save', 'auto_save_reminder', 'reset_counter'}

for event_type, entries in hooks.items():
    for entry in entries:
        for hook in entry.get('hooks', []):
            cmd = hook.get('command', '')
            if any(mc in cmd for mc in memcp_commands):
                matcher = entry.get('matcher', '') or '(all)'
                print(f'    {event_type:15s} matcher={matcher:40s} cmd={cmd}')
" 2>/dev/null || true
        fi
    else
        print_warn "MemCP hooks are NOT installed"
        print_info "Run: bash scripts/setup-hooks.sh install"
    fi

    # Check hook files exist
    echo ""
    local HOOK_FILES=("pre_compact_save.py" "auto_save_reminder.py" "reset_counter.py")
    for hf in "${HOOK_FILES[@]}"; do
        if [[ -f "${PROJECT_DIR}/hooks/${hf}" ]]; then
            print_ok "hooks/${hf} exists"
        else
            print_warn "hooks/${hf} missing"
        fi
    done

    # Check template
    if [[ -f "$TEMPLATE_FILE" ]]; then
        print_ok "hooks/snippets/settings.json template exists"
    else
        print_warn "hooks/snippets/settings.json template missing"
    fi
}

# ── Help ─────────────────────────────────────────────────────────────
show_help() {
    echo ""
    echo -e "  ${BOLD}MemCP Hook Manager${NC}"
    echo ""
    echo -e "  ${BOLD}Usage:${NC}"
    echo -e "    bash scripts/setup-hooks.sh ${CYAN}install${NC}   Merge hooks into ~/.claude/settings.json"
    echo -e "    bash scripts/setup-hooks.sh ${CYAN}remove${NC}    Remove MemCP hooks from settings"
    echo -e "    bash scripts/setup-hooks.sh ${CYAN}status${NC}    Check if hooks are installed"
    echo ""
    echo -e "  ${BOLD}Options:${NC}"
    echo -e "    ${CYAN}--quiet${NC}     Suppress prompts (auto-confirm with defaults)"
    echo -e "    ${CYAN}--help${NC}      Show this help message"
    echo ""
    echo -e "  ${BOLD}What the hooks do:${NC}"
    echo -e "    ${BOLD}PreCompact${NC}      Forces save before /compact (blocks execution)"
    echo -e "    ${BOLD}Notification${NC}    Progressive reminders at 10/20/30 turns (>= 55% context)"
    echo -e "    ${BOLD}PostToolUse${NC}     Resets reminder counter after memcp_remember/memcp_load_context"
    echo ""
    echo -e "  ${BOLD}Examples:${NC}"
    echo -e "    ${DIM}bash scripts/setup-hooks.sh install${NC}           # Interactive install"
    echo -e "    ${DIM}bash scripts/setup-hooks.sh install --quiet${NC}   # Non-interactive install"
    echo -e "    ${DIM}bash scripts/setup-hooks.sh status${NC}            # Check current state"
    echo ""
    echo -e "  ${DIM}See docs/HOOKS.md for full hook documentation.${NC}"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────
main() {
    local ACTION=""
    QUIET="${QUIET:-false}"

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            install|remove|status) ACTION="$arg" ;;
            --quiet|-q) QUIET=true ;;
            --help|-h) show_help; exit 0 ;;
            *)
                echo -e "  ${CROSS} Unknown argument: $arg"
                show_help
                exit 1
                ;;
        esac
    done

    if [[ -z "$ACTION" ]]; then
        show_help
        exit 1
    fi

    case "$ACTION" in
        install) do_install ;;
        remove)  do_remove ;;
        status)  do_status ;;
    esac
}

main "$@"
