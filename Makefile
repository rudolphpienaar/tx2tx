# tx2tx Development Makefile
#
# Quick start:
#   make venv      - Create virtual environment
#   make dev       - Install in editable mode with dev dependencies
#   make install   - Install package
#   make test      - Run tests
#   make lint      - Run linters
#   make clean     - Remove build artifacts

VENV_DIR := .venv
VENV_BIN := $(VENV_DIR)/bin
UV ?= uv
REQUIREMENTS := requirements.txt

.PHONY: help venv dev install test lint format typecheck clean purge shell

help:
	@echo "tx2tx development targets:"
	@echo "  make venv       - Create virtual environment"
	@echo "  make dev        - Install in editable mode with dev dependencies"
	@echo "  make install    - Install package (production)"
	@echo "  make shell      - Start shell with activated virtual environment"
	@echo "  make test       - Run pytest"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Run black formatter"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make clean      - Remove build artifacts"
	@echo "  make purge      - Remove build artifacts AND virtual environment"

venv:
	test -d $(VENV_DIR) || python3 -m venv $(VENV_DIR)
	@echo "Virtual environment created. Activate with: source $(VENV_BIN)/activate"

dev: venv
	$(VENV_BIN)/pip install -e ./
	@echo "Installed tx2tx in editable mode"

install: venv
	$(VENV_BIN)/pip install ./
	@echo "Installed tx2tx"

test:
	$(VENV_BIN)/pytest -q

lint:
	$(VENV_BIN)/ruff check .

format:
	$(VENV_BIN)/black .

typecheck:
	$(VENV_BIN)/mypy tx2tx

clean:
	rm -rf build/ dist/ *.egg-info .mypy_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

purge: clean
	rm -rf $(VENV_DIR)
	@echo "Removed virtual environment"

shell: venv
	@echo "Starting shell with activated venv (exit to return)..."
	@zsh -c "source $(VENV_BIN)/activate && exec zsh"
