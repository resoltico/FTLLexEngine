#!/usr/bin/env bash

if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
elif [[ ! -t 1 ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

HAS_PSUTIL=false
python -c "import psutil" 2>/dev/null && HAS_PSUTIL=true || true

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end()   { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_fail() { echo -e "${RED}[FAIL]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }

format_bytes() {
    local bytes="$1"
    if (( bytes >= 1048576 )); then
        printf "%d MiB" $((bytes / 1048576))
    elif (( bytes >= 1024 )); then
        printf "%d KiB" $((bytes / 1024))
    else
        printf "%d B" "$bytes"
    fi
}

last_nonempty_log_line() {
    local log_file="$1"
    local last_line
    last_line=$(awk 'NF { line = $0 } END { print line }' "$log_file" 2>/dev/null || true)
    last_line=${last_line//$'\r'/}
    if [[ -z "$last_line" ]]; then
        echo "awaiting first output"
        return 0
    fi
    if (( ${#last_line} > 160 )); then
        echo "${last_line:0:157}..."
        return 0
    fi
    echo "$last_line"
}

_heartbeat_daemon() {
    local watched_pid="$1" log_file="$2" start_sec="$3"
    local prev_last_line="" prev_change_sec=$SECONDS
    sleep 5
    while kill -0 "$watched_pid" 2>/dev/null; do
        local elapsed=$(( SECONDS - start_sec ))
        local log_bytes=0
        [[ -f "$log_file" ]] && log_bytes=$(wc -c < "$log_file" | tr -d '[:space:]')
        local raw_last_line last_display
        raw_last_line=$(last_nonempty_log_line "$log_file")
        if [[ "$raw_last_line" == "$prev_last_line" ]]; then
            local unchanged_sec=$(( SECONDS - prev_change_sec ))
            last_display="(no new output, ${unchanged_sec}s)"
        else
            last_display="$raw_last_line"
            prev_last_line="$raw_last_line"
            prev_change_sec=$SECONDS
        fi
        if [[ "$HAS_PSUTIL" == "true" ]]; then
            local stats
            stats=$(python -c "
import psutil
try:
    p = psutil.Process(${watched_pid})
    all_procs = [p] + p.children(recursive=True)
    cpu = sum(x.cpu_percent(interval=0.2) for x in all_procs)
    mem_mb = sum(x.memory_info().rss for x in all_procs) // 1048576
    print(f'CPU={cpu:.0f}% MEM={mem_mb}MB procs={len(all_procs)}')
except Exception:
    print('CPU=? MEM=? procs=?')
" 2>/dev/null || echo "CPU=? MEM=? procs=?")
            echo "[HEARTBEAT] T+${elapsed}s | ${stats} | log=$(format_bytes "$log_bytes") | last: ${last_display}" >&2
        else
            echo "[HEARTBEAT] T+${elapsed}s | log=$(format_bytes "$log_bytes") | last: ${last_display}" >&2
        fi
        sleep "$HEARTBEAT_INTERVAL_SEC"
    done
}

_run_with_heartbeat() {
    local log_file="$1" append="$2"; shift 2
    if [[ "$1" == "--" ]]; then shift; fi
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"

    "$@" > "$fifo" 2>&1 &
    local cmd_pid=$!
    PID_LIST+=("$cmd_pid")

    local hb_pid=0
    if [[ "$HEARTBEAT_ENABLED" == "true" && "$HEARTBEAT_INTERVAL_SEC" -gt 0 ]]; then
        _heartbeat_daemon "$cmd_pid" "$log_file" "$SECONDS" &
        hb_pid=$!
        PID_LIST+=("$hb_pid")
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        if [[ "$append" == "true" ]]; then
            tee -a "$log_file" < "$fifo" || true
        else
            tee "$log_file" < "$fifo" || true
        fi
    else
        if [[ "$append" == "true" ]]; then
            cat < "$fifo" >> "$log_file" || true
        else
            cat < "$fifo" > "$log_file" || true
        fi
    fi

    wait "$cmd_pid" 2>/dev/null
    local exit_code=$?

    if [[ "$hb_pid" -gt 0 ]]; then
        kill "$hb_pid" 2>/dev/null || true
        wait "$hb_pid" 2>/dev/null || true
    fi

    PID_LIST=()

    rm -f "$fifo"
    return "$exit_code"
}

run_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"

    echo "[ INFO ] Script               : $SCRIPT_NAME v$SCRIPT_VERSION"

    local python_version
    python_version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo "[  OK  ] Python               : $python_version"

    if python -c "import hypothesis" &>/dev/null; then
        local hypo_version
        hypo_version=$(python -c "import hypothesis; print(hypothesis.__version__)")
        echo "[  OK  ] Hypothesis           : $hypo_version"
    else
        echo "[ FAIL ] Hypothesis           : MISSING"
        log_err "Hypothesis not installed. Run 'uv sync' to install dependencies."
        exit 1
    fi

    log_pass "System is ready."
    log_group_end
}

_on_exit() {
    local exit_code=$?
    local pid
    for pid in "${PID_LIST[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    [[ ${#PID_LIST[@]} -gt 0 ]] && wait "${PID_LIST[@]}" 2>/dev/null || true
    echo "[EXIT-CODE] $exit_code" >&2
}

_on_signal() {
    _SIGNAL_RECEIVED=true
    local pid
    for pid in "${PID_LIST[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    PID_LIST=()
}
