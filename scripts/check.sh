#!/usr/bin/env bash
# Lint, format check, type check and the default (model-free) test run.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run mypy src
uv run pytest
