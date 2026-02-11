#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# MemCP Installer — Interactive setup for the persistent memory MCP server
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
NC='\033[0m' # No Color

CHECK="${GREEN}✔${NC}"
CROSS="${RED}✘${NC}"
ARROW="${CYAN}→${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${BLUE}ℹ${NC}"

# ── Helpers ───────────────────────────────────────────────────────────
print_step() { echo -e "\n${BOLD}${BLUE}[$1/$TOTAL_STEPS]${NC} ${BOLD}$2${NC}"; }
print_ok()   { echo -e "  ${CHECK} $1"; }
print_fail() { echo -e "  ${CROSS} $1"; }
print_warn() { echo -e "  ${WARN} $1"; }
print_info() { echo -e "  ${INFO} $1"; }
print_arrow(){ echo -e "  ${ARROW} $1"; }

ask_yes_no() {
    local prompt="$1" default="${2:-y}"
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

ask_choice() {
    local prompt="$1"
    shift
    local options=("$@")
    echo -e "\n  ${CYAN}?${NC} ${prompt}"
    for i in "${!options[@]}"; do
        echo -e "    ${BOLD}$((i+1)))${NC} ${options[$i]}"
    done
    echo -en "  ${CYAN}→${NC} Enter choice [1-${#options[@]}]: "
    read -r choice
    echo "$choice"
}

separator() {
    echo -e "${DIM}  ────────────────────────────────────────────────${NC}"
}

# ── Banner ────────────────────────────────────────────────────────────
show_banner() {
    echo ""
    # Try figlet first, then toilet, then fallback ASCII art
    if command -v figlet &>/dev/null; then
        echo -e "${MAGENTA}"
        figlet -f slant "MemCP" 2>/dev/null || figlet "MemCP" 2>/dev/null || show_ascii_banner
        echo -e "${NC}"
    elif command -v toilet &>/dev/null; then
        echo -e "${MAGENTA}"
        toilet -f future "MemCP" 2>/dev/null || show_ascii_banner
        echo -e "${NC}"
    else
        show_ascii_banner
    fi

    echo -e "${DIM}  Persistent Memory MCP Server for Claude Code${NC}"
    echo -e "${DIM}  Never lose context again.${NC}"
    echo ""
    separator
}

show_ascii_banner() {
    echo ""
    echo -e "${MAGENTA}${BOLD}  ██████   ██████ ██████████ ██████   ██████   █████████  ███████████${NC}"
    echo -e "${MAGENTA}${BOLD} ░░██████ ██████ ░░███░░░░░█░░██████ ██████   ███░░░░░███░░███░░░░░███${NC}"
    echo -e "${MAGENTA}${BOLD}  ░███░█████░███  ░███  █ ░  ░███░█████░███  ███     ░░░  ░███    ░███${NC}"
    echo -e "${MAGENTA}${BOLD}  ░███░░███ ░███  ░██████    ░███░░███ ░███ ░███          ░██████████${NC}"
    echo -e "${MAGENTA}${BOLD}  ░███ ░░░  ░███  ░███░░█    ░███ ░░░  ░███ ░███          ░███░░░░░░${NC}"
    echo -e "${MAGENTA}${BOLD}  ░███      ░███  ░███ ░   █ ░███      ░███ ░░███     ███ ░███${NC}"
    echo -e "${MAGENTA}${BOLD}  █████     █████ ██████████ █████     █████ ░░█████████  █████${NC}"
    echo -e "${MAGENTA}${BOLD} ░░░░░     ░░░░░ ░░░░░░░░░░ ░░░░░     ░░░░░   ░░░░░░░░░  ░░░░░${NC}"
    echo ""
}

# ── Pre-flight Checks ─────────────────────────────────────────────────
TOTAL_STEPS=8
ERRORS=0
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

preflight_checks() {
    print_step 1 "Pre-flight checks"
    echo ""

    # Python version
    if command -v python3 &>/dev/null; then
        PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
        PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
        if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 10 ]]; then
            print_ok "Python ${PY_VERSION} detected (>= 3.10 required)"
            PYTHON_CMD="python3"
        else
            print_fail "Python ${PY_VERSION} is too old (>= 3.10 required)"
            ERRORS=$((ERRORS+1))
        fi
    else
        print_fail "Python 3 not found"
        print_info "Install Python 3.10+ from https://python.org"
        ERRORS=$((ERRORS+1))
    fi

    # pip
    if $PYTHON_CMD -m pip --version &>/dev/null 2>&1; then
        PIP_VERSION=$($PYTHON_CMD -m pip --version 2>/dev/null | awk '{print $2}')
        print_ok "pip ${PIP_VERSION} available"
    else
        print_fail "pip not found"
        print_info "Install pip: ${PYTHON_CMD} -m ensurepip --upgrade"
        ERRORS=$((ERRORS+1))
    fi

    # venv module
    if $PYTHON_CMD -c "import venv" &>/dev/null 2>&1; then
        print_ok "venv module available"
    else
        print_warn "venv module not found — may need: apt install python3-venv"
    fi

    # Claude CLI
    if command -v claude &>/dev/null; then
        print_ok "Claude CLI detected"
        CLAUDE_AVAILABLE=true
    else
        print_warn "Claude CLI not found — MCP registration will be skipped"
        print_info "Install: https://docs.anthropic.com/en/docs/claude-code"
        CLAUDE_AVAILABLE=false
    fi

    # Docker (optional)
    if command -v docker &>/dev/null; then
        print_ok "Docker available (optional)"
        DOCKER_AVAILABLE=true
    else
        print_info "Docker not found (optional — for containerized setup)"
        DOCKER_AVAILABLE=false
    fi

    # Project directory
    if [[ -f "${PROJECT_DIR}/pyproject.toml" ]]; then
        print_ok "Project found at ${PROJECT_DIR}"
    else
        print_fail "pyproject.toml not found at ${PROJECT_DIR}"
        print_info "Run this script from the MemCP project root"
        ERRORS=$((ERRORS+1))
    fi

    # Check for existing installation
    if [[ -d "${PROJECT_DIR}/.venv" ]]; then
        print_warn "Existing .venv found — will be reused"
    fi
    if [[ -d "${HOME}/.memcp" ]]; then
        print_info "Existing ~/.memcp data directory found — will be preserved"
    fi

    echo ""
    if [[ $ERRORS -gt 0 ]]; then
        echo -e "  ${RED}${BOLD}${ERRORS} pre-flight check(s) failed.${NC} Please fix the issues above and retry."
        exit 1
    else
        echo -e "  ${GREEN}${BOLD}All pre-flight checks passed!${NC}"
    fi
}

