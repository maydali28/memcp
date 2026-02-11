.DEFAULT_GOAL := help

PYTHON   ?= python3
SRC_DIRS := src/ tests/

# ──────────────────────────────────────────────
#  Install / Uninstall
# ──────────────────────────────────────────────

.PHONY: setup
setup: ## Interactive install (MCP registration, agents, hooks)
	bash scripts/install.sh

.PHONY: teardown
teardown: ## Interactive uninstall (remove everything)
	bash scripts/uninstall.sh

.PHONY: dev
dev: ## Set up local dev environment (venv + all extras + pre-commit)
	$(PYTHON) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[all]"
	.venv/bin/pre-commit install
	@echo "\nReady — run:  source .venv/bin/activate"

# ──────────────────────────────────────────────
#  Quality
# ──────────────────────────────────────────────

.PHONY: lint
lint: ## Lint + format check (same as CI)
	ruff check $(SRC_DIRS)
	ruff format --check $(SRC_DIRS)

.PHONY: fmt
fmt: ## Auto-fix lint errors and format code
	ruff check $(SRC_DIRS) --fix
	ruff format $(SRC_DIRS)

# ──────────────────────────────────────────────
#  Test
# ──────────────────────────────────────────────

.PHONY: test
test: ## Run unit tests
	pytest tests/unit/ -v --tb=short

.PHONY: test-all
test-all: ## Run unit + benchmark tests
	pytest tests/ -v --tb=short

.PHONY: benchmark
benchmark: ## Run benchmark suite
	pytest tests/benchmark/ --benchmark-only -v

# ──────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────

.PHONY: run
run: ## Start the MCP server
	$(PYTHON) -m memcp

.PHONY: docker
docker: ## Build and run via Docker Compose
	docker-compose up --build

# ──────────────────────────────────────────────
#  Build / Clean
# ──────────────────────────────────────────────

.PHONY: build
build: clean ## Build source and wheel distributions
	$(PYTHON) -m build

.PHONY: clean
clean: ## Remove build, cache, and test artifacts
	rm -rf dist/ build/ htmlcov/ .coverage
	find . -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/

# ──────────────────────────────────────────────
#  Help
# ──────────────────────────────────────────────

.PHONY: help
help: ## Show available targets
	@printf "\n\033[1mMemCP — Makefile targets\033[0m\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@printf "\n"
