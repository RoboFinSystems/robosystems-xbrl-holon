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
    uv pip install -e ".[dev]"
    uv sync --all-extras

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

# Build a holon.jsonld from a SEC filing (defaults into ./output/)
holon-build cik accno out="":
    uv run holon build --cik {{cik}} --accno {{accno}} {{ if out == "" { "" } else { "-o " + out } }}

# Fetch the latest filing for a ticker (into ./output/)
holon-fetch ticker:
    uv run holon fetch --ticker {{ticker}}

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
    rm -rf robosystems_xbrl_holon.egg-info
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Show help
help:
    @just --list
