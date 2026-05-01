#!/usr/bin/env bash

show_help() {
    cat <<EOF
Atheris Fuzzing Interface

USAGE:
    ./scripts/fuzz_atheris.sh <target> [OPTIONS]
    ./scripts/fuzz_atheris.sh --setup [TARGET]
    ./scripts/fuzz_atheris.sh --list
    ./scripts/fuzz_atheris.sh --corpus
    ./scripts/fuzz_atheris.sh --smoke-all [--time N]
    ./scripts/fuzz_atheris.sh --minimize TARGET FILE
    ./scripts/fuzz_atheris.sh --replay TARGET [DIR]
    ./scripts/fuzz_atheris.sh --report TARGET
    ./scripts/fuzz_atheris.sh --clean TARGET

TARGETS:
EOF
    for target in "${TARGET_ORDER[@]}"; do
        printf '    %-22s %s\n' "$target" "${TARGET_DESCRIPTIONS[$target]}"
    done
    cat <<EOF

OPTIONS:
    --workers N         Number of libFuzzer workers (default: 1)
    --time N            Maximum campaign time in seconds
    --verbose           Emit extra runner details
    --quiet             Suppress non-essential status output
    --dry-run           Print the resolved action without executing it
    --help              Show this help message

ENVIRONMENT:
    Native Atheris execution is container-owned. Run this script inside the
    committed contributor devcontainer or via:

      npx --yes @devcontainers/cli up --workspace-folder .
      npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh graph --time 60

INVENTORY:
    Target names, files, and descriptions are owned by:
      fuzz_atheris/targets.tsv
EOF
}

run_setup() {
    if [[ -n "$TARGET" ]]; then
        require_known_target "$TARGET"
        printf 'Target      : %s\n' "$TARGET"
        printf 'Script      : %s\n' "$(target_script_for "$TARGET")"
    fi
    check_atheris_environment
    log_pass "Atheris contributor environment is ready."
}

run_list() {
    if [[ ! -d "$ATHERIS_CORPUS_ROOT" ]]; then
        printf 'No Atheris corpus directory found at %s\n' "$ATHERIS_CORPUS_ROOT"
        return 0
    fi

    python3 - "$ATHERIS_CORPUS_ROOT" <<'PY'
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

corpus_root = Path(sys.argv[1])

print("Crashes")
crashes = sorted(glob.glob(str(corpus_root / "*/crash_*")))
if crashes:
    for crash in crashes[:20]:
        print(f"  {crash}")
    if len(crashes) > 20:
        print(f"  ... and {len(crashes) - 20} more")
else:
    print("  none")

print("\nFindings")
finding_dirs = sorted(corpus_root.glob("*/findings"))
found_any = False
for finding_dir in finding_dirs:
    meta_files = sorted(finding_dir.glob("*_meta.json"))
    if not meta_files:
        continue
    found_any = True
    print(f"  {finding_dir}:")
    for meta_file in meta_files[:10]:
        try:
            payload = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"    {meta_file.name}: unreadable metadata")
            continue
        pattern = payload.get("pattern", "unknown")
        source_len = payload.get("source_len", "?")
        diff_offset = payload.get("diff_offset", "?")
        print(
            f"    {meta_file.name}: pattern={pattern} source={source_len}chars diff@byte{diff_offset}"
        )

if not found_any:
    print("  none")
PY
}

run_corpus_health() {
    require_file "$ATHERIS_HEALTH_SCRIPT"
    check_atheris_environment
    python "$ATHERIS_HEALTH_SCRIPT"
}

run_smoke_all() {
    local per_target_time="${TIME_LIMIT:-3}"
    local target=""

    check_atheris_environment
    log_info "Running bounded Atheris smoke sweep across ${#TARGET_ORDER[@]} targets (${per_target_time}s each)"

    for target in "${TARGET_ORDER[@]}"; do
        TIME_LIMIT="$per_target_time" run_fuzz_target "$target"
    done
}