# ── Installation Method ───────────────────────────────────────────────
choose_install_method() {
    print_step 2 "Choose installation method"

    local options=(
        "Local development  ${DIM}(editable install from source, recommended for contributors)${NC}"
        "pip install         ${DIM}(install as a package from source)${NC}"
        "Docker              ${DIM}(containerized, no local Python needed)${NC}"
    )

    if [[ "$DOCKER_AVAILABLE" == "false" ]]; then
        options[2]="${DIM}Docker (not available — install Docker first)${NC}"
    fi

    INSTALL_METHOD=$(ask_choice "How would you like to install MemCP?" "${options[@]}")

    case "$INSTALL_METHOD" in
        1) INSTALL_METHOD="dev" ;;
        2) INSTALL_METHOD="pip" ;;
        3)
            if [[ "$DOCKER_AVAILABLE" == "false" ]]; then
                echo -e "  ${CROSS} Docker is not installed. Please choose another method."
                choose_install_method
                return
            fi
            INSTALL_METHOD="docker"
            ;;
        *) INSTALL_METHOD="dev" ;;
    esac
}

# ── Optional Extras ───────────────────────────────────────────────────
choose_extras() {
    if [[ "$INSTALL_METHOD" == "docker" ]]; then
        EXTRAS=""
        return
    fi

    print_step 3 "Choose optional features"
    echo ""
    echo -e "  MemCP has a tiered dependency system. Core features work with zero"
    echo -e "  optional deps. Each extra unlocks better capabilities:"
    echo ""
    echo -e "    ${BOLD}search${NC}       BM25 ranked search (bm25s)             ${DIM}~5MB${NC}"
    echo -e "    ${BOLD}fuzzy${NC}        Typo-tolerant matching (rapidfuzz)      ${DIM}~2MB${NC}"
    echo -e "    ${BOLD}semantic${NC}     Vector embeddings (model2vec + numpy)   ${DIM}~40MB${NC}"
    echo -e "    ${BOLD}semantic-hq${NC}  High-quality embeddings (fastembed)     ${DIM}~200MB${NC}"
    echo -e "    ${BOLD}cache${NC}        Embedding disk cache (diskcache)        ${DIM}~1MB${NC}"
    echo ""

    local options=(
        "Core only        ${DIM}(keyword search, zero extra deps)${NC}"
        "Recommended      ${DIM}(search + fuzzy + semantic + cache — best balance)${NC}"
        "Everything       ${DIM}(all optional features)${NC}"
        "Custom           ${DIM}(choose individual extras)${NC}"
    )

    local choice
    choice=$(ask_choice "Which features do you want?" "${options[@]}")

    case "$choice" in
        1) EXTRAS="" ;;
        2) EXTRAS="search,fuzzy,semantic,cache" ;;
        3) EXTRAS="all" ;;
        4) choose_custom_extras ;;
        *) EXTRAS="search,fuzzy,semantic,cache" ;;
    esac

    if [[ -n "$EXTRAS" ]]; then
        print_ok "Selected extras: ${BOLD}${EXTRAS}${NC}"
    else
        print_ok "Core only (no extras)"
    fi
}

