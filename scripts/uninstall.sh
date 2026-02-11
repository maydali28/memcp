#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# MemCP Uninstaller — Remove MemCP configuration and data
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors & Symbols ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

CHECK="${GREEN}✔${NC}"
CROSS="${RED}✘${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${BLUE}ℹ${NC}"

separator() {
    echo -e "${DIM}  ────────────────────────────────────────────────${NC}"
}

ask_yes_no() {
    local prompt="$1" default="${2:-n}"
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

# ── Banner ────────────────────────────────────────────────────────────
show_banner() {
    echo ""
    if command -v figlet &>/dev/null; then
        echo -e "${RED}"
        figlet -f slant "MemCP" 2>/dev/null || figlet "MemCP" 2>/dev/null || true
        echo -e "${NC}"
    else
        echo ""
        echo -e "${RED}${BOLD}  ██████   ██████ ██████████ ██████   ██████   █████████  ███████████${NC}"
        echo -e "${RED}${BOLD} ░░██████ ██████ ░░███░░░░░█░░██████ ██████   ███░░░░░███░░███░░░░░███${NC}"
        echo -e "${RED}${BOLD}  ░███░█████░███  ░███  █ ░  ░███░█████░███  ███     ░░░  ░███    ░███${NC}"
        echo -e "${RED}${BOLD}  ░███░░███ ░███  ░██████    ░███░░███ ░███ ░███          ░██████████${NC}"
        echo -e "${RED}${BOLD}  ░███ ░░░  ░███  ░███░░█    ░███ ░░░  ░███ ░███          ░███░░░░░░${NC}"
        echo -e "${RED}${BOLD}  ░███      ░███  ░███ ░   █ ░███      ░███ ░░███     ███ ░███${NC}"
        echo -e "${RED}${BOLD}  █████     █████ ██████████ █████     █████ ░░█████████  █████${NC}"
        echo -e "${RED}${BOLD} ░░░░░     ░░░░░ ░░░░░░░░░░ ░░░░░     ░░░░░   ░░░░░░░░░  ░░░░░${NC}"
        echo ""
    fi

    echo -e "${DIM}  Uninstaller${NC}"
    echo ""
    separator
}

# ── Detect What's Installed ───────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOVED=0

detect_installation() {
    echo ""
    echo -e "  ${BOLD}Detected installation:${NC}"
    echo ""

    # MCP registration
    MCP_REGISTERED=false
    if command -v claude &>/dev/null; then
        if claude mcp list 2>/dev/null | grep -q "memcp"; then
            echo -e "    ${CHECK} MCP server registered with Claude Code"
            MCP_REGISTERED=true
        else
            echo -e "    ${DIM}  MCP server not registered${NC}"
        fi
    else
        echo -e "    ${DIM}  Claude CLI not available${NC}"
    fi

    # Data directory
    DATA_DIR_EXISTS=false
    DATA_DIR="${MEMCP_DATA_DIR:-${HOME}/.memcp}"
    if [[ -d "$DATA_DIR" ]]; then
        local SIZE
        SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | awk '{print $1}')
        echo -e "    ${CHECK} Data directory: ${DATA_DIR} (${SIZE})"
        DATA_DIR_EXISTS=true
    else
        echo -e "    ${DIM}  No data directory at ${DATA_DIR}${NC}"
    fi

    # Virtual environment
    VENV_EXISTS=false
    if [[ -d "${PROJECT_DIR}/.venv" ]]; then
        echo -e "    ${CHECK} Virtual environment: .venv/"
        VENV_EXISTS=true
    else
        echo -e "    ${DIM}  No virtual environment${NC}"
    fi

    # Sub-agents (global: ~/.claude/agents/)
    AGENTS_EXIST=false
    AGENT_COUNT=0
    if [[ -d "${HOME}/.claude/agents" ]]; then
        AGENT_COUNT=$(find "${HOME}/.claude/agents" -name "memcp-*.md" 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$AGENT_COUNT" -gt 0 ]]; then
            echo -e "    ${CHECK} Sub-agents: ${AGENT_COUNT} agent(s) in ~/.claude/agents/"
            for agent_file in "${HOME}/.claude/agents"/memcp-*.md; do
                if [[ -f "$agent_file" ]]; then
                    echo -e "      ${DIM}$(basename "$agent_file")${NC}"
                fi
            done
            AGENTS_EXIST=true
        else
            echo -e "    ${DIM}  No MemCP sub-agents${NC}"
        fi
    else
        echo -e "    ${DIM}  No sub-agents directory${NC}"
    fi

    # Hook configuration (global: ~/.claude/settings.json)
    HOOKS_EXIST=false
    if [[ -f "${HOME}/.claude/settings.json" ]]; then
        # Check if MemCP hooks are present in the global settings
        if command -v python3 &>/dev/null && python3 -c "
import json, sys
try:
    settings = json.load(open('${HOME}/.claude/settings.json'))
    hooks = settings.get('hooks', {})
    for event_type in hooks:
        for entry in hooks[event_type]:
            for hook in entry.get('hooks', []):
                cmd = hook.get('command', '')
                if 'memcp' in cmd or 'pre_compact_save' in cmd or 'auto_save_reminder' in cmd or 'reset_counter' in cmd:
                    sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null; then
            echo -e "    ${CHECK} MemCP hooks in ~/.claude/settings.json"
            HOOKS_EXIST=true
        else
            echo -e "    ${DIM}  No MemCP hooks in ~/.claude/settings.json${NC}"
        fi
    else
        echo -e "    ${DIM}  No ~/.claude/settings.json${NC}"
    fi

    echo ""
}

# ── Removal ───────────────────────────────────────────────────────────
remove_components() {
    echo -e "  ${BOLD}What would you like to remove?${NC}"
    echo ""

    # MCP registration
    if [[ "$MCP_REGISTERED" == "true" ]]; then
        if ask_yes_no "Remove MCP server registration from Claude Code?" "y"; then
            if claude mcp remove memcp 2>/dev/null; then
                echo -e "    ${CHECK} MCP registration removed"
                REMOVED=$((REMOVED+1))
            else
                echo -e "    ${CROSS} Failed to remove MCP registration"
            fi
        else
            echo -e "    ${DIM}  Skipped MCP registration${NC}"
        fi
        echo ""
    fi

    # Sub-agents (global: ~/.claude/agents/)
    if [[ "$AGENTS_EXIST" == "true" ]]; then
        if ask_yes_no "Remove ${AGENT_COUNT} MemCP sub-agent(s) from ~/.claude/agents/?" "y"; then
            local removed_agents=0
            for agent_file in "${HOME}/.claude/agents"/memcp-*.md; do
                if [[ -f "$agent_file" ]]; then
                    rm -f "$agent_file"
                    removed_agents=$((removed_agents+1))
                fi
            done
            echo -e "    ${CHECK} ${removed_agents} sub-agent(s) removed"
            REMOVED=$((REMOVED+1))

            # Clean up agents dir if empty
            if [[ -d "${HOME}/.claude/agents" ]]; then
                local remaining
                remaining=$(find "${HOME}/.claude/agents" -type f 2>/dev/null | wc -l | tr -d ' ')
                if [[ "$remaining" -eq 0 ]]; then
                    rmdir "${HOME}/.claude/agents" 2>/dev/null || true
                    echo -e "    ${DIM}  Removed empty ~/.claude/agents/ directory${NC}"
                fi
            fi
        else
            echo -e "    ${DIM}  Skipped sub-agents${NC}"
        fi
        echo ""
    fi

    # Hooks (remove MemCP hooks from global ~/.claude/settings.json)
    if [[ "$HOOKS_EXIST" == "true" ]]; then
        local HOOK_SCRIPT="${PROJECT_DIR}/scripts/setup-hooks.sh"
        if [[ -f "$HOOK_SCRIPT" ]]; then
            if QUIET=true bash "$HOOK_SCRIPT" remove; then
                REMOVED=$((REMOVED+1))
            fi
        else
            echo -e "    ${CROSS} Hook setup script not found at scripts/setup-hooks.sh"
            echo -e "    ${DIM}  Edit ~/.claude/settings.json manually to remove MemCP hook entries${NC}"
        fi
        echo ""
    fi

    # Virtual environment
    if [[ "$VENV_EXISTS" == "true" ]]; then
        if ask_yes_no "Remove virtual environment (.venv/)?" "y"; then
            rm -rf "${PROJECT_DIR}/.venv"
            echo -e "    ${CHECK} Virtual environment removed"
            REMOVED=$((REMOVED+1))
        else
            echo -e "    ${DIM}  Skipped virtual environment${NC}"
        fi
        echo ""
    fi

    # Data directory (DANGEROUS — user data!)
    if [[ "$DATA_DIR_EXISTS" == "true" ]]; then
        echo -e "  ${RED}${BOLD}⚠  WARNING: The data directory contains your saved memories!${NC}"
        echo -e "  ${RED}  This includes insights, contexts, graph data, and session history.${NC}"
        echo -e "  ${RED}  This action is ${BOLD}IRREVERSIBLE${NC}${RED}.${NC}"
        echo ""
        if ask_yes_no "${RED}Delete ALL data at ${DATA_DIR}?${NC}" "n"; then
            echo -en "  ${CYAN}?${NC} Type ${BOLD}DELETE${NC} to confirm: "
            read -r confirm
            if [[ "$confirm" == "DELETE" ]]; then
                rm -rf "$DATA_DIR"
                echo -e "    ${CHECK} Data directory deleted: ${DATA_DIR}"
                REMOVED=$((REMOVED+1))
            else
                echo -e "    ${DIM}  Confirmation not matched — skipped${NC}"
            fi
        else
            echo -e "    ${DIM}  Skipped data directory (preserved)${NC}"
        fi
        echo ""
    fi
}

# ── Summary ───────────────────────────────────────────────────────────
show_summary() {
    separator
    echo ""

    if [[ $REMOVED -eq 0 ]]; then
        echo -e "  ${INFO} Nothing was removed."
    else
        echo -e "  ${CHECK} ${BOLD}Removed ${REMOVED} component(s).${NC}"
    fi

    # Show what's still present
    local REMAINING=0
    if command -v claude &>/dev/null && claude mcp list 2>/dev/null | grep -q "memcp"; then
        REMAINING=$((REMAINING+1))
    fi
    if [[ -d "${MEMCP_DATA_DIR:-${HOME}/.memcp}" ]]; then
        REMAINING=$((REMAINING+1))
    fi
    if [[ -d "${PROJECT_DIR}/.venv" ]]; then
        REMAINING=$((REMAINING+1))
    fi
    if [[ -f "${HOME}/.claude/settings.json" ]] && command -v python3 &>/dev/null && python3 -c "
import json, sys
try:
    settings = json.load(open('${HOME}/.claude/settings.json'))
    hooks = settings.get('hooks', {})
    for event_type in hooks:
        for entry in hooks[event_type]:
            for hook in entry.get('hooks', []):
                if 'memcp' in hook.get('command', '') or 'pre_compact_save' in hook.get('command', '') or 'auto_save_reminder' in hook.get('command', ''):
                    sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null; then
        REMAINING=$((REMAINING+1))
    fi
    if [[ -d "${HOME}/.claude/agents" ]] && find "${HOME}/.claude/agents" -name "memcp-*.md" 2>/dev/null | grep -q .; then
        REMAINING=$((REMAINING+1))
    fi

    if [[ $REMAINING -gt 0 ]]; then
        echo -e "  ${INFO} ${REMAINING} component(s) still present."
        echo -e "  ${DIM}  Run this script again to remove remaining components.${NC}"
    fi

    echo ""
    echo -e "  ${DIM}To reinstall: bash scripts/install.sh${NC}"
    echo ""
    separator
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────
main() {
    show_banner
    detect_installation
    remove_components
    show_summary
}

main "$@"
