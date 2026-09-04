# Local env file, provisioned from .env.example on `just install`
_env := ".env"

# Default recipe to run when just is called without arguments
default:
    @just --list

# Create virtual environment and install dependencies
venv:
    pip install uv
    uv venv
    source .venv/bin/activate
    @just install

# Install dependencies (provisions .env from the template on first run)
install:
    @test -f {{_env}} || cp .env.example {{_env}}
    @just install-hooks
    uv pip install -e ".[dev]"
    uv sync --all-extras

# Install git hooks (points core.hooksPath at .githooks; idempotent, safe to re-run)
install-hooks:
    git config core.hooksPath .githooks

# Update dependencies
update:
    uv pip install -e ".[dev]"
    uv lock --upgrade

# Run tests
test:
    uv run pytest

# Run all tests
test-all:
    @just test
    @just format
    @just lint
    @just typecheck

# Run linting
lint:
    uv run ruff check .
    uv run ruff format --check .

# Format code
format:
    uv run ruff format .

# Run type checking
typecheck:
    uv run basedpyright

# Convert a SEC filing (format: holon | tavi | both; defaults into ./output/)
build cik accno format="holon" out="":
    uv run xbrlkit build --cik {{cik}} --accno {{accno}} --format {{format}} {{ if out == "" { "" } else { "-o " + out } }}

# Fetch and convert the latest filing for a ticker (into ./output/)
fetch ticker format="holon":
    uv run xbrlkit fetch --ticker {{ticker}} --format {{format}}

# Build python package locally (for testing)
build-package:
    python -m build

# Create a feature branch
create-feature branch_type="feature" branch_name="" base_branch="main" update="no":
    bin/create-feature.sh {{branch_type}} {{branch_name}} {{base_branch}} {{update}}

# Version management
create-release type="patch":
    bin/create-release.sh {{type}}

# Clean up development artifacts
clean:
    rm -rf .pytest_cache
    rm -rf .ruff_cache
    rm -rf __pycache__
    rm -rf xbrlkit.egg-info
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Show help
help:
    @just --list
