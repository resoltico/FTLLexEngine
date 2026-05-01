#!/usr/bin/env bash

set -euo pipefail

PY_VERSION="${PY_VERSION:-3.13}"
if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" == "1" ]]; then
    UV_ENV=".venv-devcontainer-${PY_VERSION}"
else
    UV_ENV=".venv-${PY_VERSION}"
fi
if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" == "1" && -z "${UV_LINK_MODE:-}" ]]; then
    export UV_LINK_MODE="copy"
fi
ATHERIS_TARGET_SMOKE_TIME="${ATHERIS_TARGET_SMOKE_TIME:-3}"

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" != "1" ]]; then
    printf 'Error: ./check.sh must be run inside the committed contributor devcontainer.\n' >&2
    printf 'Use the Dev Containers extension or:\n' >&2
    printf '  npx --yes @devcontainers/cli up --workspace-folder .\n' >&2
    printf '  npx --yes @devcontainers/cli exec --workspace-folder . ./check.sh\n' >&2
    exit 1
fi

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
run_step "Contributor Devcontainer" ./scripts/validate-devcontainer.sh
run_step "Documentation Validation" uv_python scripts/validate_docs.py
run_step "Examples" uv_python scripts/run_examples.py
run_step "Lint" ./scripts/lint.sh
run_step "Tests" ./scripts/test.sh
run_step "HypoFuzz Preflight" ./scripts/fuzz_hypofuzz.sh --preflight
run_step "Atheris Corpus Health" ./scripts/fuzz_atheris.sh --corpus
run_step "Atheris Manifest Smoke" ./scripts/fuzz_atheris.sh --smoke-all --time "$ATHERIS_TARGET_SMOKE_TIME"

printf '\n[PASS] Full repository check completed.\n'