choose_custom_extras() {
    EXTRAS=""
    echo ""
    local extras_list=("search" "fuzzy" "semantic" "semantic-hq" "cache" "vectors")
    for extra in "${extras_list[@]}"; do
        if ask_yes_no "Install ${BOLD}${extra}${NC}?" "n"; then
            if [[ -n "$EXTRAS" ]]; then
                EXTRAS="${EXTRAS},${extra}"
            else
                EXTRAS="${extra}"
            fi
        fi
    done
}

# ── Install ───────────────────────────────────────────────────────────
run_install() {
    print_step 4 "Installing MemCP"
    echo ""

    case "$INSTALL_METHOD" in
        dev)  install_dev ;;
        pip)  install_pip ;;
        docker) install_docker ;;
    esac
}

install_dev() {
    local VENV_DIR="${PROJECT_DIR}/.venv"

    # Create venv if needed
    if [[ ! -d "$VENV_DIR" ]]; then
        print_arrow "Creating virtual environment..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        print_ok "Virtual environment created at .venv/"
    else
        print_info "Using existing virtual environment at .venv/"
    fi

    # Build install spec
    local INSTALL_SPEC=".[dev"
    if [[ -n "$EXTRAS" ]]; then
        INSTALL_SPEC="${INSTALL_SPEC},${EXTRAS}"
    fi
    INSTALL_SPEC="${INSTALL_SPEC}]"

    # Install
    print_arrow "Installing MemCP (editable) with extras: ${INSTALL_SPEC}..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip 2>/dev/null
    "${VENV_DIR}/bin/pip" install --quiet -e "${PROJECT_DIR}/${INSTALL_SPEC}" 2>&1 | tail -1 || true
    print_ok "MemCP installed in development mode"

    # Verify import
    if "${VENV_DIR}/bin/python" -c "import memcp; print(f'  MemCP v{memcp.__version__}')" 2>/dev/null; then
        print_ok "Import verification passed"
    else
        print_fail "Import verification failed"
        ERRORS=$((ERRORS+1))
    fi

    MEMCP_PYTHON="${VENV_DIR}/bin/python"
}

