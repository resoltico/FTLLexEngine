#!/usr/bin/env bash
# Native Atheris/libFuzzer entrypoint for FTLLexEngine.

export PATH="/usr/bin:/bin:${PATH:-}"

if [[ "${BASH_VERSINFO[0]}" -lt 5 ]]; then
    echo "Error: Bash 5.0+ required (current: ${BASH_VERSION})." >&2
    exit 1
fi

set -o errexit
set -o nounset
set -o pipefail
shopt -s inherit_errexit

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=scripts/lib/python_support_contract.sh
source "$PROJECT_ROOT/scripts/lib/python_support_contract.sh"

# Premise: the native Atheris lane must follow the same minimum-version owner
# as the rest of the repository gates.
# Reason: keeping the interpreter default in one contract file prevents the
# native-fuzz lane from silently diverging from the supported floor.
PY_VERSION="${PY_VERSION:-$FTLLEXENGINE_PYTHON_MIN}"
WORKERS=1
TIME_LIMIT=""
TARGET=""
MODE="fuzz"
MINIMIZE_TARGET=""
MINIMIZE_FILE=""
REPLAY_TARGET=""
REPLAY_DIR=""
QUIET=0
VERBOSE=0
DRY_RUN=0
ORIGINAL_ARGS=("$@")

readonly FUZZ_LIB_DIR="$SCRIPT_DIR/lib/fuzz_atheris"

require_fuzz_lib() {
    local path="$1"
    [[ -f "$path" ]] || {
        echo "Error: Missing Atheris helper library: $path" >&2
        exit 1
    }
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --setup)
            MODE="setup"
            shift
            if [[ $# -gt 0 && "$1" != --* ]]; then
                TARGET="$1"
                shift
            fi
            ;;
        --list)
            MODE="list"
            shift
            ;;
        --corpus)
            MODE="corpus"
            shift
            ;;
        --smoke-all)
            MODE="smoke"
            shift
            ;;
        --minimize)
            [[ $# -ge 3 ]] || {
                echo "Error: --minimize requires TARGET and FILE." >&2
                exit 1
            }
            MODE="minimize"
            MINIMIZE_TARGET="$2"
            MINIMIZE_FILE="$3"
            shift 3
            ;;
        --replay)
            [[ $# -ge 2 ]] || {
                echo "Error: --replay requires TARGET." >&2
                exit 1
            }
            MODE="replay"
            REPLAY_TARGET="$2"
            shift 2
            if [[ $# -gt 0 && "$1" != --* ]]; then
                REPLAY_DIR="$1"
                shift
            fi
            ;;
        --report)
            [[ $# -ge 2 ]] || {
                echo "Error: --report requires TARGET." >&2
                exit 1
            }
            MODE="report"
            TARGET="$2"
            shift 2
            ;;
        --clean)
            [[ $# -ge 2 ]] || {
                echo "Error: --clean requires TARGET." >&2
                exit 1
            }
            MODE="clean"
            TARGET="$2"
            shift 2
            ;;
        --workers)
            [[ $# -ge 2 && "$2" =~ ^[1-9][0-9]*$ ]] || {
                echo "Error: --workers requires a positive integer." >&2
                exit 1
            }
            WORKERS="$2"
            shift 2
            ;;
        --time)
            [[ $# -ge 2 && "$2" =~ ^[1-9][0-9]*$ ]] || {
                echo "Error: --time requires a positive integer." >&2
                exit 1
            }
            TIME_LIMIT="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=1
            shift
            ;;
        --quiet)
            QUIET=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --help|-h)
            MODE="help"
            shift
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            [[ -z "$TARGET" && "$MODE" == "fuzz" ]] || {
                echo "Error: Unexpected positional argument: $1" >&2
                exit 1
            }
            TARGET="$1"
            shift
            ;;
    esac
done

require_fuzz_lib "$FUZZ_LIB_DIR/common.sh"
require_fuzz_lib "$FUZZ_LIB_DIR/commands.sh"

# shellcheck source=scripts/lib/fuzz_atheris/common.sh
source "$FUZZ_LIB_DIR/common.sh"
# shellcheck source=scripts/lib/fuzz_atheris/commands.sh
source "$FUZZ_LIB_DIR/commands.sh"

load_target_registry

if mode_requires_atheris_env "$MODE"; then
    require_devcontainer
    pivot_to_atheris_env "${ORIGINAL_ARGS[@]}"
fi

case "$MODE" in
    help)
        show_help
        ;;
    setup)
        run_setup
        ;;
    list)
        run_list
        ;;
    corpus)
        run_corpus_health
        ;;
    smoke)
        run_smoke_all
        ;;
    minimize)
        run_minimize "$MINIMIZE_TARGET" "$MINIMIZE_FILE"
        ;;
    replay)
        run_replay "$REPLAY_TARGET" "$REPLAY_DIR"
        ;;
    report)
        require_known_target "$TARGET"
        parse_and_display_report "$TARGET"
        ;;
    clean)
        run_clean "$TARGET"
        ;;
    fuzz)
        if [[ -z "$TARGET" ]]; then
            show_help
            exit 0
        fi
        run_fuzz_target "$TARGET"
        ;;
esac
