#!/usr/bin/env bash

run_deep() {
    run_diagnostics

    local -a fuzz_uv=(uv run --group fuzz --python "$PY_VERSION")
    local deep_tooling
    if ! deep_tooling="$("${fuzz_uv[@]}" python <<'PYEOF'
import click
import hypofuzz
import hypothesis

print(f"Hypothesis CLI     : {hypothesis.__version__}")
print(f"HypoFuzz           : {hypofuzz.__version__}")
print(f"Click              : {click.__version__}")
PYEOF
)"; then
        log_err "Deep fuzzing tooling is unavailable in the fuzz dependency group."
        log_err "Run 'uv sync --group fuzz' or fix pyproject.toml dependency-groups.fuzz."
        return 1
    fi

    if [[ "$METRICS" == "true" ]]; then
        log_group_start "Deep Fuzzing (pytest with metrics)"
    else
        log_group_start "Continuous HypoFuzz"
    fi

    export HYPOTHESIS_PROFILE="hypofuzz"

    local log_file="$PROJECT_ROOT/.hypothesis/hypofuzz.log"
    mkdir -p "$PROJECT_ROOT/.hypothesis"
    log_info "Tooling:"
    while IFS= read -r line; do
        log_info "  $line"
    done <<< "$deep_tooling"

    if [[ "$METRICS" == "true" ]]; then
        export STRATEGY_METRICS="1"
        export STRATEGY_METRICS_DETAILED="1"
        export STRATEGY_METRICS_LIVE="1"
        export STRATEGY_METRICS_INTERVAL="10"
        log_info "Metrics: Per-strategy breakdown enabled (10s interval)"
        log_info "Metrics: Using pytest (HypoFuzz multiprocessing incompatible with metrics)"
        log_info "Profile: hypofuzz (deadline=None)"

        {
            echo ""
            echo "================================================================================"
            echo "Metrics Session (pytest -m fuzz): $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Profile: hypofuzz"
            echo "================================================================================"
        } >> "$log_file"

        local exit_code=0
        set +e
        _run_with_heartbeat "$log_file" true -- "${fuzz_uv[@]}" pytest tests/ -m fuzz -v --tb=short
        exit_code=$?
        set -e

        if [[ $exit_code -ne 0 ]]; then
            log_fail "Metrics session failed (exit $exit_code). Last 80 lines of log:"
            tail -n 80 "$log_file"
        fi

        python << METRICS_PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$log_file")
exit_code = $exit_code
try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

summary_match = re.search(r'=+ (.*?) =+\n*$', log_content, re.MULTILINE)
summary_text = summary_match.group(1) if summary_match else ""
passed_m = re.search(r'(\d+) passed', summary_text)
failed_m = re.search(r'(\d+) failed', summary_text)
skipped_m = re.search(r'(\d+) skipped', summary_text)
hypo_count = log_content.count('Falsifying example')