install_pip() {
    local VENV_DIR="${PROJECT_DIR}/.venv"

    # Create venv if needed
    if [[ ! -d "$VENV_DIR" ]]; then
        print_arrow "Creating virtual environment..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        print_ok "Virtual environment created at .venv/"
    else
        print_info "Using existing virtual environment at .venv/"
    fi

    # Build install spec
    local INSTALL_SPEC="."
    if [[ -n "$EXTRAS" ]]; then
        INSTALL_SPEC=".[${EXTRAS}]"
    fi

    # Install
    print_arrow "Installing MemCP with extras: ${INSTALL_SPEC}..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip 2>/dev/null
    "${VENV_DIR}/bin/pip" install --quiet "${PROJECT_DIR}/${INSTALL_SPEC}" 2>&1 | tail -1 || true
    print_ok "MemCP installed"

    # Verify import
    if "${VENV_DIR}/bin/python" -c "import memcp; print(f'  MemCP v{memcp.__version__}')" 2>/dev/null; then
        print_ok "Import verification passed"
    else
        print_fail "Import verification failed"
        ERRORS=$((ERRORS+1))
    fi

    MEMCP_PYTHON="${VENV_DIR}/bin/python"
}

install_docker() {
    print_arrow "Building Docker image..."
    if docker build -t memcp "${PROJECT_DIR}" --quiet 2>/dev/null; then
        print_ok "Docker image built: memcp"
    else
        print_fail "Docker build failed"
        ERRORS=$((ERRORS+1))
        return
    fi

    MEMCP_PYTHON="docker"
}

# ── MCP Registration ─────────────────────────────────────────────────
register_mcp() {
    print_step 5 "Register with Claude Code"
    echo ""

    if [[ "$CLAUDE_AVAILABLE" == "false" ]]; then
        print_warn "Claude CLI not available — skipping MCP registration"
        print_info "To register manually later:"
        if [[ "$INSTALL_METHOD" == "docker" ]]; then
            echo -e "    ${DIM}claude mcp add memcp -- docker run --rm -i -v ~/.memcp:/data -e MEMCP_DATA_DIR=/data memcp${NC}"
        else
            echo -e "    ${DIM}claude mcp add memcp ${MEMCP_PYTHON} -- -m memcp${NC}"
        fi
        return
    fi

    # Check if already registered
    if claude mcp list 2>/dev/null | grep -q "memcp"; then
        print_info "MemCP is already registered with Claude Code"
        if ask_yes_no "Re-register (replace existing)?" "n"; then
            claude mcp remove memcp 2>/dev/null || true
        else
            print_ok "Keeping existing registration"
            return
        fi
    fi

    # Ask for scope
    local options=(
        "user     ${DIM}(available in all projects — recommended)${NC}"
        "project  ${DIM}(available only in this project)${NC}"
    )
    local scope_choice
    scope_choice=$(ask_choice "Registration scope?" "${options[@]}")

    local SCOPE="user"
    case "$scope_choice" in
        2) SCOPE="project" ;;
        *) SCOPE="user" ;;
    esac

    # Register
    print_arrow "Registering MCP server (scope: ${SCOPE})..."
    if [[ "$INSTALL_METHOD" == "docker" ]]; then
        if claude mcp add memcp -s "$SCOPE" -- docker run --rm -i -v "${HOME}/.memcp:/data" -e MEMCP_DATA_DIR=/data memcp 2>/dev/null; then
            print_ok "MCP server registered (Docker)"
        else
            print_fail "MCP registration failed"
            print_info "Register manually: claude mcp add memcp -s ${SCOPE} -- docker run --rm -i -v ~/.memcp:/data -e MEMCP_DATA_DIR=/data memcp"
        fi
    else
        if claude mcp add memcp -s "$SCOPE" -- "${MEMCP_PYTHON}" -m memcp 2>/dev/null; then
            print_ok "MCP server registered"
        else
            print_fail "MCP registration failed"
            print_info "Register manually: claude mcp add memcp -s ${SCOPE} -- ${MEMCP_PYTHON} -m memcp"
        fi
    fi

    # Set up data directory
    print_arrow "Ensuring data directory..."
    mkdir -p "${HOME}/.memcp"
    print_ok "Data directory ready: ~/.memcp/"
}