parse_and_display_report() {
    local target="$1"
    local report_file="$ATHERIS_CORPUS_ROOT/$target/fuzz_${target}_report.json"

    if [[ ! -f "$report_file" ]]; then
        log_warn "no campaign summary found for target '$target'"
        return 0
    fi

    python3 - "$report_file" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
payload = json.loads(report_path.read_text(encoding="utf-8"))

def fmt_int(value: object) -> str:
    return f"{int(value):,}"

print("\nFuzzing Campaign Summary")
print(f"Status      : {payload.get('status', 'unknown')}")
print(f"Iterations  : {fmt_int(payload.get('iterations', 0))}")
print(f"Findings    : {fmt_int(payload.get('findings', 0))}")
if payload.get("campaign_duration_sec") is not None:
    print(f"Duration    : {payload['campaign_duration_sec']}s")
if payload.get("iterations_per_sec") is not None:
    print(f"Throughput  : {payload['iterations_per_sec']:,.1f} iter/s")

if payload.get("perf_mean_ms") is not None:
    print(f"Mean latency: {payload['perf_mean_ms']}ms")
if payload.get("memory_peak_mb") is not None:
    print(f"Peak memory : {payload['memory_peak_mb']}MB")

if int(payload.get("findings", 0)) > 0:
    print(f"Report      : {report_path}")
    raise SystemExit(1)
PY
}

run_fuzz_target() {
    local target="$1"
    local target_script=""
    local corpus_dir=""
    local seed_dir=""
    local -a fuzz_args=()
    local exit_code=0

    target_script="$(target_script_for "$target")"
    corpus_dir="$ATHERIS_CORPUS_ROOT/$target"
    seed_dir="$PROJECT_ROOT/fuzz_atheris/seeds/$target"

    printf 'Target      : %s\n' "$target"
    printf 'Script      : %s\n' "$target_script"
    printf 'Workers     : %s\n' "$WORKERS"
    if [[ -n "$TIME_LIMIT" ]]; then
        printf 'Time        : %ss\n' "$TIME_LIMIT"
    else
        printf 'Time        : until interrupted\n'
    fi

    if [[ "$WORKERS" -gt 1 ]]; then
        log_warn "workers > 1 fragments libFuzzer metrics across processes"
    fi

    if [[ "$DRY_RUN" -eq 1 ]]; then
        return 0
    fi

    check_atheris_environment
    mkdir -p "$corpus_dir"

    fuzz_args+=("-workers=$WORKERS")
    fuzz_args+=("-jobs=0")
    fuzz_args+=("-artifact_prefix=$corpus_dir/crash_")
    if [[ -n "$TIME_LIMIT" ]]; then
        fuzz_args+=("-max_total_time=$TIME_LIMIT")
    fi
    fuzz_args+=("$corpus_dir")

    if [[ -d "$seed_dir" ]]; then
        fuzz_args+=("$seed_dir")
    else
        log_warn "no seed corpus directory found for target '$target'"
    fi

    python "$target_script" "${fuzz_args[@]}" || exit_code=$?

    if ! parse_and_display_report "$target"; then
        local findings_dir="$corpus_dir/findings"
        if [[ -d "$findings_dir" ]]; then
            python "$ATHERIS_REPLAY_SCRIPT" "$findings_dir" || true
        fi
        exit 1
    fi

    if [[ "$exit_code" -ne 0 ]]; then
        exit "$exit_code"
    fi
}

run_replay() {
    local target="$1"
    local findings_dir="${2:-$ATHERIS_CORPUS_ROOT/$target/findings}"

    require_known_target "$target"
    require_file "$ATHERIS_REPLAY_SCRIPT"
    [[ -d "$findings_dir" ]] || die "findings directory not found: $findings_dir"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf 'Replay      : %s\n' "$findings_dir"
        return 0
    fi

    python "$ATHERIS_REPLAY_SCRIPT" "$findings_dir"
}

run_minimize() {
    local target="$1"
    local crash_file="$2"
    local target_script=""
    local minimized=""
    local original_size=0
    local minimized_size=0

    require_known_target "$target"
    [[ -f "$crash_file" ]] || die "crash file not found: $crash_file"

    target_script="$(target_script_for "$target")"
    minimized="${crash_file}.minimized"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf 'Minimize    : %s via %s\n' "$crash_file" "$target"
        return 0
    fi

    check_atheris_environment
    python "$target_script" -minimize_crash=1 -exact_artifact_path="$minimized" "$crash_file"

    [[ -f "$minimized" ]] || die "minimization did not produce $minimized"

    original_size=$(wc -c < "$crash_file" | tr -d '[:space:]')
    minimized_size=$(wc -c < "$minimized" | tr -d '[:space:]')

    printf 'Original size: %s bytes\n' "$original_size"
    printf 'Minimized    : %s bytes\n' "$minimized_size"
    printf 'Output       : %s\n' "$minimized"
}

run_clean() {
    local target="$1"
    local clean_dir="$ATHERIS_CORPUS_ROOT/$target"

    require_known_target "$target"
    if [[ ! -d "$clean_dir" ]]; then
        log_warn "no corpus directory found for target '$target'"
        return 0
    fi

    rm -rf "$clean_dir"
    log_pass "Removed $clean_dir"
}
