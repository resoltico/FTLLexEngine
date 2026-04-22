#!/usr/bin/env bash

set -euo pipefail

PY_VERSION="${PY_VERSION:-3.13}"
UV_ENV=".venv-${PY_VERSION}"
ATHERIS_SMOKE_TIME="${ATHERIS_SMOKE_TIME:-5}"

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

run_step() {
    local title="$1"
    shift
    printf '\n== %s ==\n' "$title"
    "$@"
}

uv_python() {
    UV_PROJECT_ENVIRONMENT="$UV_ENV" uv run --python "$PY_VERSION" --group dev python "$@"
}

run_step "Version Validation" uv_python scripts/validate_version.py
run_step "Documentation Validation" uv_python scripts/validate_docs.py
run_step "Examples" uv_python scripts/run_examples.py
run_step "Lint" ./scripts/lint.sh
run_step "Tests" ./scripts/test.sh
run_step "HypoFuzz Preflight" ./scripts/fuzz_hypofuzz.sh --preflight
run_step "Atheris Corpus Health" ./scripts/fuzz_atheris.sh --corpus
run_step "Atheris Graph Smoke" ./scripts/fuzz_atheris.sh graph --time "$ATHERIS_SMOKE_TIME"
run_step "Atheris Introspection Smoke" ./scripts/fuzz_atheris.sh introspection --time "$ATHERIS_SMOKE_TIME"

printf '\n[PASS] Full repository check completed.\n'