report = {
    'script': '$SCRIPT_NAME',
    'script_version': '$SCRIPT_VERSION',
    'mode': 'deep_metrics',
    'status': 'pass' if exit_code == 0 else 'fail',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'tests_passed': int(passed_m.group(1)) if passed_m else 0,
    'tests_failed': int(failed_m.group(1)) if failed_m else 0,
    'tests_skipped': int(skipped_m.group(1)) if skipped_m else 0,
    'hypothesis_failures': hypo_count,
    'exit_code': exit_code,
    'log_file': str(log_path),
}
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps(report, indent=2))
print('[SUMMARY-JSON-END]')
METRICS_PYEOF

        log_group_end
        return "$exit_code"
    fi

    if [[ -n "$TIME_LIMIT" ]]; then
        log_info "Time Limit: ${TIME_LIMIT}s"
    else
        log_info "Time Limit: Until Ctrl+C"
    fi
    log_info "Workers: $WORKERS"
    log_info "Profile: hypofuzz (deadline=None)"

    local session_log_start=0
    [[ -f "$log_file" ]] && session_log_start=$(wc -c < "$log_file" | tr -d ' ')

    local exit_code=0
    local teardown_race_detected=false
    local restart_count=0
    local max_teardown_restarts=20

    if [[ -n "$TIME_LIMIT" ]]; then
        {
            echo ""
            echo "================================================================================"
            echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Script: $SCRIPT_NAME v$SCRIPT_VERSION"
            echo "Workers: $WORKERS"
            echo "Profile: hypofuzz"
            echo "================================================================================"
        } >> "$log_file"

        local run_log_start=0
        [[ -f "$log_file" ]] && run_log_start=$(wc -c < "$log_file" | tr -d ' ')

        set +e
        _run_with_heartbeat "$log_file" true -- timeout "$TIME_LIMIT" "${fuzz_uv[@]}" hypothesis fuzz --no-dashboard -n "$WORKERS" tests/fuzz/
        exit_code=$?
        set -e
        [[ $exit_code -eq 124 ]] && exit_code=0

        if [[ "$_SIGNAL_RECEIVED" == "true" && $exit_code -ne 0 ]]; then exit_code=130; fi

        local _log_window
        _log_window=$(tail -c "+$((run_log_start + 1))" "$log_file" 2>/dev/null || true)
        if [[ $exit_code -ne 0 && $exit_code -ne 130 && $exit_code -ne 120 ]] \
            && [[ -f "$log_file" ]] \
            && echo "$_log_window" | grep -qF "_start_worker" 2>/dev/null \
            && echo "$_log_window" | grep -qF "managers.py" 2>/dev/null; then
            log_warn "Worker teardown race detected (HypoFuzz bug, exit $exit_code)."
            log_warn "Worker crashed on Manager proxy access after shutdown - no test failures."
            log_warn "Re-run ./scripts/fuzz_hypofuzz.sh --deep to continue (database is preserved)."
            teardown_race_detected=true
            exit_code=0
        fi
    else
        while true; do
            local run_log_start=0
            [[ -f "$log_file" ]] && run_log_start=$(wc -c < "$log_file" | tr -d ' ')

            {
                echo ""
                echo "================================================================================"
                if [[ $restart_count -eq 0 ]]; then
                    echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')"
                else
                    echo "HypoFuzz Restart #${restart_count}: $(date '+%Y-%m-%d %H:%M:%S')"
                fi
                echo "Script: $SCRIPT_NAME v$SCRIPT_VERSION"
                echo "Workers: $WORKERS"
                echo "Profile: hypofuzz"
                echo "================================================================================"
            } >> "$log_file"

            set +e
            _run_with_heartbeat "$log_file" true -- "${fuzz_uv[@]}" hypothesis fuzz --no-dashboard -n "$WORKERS" tests/fuzz/
            exit_code=$?
            set -e

            if [[ "$_SIGNAL_RECEIVED" == "true" ]]; then
                [[ $exit_code -ne 0 ]] && exit_code=130
                break
            fi

            [[ $exit_code -eq 0 || $exit_code -eq 120 ]] && break

            local _log_window
            _log_window=$(tail -c "+$((run_log_start + 1))" "$log_file" 2>/dev/null || true)
            if [[ $exit_code -ne 130 ]] \
                && [[ -f "$log_file" ]] \
                && echo "$_log_window" | grep -qF "_start_worker" 2>/dev/null \
                && echo "$_log_window" | grep -qF "managers.py" 2>/dev/null; then

                teardown_race_detected=true
                (( restart_count++ )) || true

                if [[ $restart_count -gt $max_teardown_restarts ]]; then
                    log_warn "Teardown race repeated $restart_count times - giving up (max $max_teardown_restarts)."
                    exit_code=1
                    break
                fi

                log_info "Teardown race (${restart_count}/${max_teardown_restarts}) - restarting automatically (database preserved)."
                sleep 1
                continue
            fi

            break
        done
    fi

    local failure_count=0
    if [[ -f "$log_file" ]]; then
        failure_count=$(tail -c "+$((session_log_start + 1))" "$log_file" | grep -c "Falsifying example" 2>/dev/null) || failure_count=0
    fi

    if [[ $exit_code -eq 0 || $exit_code -eq 130 || $exit_code -eq 120 ]]; then
        log_pass "Fuzzing session ended."

        if [[ "$failure_count" -gt 0 ]]; then
            log_warn "$failure_count falsifying example(s) found in this session."
            echo "  View log: cat $log_file"
            echo "  List failures: ./scripts/fuzz_hypofuzz.sh --list"
        fi

        log_group_start "Event Infrastructure"
        python << EVENTEOF