# ── Deploy Sub-Agents ────────────────────────────────────────────────
deploy_agents() {
    print_step 6 "Deploy RLM sub-agents"
    echo ""

    echo -e "  MemCP includes 4 Claude Code sub-agents for the RLM map-reduce pipeline:"
    echo -e "    ${BOLD}memcp-analyzer${NC}          — Peek-identify-load-analyze (Haiku)"
    echo -e "    ${BOLD}memcp-mapper${NC}            — MAP phase for parallel chunk analysis (Haiku)"
    echo -e "    ${BOLD}memcp-synthesizer${NC}       — REDUCE phase for result synthesis (Sonnet)"
    echo -e "    ${BOLD}memcp-entity-extractor${NC}  — LLM-based entity extraction (Haiku)"
    echo ""

    local AGENTS_SRC="${PROJECT_DIR}/agents"
    local AGENTS_DST="${HOME}/.claude/agents"

    if [[ ! -d "$AGENTS_SRC" ]]; then
        print_warn "Agent templates not found at agents/"
        print_info "Sub-agents can be set up manually — see docs/ARCHITECTURE.md"
        return
    fi

    # Check if agents already exist
    local EXISTING_COUNT=0
    if [[ -d "$AGENTS_DST" ]]; then
        EXISTING_COUNT=$(find "$AGENTS_DST" -name "memcp-*.md" 2>/dev/null | wc -l | tr -d ' ')
    fi

    if [[ "$EXISTING_COUNT" -gt 0 ]]; then
        print_info "${EXISTING_COUNT} MemCP agent(s) already exist in ~/.claude/agents/"
        if ask_yes_no "Overwrite existing agents with latest templates?" "y"; then
            :  # continue to copy
        else
            print_ok "Keeping existing agents"
            return
        fi
    fi

    if ask_yes_no "Deploy sub-agents to ~/.claude/agents/ (user-level, all projects)?" "y"; then
        mkdir -p "$AGENTS_DST"

        local DEPLOYED=0
        for agent_file in "${AGENTS_SRC}"/memcp-*.md; do
            if [[ -f "$agent_file" ]]; then
                cp "$agent_file" "$AGENTS_DST/"
                DEPLOYED=$((DEPLOYED+1))
            fi
        done

        print_ok "${DEPLOYED} sub-agent(s) deployed to ~/.claude/agents/"

        # Show what was deployed
        for agent_file in "${AGENTS_DST}"/memcp-*.md; do
            if [[ -f "$agent_file" ]]; then
                local agent_name
                agent_name=$(basename "$agent_file" .md)
                echo -e "    ${DIM}  ${agent_name}${NC}"
            fi
        done
    else
        print_info "Skipping sub-agents — deploy later with:"
        echo -e "    ${DIM}mkdir -p ~/.claude/agents && cp agents/memcp-*.md ~/.claude/agents/${NC}"
    fi
}

# ── Setup Hooks ───────────────────────────────────────────────────────
setup_hooks() {
    print_step 7 "Configure auto-save hooks"

    local HOOK_SCRIPT="${PROJECT_DIR}/scripts/setup-hooks.sh"

    if [[ -f "$HOOK_SCRIPT" ]]; then
        QUIET=true bash "$HOOK_SCRIPT" install
    else
        print_warn "Hook setup script not found at scripts/setup-hooks.sh"
        print_info "Hooks can be set up manually — see docs/HOOKS.md"
    fi
}

# ── Deploy CLAUDE.md ──────────────────────────────────────────────────
deploy_claude_md() {
    print_step 8 "Deploy CLAUDE.md to project"
    echo ""

    echo -e "  CLAUDE.md provides session instructions for Claude Code:"
    echo -e "    When to save, tool quick reference, sub-agent patterns"
    echo ""

    local TEMPLATE="${PROJECT_DIR}/templates/CLAUDE.md"
    local TARGET_DIR
    TARGET_DIR="$(pwd)"
    local TARGET="${TARGET_DIR}/CLAUDE.md"

    if [[ ! -f "$TEMPLATE" ]]; then
        print_warn "CLAUDE.md template not found at templates/CLAUDE.md"
        return
    fi

    if [[ -f "$TARGET" ]]; then
        print_info "CLAUDE.md already exists in current directory"
        if ask_yes_no "Overwrite with latest template?" "n"; then
            :  # continue to copy
        else
            print_ok "Keeping existing CLAUDE.md"
            return
        fi
    fi

    if ask_yes_no "Deploy CLAUDE.md to current project directory?" "y"; then
        cp "$TEMPLATE" "$TARGET"
        print_ok "CLAUDE.md deployed to ${TARGET_DIR}/CLAUDE.md"
    else
        print_info "Skipping — copy manually with:"
        echo -e "    ${DIM}cp ${PROJECT_DIR}/templates/CLAUDE.md ./CLAUDE.md${NC}"
    fi
}

