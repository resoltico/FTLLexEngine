#!/usr/bin/env bash

readonly TARGET_VENV=".venv-devcontainer-atheris"
readonly ATHERIS_TARGETS_FILE="$PROJECT_ROOT/fuzz_atheris/targets.tsv"
# shellcheck disable=SC2034
readonly ATHERIS_CORPUS_ROOT="$PROJECT_ROOT/.fuzz_atheris_corpus"
# shellcheck disable=SC2034
readonly ATHERIS_REPLAY_SCRIPT="$PROJECT_ROOT/fuzz_atheris/fuzz_atheris_replay_finding.py"
# shellcheck disable=SC2034
readonly ATHERIS_HEALTH_SCRIPT="$PROJECT_ROOT/scripts/fuzz_atheris_corpus_health.py"

if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" == "1" && -z "${UV_LINK_MODE:-}" ]]; then
    export UV_LINK_MODE="copy"
fi

declare -A TARGET_SCRIPTS=()
# shellcheck disable=SC2034
declare -A TARGET_DESCRIPTIONS=()
declare -a TARGET_ORDER=()

if [[ -t 1 && "${QUIET:-0}" -eq 0 ]]; then
    RED='\033[31m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    BLUE='\033[34m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' RESET=''
fi

die() {
    printf '%serror:%s %s\n' "$RED" "$RESET" "$1" >&2
    exit 1
}

log_info() {
    if [[ "${QUIET:-0}" -eq 0 ]]; then
        printf '%s[INFO]%s %s\n' "$BLUE" "$RESET" "$1"
    fi
}

log_warn() {
    printf '%s[WARN]%s %s\n' "$YELLOW" "$RESET" "$1" >&2
}

log_pass() {
    if [[ "${QUIET:-0}" -eq 0 ]]; then
        printf '%s[PASS]%s %s\n' "$GREEN" "$RESET" "$1"
    fi
}

require_file() {
    local path="$1"
    [[ -f "$path" ]] || die "missing required file: $path"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

load_target_registry() {
    local name=""
    local module=""
    local description=""

    require_file "$ATHERIS_TARGETS_FILE"

    while IFS=$'\t' read -r name module description; do
        [[ -z "$name" ]] && continue
        [[ "$name" == \#* ]] && continue
        [[ -n "$module" ]] || die "malformed Atheris target row for $name"
        [[ -n "$description" ]] || die "missing description for Atheris target $name"

        TARGET_ORDER+=("$name")
        TARGET_SCRIPTS["$name"]="$PROJECT_ROOT/fuzz_atheris/$module"
        # shellcheck disable=SC2034
        TARGET_DESCRIPTIONS["$name"]="$description"
    done < "$ATHERIS_TARGETS_FILE"

    [[ "${#TARGET_ORDER[@]}" -gt 0 ]] || die "Atheris target registry is empty"

    for name in "${TARGET_ORDER[@]}"; do
        require_file "${TARGET_SCRIPTS[$name]}"
    done
}

target_script_for() {
    local target="$1"
    local script_path="${TARGET_SCRIPTS[$target]:-}"
    [[ -n "$script_path" ]] || die "unknown target: $target"
    printf '%s\n' "$script_path"
}

require_known_target() {
    local target="$1"
    [[ -n "${TARGET_SCRIPTS[$target]:-}" ]] || die "unknown target: $target"
}

require_devcontainer() {
    if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" != "1" ]]; then
        die "Atheris runs only inside the committed contributor devcontainer.
Use:
  npx --yes @devcontainers/cli up --workspace-folder .
  npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --help"
    fi
}

mode_requires_atheris_env() {
    case "$1" in
        setup|corpus|smoke|minimize|replay|fuzz)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

pivot_to_atheris_env() {
    if [[ "${UV_PROJECT_ENVIRONMENT:-}" == "$TARGET_VENV" ]]; then
        unset ATHERIS_ALREADY_PIVOTED
        return 0
    fi

    [[ "${ATHERIS_ALREADY_PIVOTED:-0}" != "1" ]] || die "recursive uv environment pivot detected"
    require_command uv

    log_info "Pivoting to isolated Atheris environment: ${TARGET_VENV}"
    export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
    export ATHERIS_ALREADY_PIVOTED=1
    unset VIRTUAL_ENV
    exec uv run --python "$PY_VERSION" --group dev --group atheris --locked "${BASH:-bash}" "$0" "$@"
}

check_atheris_environment() {
    local clang_bin="${CLANG_BIN:-$(command -v clang)}"
    local clang_resource_dir=""
    local libfuzzer_path=""

    [[ -n "$clang_bin" ]] || die "clang toolchain not found in contributor environment"
    clang_resource_dir="$("$clang_bin" --print-resource-dir 2>/dev/null || true)"
    [[ -n "$clang_resource_dir" ]] || die "unable to resolve clang resource directory for ${clang_bin}"
    libfuzzer_path="$(find "$clang_resource_dir" -name 'libclang_rt.fuzzer*.a' | head -1)"
    [[ -n "$libfuzzer_path" ]] || die "libFuzzer runtime archive not found under ${clang_resource_dir}"

    printf 'Clang       : %s\n' "$clang_bin"
    printf 'LibFuzzer   : %s\n' "$libfuzzer_path"
    python - <<'PY'
from __future__ import annotations

import platform
import sys

import atheris  # type: ignore[import-not-found]
import ftllexengine
import psutil

version = sys.version_info
if (version.major, version.minor) != (3, 13):
    raise SystemExit(
        "expected Python 3.13 in the dedicated Atheris environment, "
        f"got {sys.version.split()[0]}"
    )

print(f"Python      : {sys.version.split()[0]}")
print(f"Platform    : {platform.platform()}")
print(f"Atheris     : {getattr(atheris, '__version__', 'unknown')}")
print(f"psutil      : {psutil.__version__}")
print(f"ftllexengine: {ftllexengine.__version__}")
PY
}