import re
from pathlib import Path

tests_dir = Path("$PROJECT_ROOT/tests")

event_count = 0
for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        event_count += len(re.findall(r'(?<![a-zA-Z_])event\(', content))
    except Exception:
        pass

print("  HypoFuzz captures hypothesis.event() internally for coverage guidance.")
print("  Events are not echoed to stdout but guide path selection.")
print()
print(f"  Infrastructure: {event_count} event() calls in test suite")
print()
print("  For detailed infrastructure audit:")
print("    ./scripts/fuzz_hypofuzz.sh --preflight")
EVENTEOF
        log_group_end

        python << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$log_file")
exit_code = $exit_code
failure_count = $failure_count
teardown_race = "${teardown_race_detected}" == "true"
restart_count = $restart_count

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

failures = []
if failure_count > 0:
    example_pattern = r'Falsifying example:\s*(\w+)\(([^)]+)\)'
    for match in re.finditer(example_pattern, log_content):
        test_name = match.group(1)
        example_args = match.group(2).strip()[:500]
        failures.append({"test": test_name, "example": example_args})

if teardown_race and exit_code != 0:
    status = "teardown_race"
elif exit_code == 120:
    status = "interrupted"
else:
    status = "pass"

report = {
    "script": "$SCRIPT_NAME",
    "script_version": "$SCRIPT_VERSION",
    "mode": "deep",
    "status": status,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": failure_count,
    "failures": failures[:50],
    "exit_code": exit_code,
    "teardown_restarts": restart_count,
    "log_file": "$log_file"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
    else
        log_err "HypoFuzz exited with error code $exit_code."

        if grep -q "AF_UNIX path too long" "$log_file"; then
            log_warn "AF_UNIX path too long detected. TMPDIR is set to $TMPDIR."
        fi

        python << PYEOF
import json
from datetime import datetime, timezone

report = {
    "script": "$SCRIPT_NAME",
    "script_version": "$SCRIPT_VERSION",
    "mode": "deep",
    "status": "error",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": $failure_count,
    "exit_code": $exit_code,
    "log_file": "$log_file"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
        log_group_end
        return "$exit_code"
    fi

    log_group_end
    return "$exit_code"
}

run_list() {
    local examples_dir="$PROJECT_ROOT/.hypothesis/examples"
    local fuzz_log="$PROJECT_ROOT/.hypothesis/hypofuzz.log"

    log_group_start "Hypothesis Failure Reproduction Info"

    log_info "How Hypothesis failures work:"
    echo "  1. When a property test fails, Hypothesis shrinks to a minimal example"
    echo "  2. The shrunk example is stored in .hypothesis/examples/ (SHA-384 hashed)"
    echo "  3. On re-run, Hypothesis AUTOMATICALLY replays the stored failure"
    echo "  4. Simply running 'uv run pytest tests/' will reproduce all known failures"
    echo ""

    if [[ -d "$examples_dir" ]]; then
        local count
        count=$(find "$examples_dir" -type f 2>/dev/null | wc -l | tr -d ' ')
        log_pass ".hypothesis/examples/ exists with $count entries"
    else
        log_warn "No .hypothesis/examples/ directory found."
        echo "     Run some Hypothesis tests first to populate the database."
    fi
    echo ""

    if [[ -f "$fuzz_log" ]]; then
        log_info "Recent HypoFuzz session log: $fuzz_log"
        local failure_count=0
        failure_count=$(grep -c "Falsifying example" "$fuzz_log" 2>/dev/null) || failure_count=0
        if [[ "$failure_count" -gt 0 ]]; then
            log_warn "Found $failure_count falsifying example(s) in log."
            echo ""
            echo "Recent failures:"
            grep -B2 "Falsifying example" "$fuzz_log" | tail -20
        else
            echo "  No failures recorded in latest session."
        fi
    else
        log_info "HypoFuzz log: Not found (run --deep to create)"
    fi
    echo ""

    echo "To reproduce a specific failing test:"
    echo "  ./scripts/fuzz_hypofuzz.sh --repro test_module::test_function"
    echo ""
    echo "To reproduce all failures:"
    echo "  uv run pytest tests/ -x -v"
    echo ""
    echo "To extract @example decorator:"
    echo "  uv run python scripts/fuzz_hypofuzz_repro.py --example test_module::test_function"

    log_group_end
}

run_clean() {
    local hypothesis_dir="$PROJECT_ROOT/.hypothesis"
    local fuzz_log="$hypothesis_dir/hypofuzz.log"

    if [[ ! -d "$hypothesis_dir" ]]; then
        log_info "No .hypothesis/ directory found. Nothing to clean."
        return 0
    fi

    local example_count
    example_count=$(find "$hypothesis_dir/examples" -type f 2>/dev/null | wc -l | tr -d ' ')

    log_group_start "Hypothesis Database Cleanup"
    echo "Directory: $hypothesis_dir"
    echo "Examples:  $example_count cached entries"
    if [[ -f "$fuzz_log" ]]; then
        echo "Log:       $(wc -l < "$fuzz_log" | tr -d ' ') lines"
    fi
    echo ""
    if [[ "$FORCE" == "true" ]]; then
        rm -rf "$hypothesis_dir"
        log_pass "Removed .hypothesis/ directory (forced)."
    else
        if [[ ! -t 0 ]]; then
            log_err "Non-interactive environment detected. You must use --force to clean the database."
            exit 1
        fi

        log_warn "Removing .hypothesis/ will:"
        echo "  - Delete all cached examples (regression database)"
        echo "  - Delete any shrunk failure examples"
        echo "  - Require tests to rediscover edge cases"
        echo ""
        read -r -p "Remove .hypothesis/ directory? (y/N): " response
        case "$response" in
            [yY][eE][sS]|[yY])
                rm -rf "$hypothesis_dir"
                log_pass "Removed .hypothesis/ directory."
                ;;
            *)
                log_info "Cancelled."
                ;;
        esac
    fi
    log_group_end
}

run_repro() {
    if [[ -z "$REPRO_TEST" ]]; then
        log_err "Missing test argument for --repro"
        echo "Usage: ./scripts/fuzz_hypofuzz.sh --repro <test_module::test_function>"
        echo ""
        echo "Examples:"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py::test_roundtrip"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py"
        return 1
    fi

    log_group_start "Reproduce Hypothesis Failure"
    log_info "Test: $REPRO_TEST"

    local exit_code=0
    set +e
    uv run --python "$PY_VERSION" python scripts/fuzz_hypofuzz_repro.py --verbose --example "$REPRO_TEST"
    exit_code=$?
    set -e

    if [[ $exit_code -eq 0 ]]; then
        log_pass "Test passed - no failure to reproduce."
        echo "If you expected a failure, the bug may have been fixed or the"
        echo ".hypothesis/examples/ database may need to be cleared."
    fi

    log_group_end
    return "$exit_code"
}