# ── Summary ───────────────────────────────────────────────────────────
show_summary() {
    echo ""
    separator
    echo ""

    if [[ $ERRORS -gt 0 ]]; then
        echo -e "  ${YELLOW}${BOLD}Installation completed with ${ERRORS} warning(s).${NC}"
    else
        echo -e "  ${GREEN}${BOLD}Installation complete!${NC} 🎉"
    fi

    echo ""
    echo -e "  ${BOLD}What was set up:${NC}"
    echo -e "    ${CHECK} MemCP server installed (${INSTALL_METHOD})"
    if [[ -n "${EXTRAS:-}" ]]; then
        echo -e "    ${CHECK} Optional features: ${EXTRAS}"
    fi
    if [[ "$CLAUDE_AVAILABLE" == "true" ]]; then
        echo -e "    ${CHECK} MCP server registered with Claude Code"
    fi
    echo -e "    ${CHECK} Data directory: ~/.memcp/"
    if [[ -d "${HOME}/.claude/agents" ]]; then
        local AGENT_COUNT
        AGENT_COUNT=$(find "${HOME}/.claude/agents" -name "memcp-*.md" 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$AGENT_COUNT" -gt 0 ]]; then
            echo -e "    ${CHECK} ${AGENT_COUNT} RLM sub-agent(s) in ~/.claude/agents/"
        fi
    fi
    if [[ -f "${HOME}/.claude/settings.json" ]]; then
        echo -e "    ${CHECK} Auto-save hooks in ~/.claude/settings.json"
    fi
    if [[ -f "$(pwd)/CLAUDE.md" ]]; then
        echo -e "    ${CHECK} CLAUDE.md deployed to project"
    fi

    echo ""
    echo -e "  ${BOLD}Next steps:${NC}"
    echo -e "    1. Start a Claude Code session"
    echo -e "    2. Type: ${CYAN}memcp_ping()${NC} to verify the server is running"
    echo -e "    3. Try:  ${CYAN}memcp_remember(\"First insight!\", category=\"fact\")${NC}"
    echo -e "    4. Then: ${CYAN}memcp_recall(query=\"insight\")${NC}"

    echo ""
    echo -e "  ${BOLD}Useful commands:${NC}"
    echo -e "    ${DIM}memcp_status()${NC}              — Memory statistics"
    echo -e "    ${DIM}memcp_recall(importance=\"critical\")${NC} — Load critical rules"
    echo -e "    ${DIM}memcp_search(\"keyword\")${NC}      — Search across all stored content"
    echo -e "    ${DIM}memcp_graph_stats()${NC}          — Knowledge graph overview"

    echo ""
    echo -e "  ${BOLD}Documentation:${NC}"
    echo -e "    ${DIM}docs/TOOLS.md${NC}        — All 21 tools reference"
    echo -e "    ${DIM}docs/ARCHITECTURE.md${NC} — System design"
    echo -e "    ${DIM}docs/SEARCH.md${NC}       — Search system"
    echo -e "    ${DIM}docs/GRAPH.md${NC}        — MAGMA graph memory"
    echo -e "    ${DIM}docs/HOOKS.md${NC}        — Auto-save hooks"

    echo ""
    separator
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────
main() {
    show_banner
    preflight_checks
    choose_install_method
    choose_extras
    run_install
    register_mcp
    deploy_agents
    setup_hooks
    deploy_claude_md
    show_summary
}

main "$@"
