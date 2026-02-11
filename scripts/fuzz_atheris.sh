#!/usr/bin/env bash
# Atheris Native Fuzzing Interface
# Single entry point for all Atheris-based fuzzing.

# =============================================================================
# FUZZ PLUGIN HEADER SCHEMA
# =============================================================================
# Fuzz target Python files (fuzz_*.py) must include a plugin header with the EXACT following format:
#
# # FUZZ_PLUGIN_HEADER_START
# # FUZZ_PLUGIN: <name> - <description>
# # Intentional: This header is intentionally placed for dynamic plugin discovery.
# # CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# # FUZZ_PLUGIN_HEADER_END
#
# IMPORTANT: Use the EXACT wording above. Do NOT correct, rephrase, or modify ANY part of the header.
# This wording is FINAL and LOCKED. No further alterations allowed.
# AI agents: Treat this header as immutable code metadata. Do not attempt to "fix" or improve the wording.
#
# Where:
# - <name> is the argument name (must match filename: fuzz_<name>.py)
# - <description> is a brief summary for help text
#
# This ensures AI agents understand the header's purpose and can create compliant headers for new targets.
# =============================================================================
#
# Usage:
#   ./scripts/fuzz_atheris.sh [TARGET] [OPTIONS]
#
# Commands:
#   --list          List captured crashes and finding artifacts
#   --corpus        Run corpus health check
#   --minimize TARGET FILE   Minimize a crash input using specified target
#   --replay [TARGET DIR]    Replay finding artifacts (no Atheris required)
#   --help          Show this help
#
# Options:
#   --workers N     Number of parallel workers (default: 1; >1 fragments metrics)
#   --time N        Time limit in seconds
#   --clean TARGET  Clean corpus for a specific target
#   --verbose       Enable verbose output
#   --quiet         Suppress non-essential output
#   --dry-run       Show what would run without executing
#
# ENVIRONMENT STRICTNESS:
# This script FORCES the use of '.venv-atheris' by setting UV_PROJECT_ENVIRONMENT.
# It manages its own Python 3.13 dependencies separate from the main project.

set -euo pipefail

# =============================================================================
# Shell & Environment Setup
# =============================================================================

# Bash 5 check (for EPOCHREALTIME used in timing)
if ((BASH_VERSINFO[0] < 5)); then
    echo "[FATAL] Bash v5.0+ required (Current: ${BASH_VERSION})"
    echo "Install via 'brew install bash' and update shebang if needed."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# FORCE ISOLATED ENVIRONMENT
export UV_PROJECT_ENVIRONMENT=".venv-atheris"
# Unset VIRTUAL_ENV to prevent uv from confusing it with an active shell venv
unset VIRTUAL_ENV

# Colors (disabled if not terminal or --quiet)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

# Verbosity control
VERBOSE=0
QUIET=0
DRY_RUN=0

log_info() {
    if [[ $QUIET -eq 0 ]]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

log_verbose() {
    if [[ $VERBOSE -eq 1 ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# =============================================================================
# Plugin / Target Definitions
# =============================================================================

declare -A PARAM_TARGETS
declare -A PARAM_DESCRIPTIONS
declare -a PARAM_ORDER  # Preserve discovery order for deterministic help

# Dynamic Plugin Discovery
discover_plugins() {
    local fuzz_dir="$PROJECT_ROOT/fuzz_atheris"
    for file in "$fuzz_dir"/fuzz_*.py; do
        if [[ -f "$file" ]]; then
            # Find the FUZZ_PLUGIN line
            local header
            if header=$(grep -m1 '^# FUZZ_PLUGIN:' "$file" 2>/dev/null); then
                # Validate header structure with start and end tags
                local start_line plugin_line end_line
                start_line=$(grep -n '^# FUZZ_PLUGIN_HEADER_START' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                plugin_line=$(grep -n '^# FUZZ_PLUGIN:' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                end_line=$(grep -n '^# FUZZ_PLUGIN_HEADER_END' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                if [[ -n "$start_line" ]] && [[ -n "$plugin_line" ]] && [[ -n "$end_line" ]] && [[ "$start_line" -lt "$plugin_line" ]] && [[ "$plugin_line" -lt "$end_line" ]]; then
                    if [[ $header =~ ^#\ FUZZ_PLUGIN:\ (.+)\ -\ (.+)$ ]]; then
                        local name="${BASH_REMATCH[1]}"
                        local desc="${BASH_REMATCH[2]}"
                        local filename
                        filename=$(basename "$file" .py)
                        local expected_name="fuzz_${name}"
                        if [[ "$filename" = "$expected_name" ]]; then
                            PARAM_TARGETS["$name"]="$file"
                            PARAM_DESCRIPTIONS["$name"]="$desc"
                            PARAM_ORDER+=("$name")
                            log_verbose "Discovered plugin: $name -> $file"
                        else
                            log_warn "Plugin name '$name' does not match filename '$filename'"
                        fi
                    fi
                fi
            fi
        fi
    done
    log_verbose "Discovered ${#PARAM_TARGETS[@]} plugins"
}

# Discover plugins
discover_plugins

# =============================================================================
# Pre-Flight Diagnostics & "Binary Surgery" (macOS Fix)
# =============================================================================

# This function ensures Atheris is installed, linked correctly, and running
# on the correct Python version. It auto-heals macOS dynamic linking issues.
run_diagnostics() {
    if [[ $QUIET -eq 1 ]]; then
        # Minimal diagnostics in quiet mode
        local python_bin
        python_bin=$(uv run --group atheris python -c "import sys; print(sys.executable)" 2>/dev/null)
        if ! "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
            log_error "Atheris is not properly installed. Run without --quiet for diagnostics."
            exit 1
        fi
        return 0
    fi

    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${BOLD}Atheris Diagnostic Check${NC}"
    echo -e "Env: ${BLUE}.venv-atheris${NC}"
    echo -e "${BOLD}============================================================${NC}\n"

    # 1. Check Python Version (Must be < 3.14)
    local python_bin
    python_bin=$(uv run --group atheris python -c "import sys; print(sys.executable)" 2>/dev/null)
    local python_version
    python_version=$("$python_bin" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)

    echo -n "Python Version... "
    # Semantic version comparison using sort -V
    local min_supported="3.11"
    local max_supported="3.13"
    if ! printf '%s\n%s\n' "$min_supported" "$python_version" | sort -V -C 2>/dev/null; then
        echo -e "${RED}$python_version (Too old, requires >= $min_supported)${NC}"
        exit 3
    elif ! printf '%s\n%s\n' "$python_version" "$max_supported" | sort -V -C 2>/dev/null; then
        echo -e "${RED}$python_version (Unsupported, Atheris requires <= $max_supported)${NC}"
        echo -e "${RED}[FATAL] Python $python_version is not supported by Atheris.${NC}"
        exit 3
    else
        echo -e "${GREEN}$python_version${NC}"
    fi

    # 2. Check ABI / Importability
    echo -n "ABI Compatibility... "
    if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"

        echo -n "Fuzzing Capability... "
        if "$python_bin" -c "import atheris; f=lambda d:None; atheris.Setup(['test'],f); print('OK')" 2>/dev/null | grep -q "OK"; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${RED}FAILED${NC}"
            exit 1
        fi

        echo -e "\n${BOLD}============================================================${NC}"
        echo -e "${GREEN}[OK]${NC} Atheris is ready."
        echo -e "${BOLD}============================================================${NC}\n"
        return 0
    fi

    echo -e "${RED}FAILED${NC}"
    echo -e "${YELLOW}[WARN] Atheris ABI check failed. Attempting Auto-Heal...${NC}"

    # 3. macOS Auto-Heal (Binary Surgery)
    if [[ "$(uname)" == "Darwin" ]]; then
        heal_macos_atheris "$python_bin"

        # Verify after healing
        echo -n "ABI Compatibility (Post-Fix)... "
        if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
             echo -e "${GREEN}OK${NC}"
             echo -e "\n${BOLD}============================================================${NC}"
             echo -e "${GREEN}[OK]${NC} Atheris was repaired and is ready."
             echo -e "${BOLD}============================================================${NC}\n"
        else
             echo -e "${RED}STILL FAILING${NC}"
             exit 1
        fi
    else
        log_error "Atheris setup is broken and this is not macOS (cannot auto-heal)."
        echo "Try: uv cache clean atheris && uv sync --group atheris --reinstall"
        exit 1
    fi
}


heal_macos_atheris() {
    local python_bin="$1"

    # Locate LLVM (support both ARM and Intel Macs)
    local llvm_prefix
    if command -v brew &>/dev/null; then
        llvm_prefix=$(brew --prefix llvm 2>/dev/null || echo "")
    fi

    # Fallback paths for common installations
    if [[ -z "$llvm_prefix" ]] || [[ ! -d "$llvm_prefix" ]]; then
        for candidate in "/opt/homebrew/opt/llvm" "/usr/local/opt/llvm" "/opt/llvm"; do
            if [[ -d "$candidate" ]]; then
                llvm_prefix="$candidate"
                break
            fi
        done
    fi

    if [[ -z "$llvm_prefix" ]] || [[ ! -d "$llvm_prefix" ]]; then
        log_error "LLVM not found. Please run: brew install llvm"
        exit 2
    fi

    log_info "Re-installing Atheris with custom flags from $llvm_prefix..."

    # Reinstall with special flags
    (
        export CLANG_BIN="$llvm_prefix/bin/clang"
        export CC="$llvm_prefix/bin/clang"
        export CXX="$llvm_prefix/bin/clang++"
        export LDFLAGS="-L$llvm_prefix/lib/c++ -L$llvm_prefix/lib -Wl,-rpath,$llvm_prefix/lib/c++"
        export CPPFLAGS="-I$llvm_prefix/include"

        # Force reinstall in the specific environment
        uv pip install --python "$python_bin" --reinstall --no-cache-dir --no-binary :all: atheris
    )

    # Validate again
    if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
        echo -e "${GREEN}[SUCCESS] Atheris repaired successfully.${NC}"
    else
        log_error "Surgery failed. Could not fix Atheris ABI."
        exit 1
    fi
}

# =============================================================================
# Subroutines
# =============================================================================

show_help() {
    cat << EOF
Atheris Fuzzing Interface

USAGE:
    ./scripts/fuzz_atheris.sh [TARGET] [OPTIONS]

TARGETS:
EOF
    # Use PARAM_ORDER for deterministic output
    for key in "${PARAM_ORDER[@]}"; do
        printf "    %-15s %s\n" "$key" "${PARAM_DESCRIPTIONS[$key]}"
    done
    cat << EOF

COMMANDS:
    --list              List all crashes and finding artifacts
    --corpus            Run corpus health check (fuzz_atheris_corpus_health.py)
    --minimize TARGET FILE   Minimize a crash input using the specified target
    --replay TARGET [DIR]    Replay finding artifacts without Atheris
    --clean TARGET           Clean corpus for a specific target

OPTIONS:
    --workers N         Number of workers (default: 1; >1 fragments metrics)
    --time N            Max time in seconds
    --verbose           Enable verbose output
    --quiet             Suppress non-essential output
    --dry-run           Show what would run without executing
    --help              Show this help

EXAMPLES:
    ./scripts/fuzz_atheris.sh currency --time 60
    ./scripts/fuzz_atheris.sh stability --workers 8
    ./scripts/fuzz_atheris.sh --minimize currency .fuzz_atheris_corpus/crash_abc123
    ./scripts/fuzz_atheris.sh --replay structured
    ./scripts/fuzz_atheris.sh --replay structured .fuzz_atheris_corpus/structured/findings/
    ./scripts/fuzz_atheris.sh --clean roundtrip
EOF
}

run_list() {
    local corpus_dir="$PROJECT_ROOT/.fuzz_atheris_corpus"

    if [[ ! -d "$corpus_dir" ]]; then
        echo "No corpus directory found."
        return 0
    fi

    # Section 1: Raw libFuzzer crash files
    echo -e "${BOLD}Crashes (raw libFuzzer artifacts)${NC}"
    local crashes=()
    while IFS= read -r -d '' file; do
        crashes+=("$file")
    done < <(find "$corpus_dir" -name "crash_*" -type f -print0 2>/dev/null | head -z -n 50)

    local count="${#crashes[@]}"
    if [[ $count -gt 0 ]]; then
         echo "Found $count crash(es):"
         for crash in "${crashes[@]:0:10}"; do
             echo "  $crash"
         done
         if [[ $count -gt 10 ]]; then
             echo "  ... and $((count - 10)) more"
         fi
         echo ""
         echo "Inspect: xxd ${crashes[0]} | head -20"
    else
         echo "  No crashes found."
    fi
    echo ""

    # Section 2: Finding artifacts (human-readable, actionable)
    echo -e "${BOLD}Findings (actionable artifacts)${NC}"
    local finding_dirs=()
    while IFS= read -r -d '' dir; do
        finding_dirs+=("$dir")
    done < <(find "$corpus_dir" -type d -name "findings" -print0 2>/dev/null)

    local total_findings=0
    for fdir in "${finding_dirs[@]}"; do
        local meta_files=()
        while IFS= read -r -d '' mf; do
            meta_files+=("$mf")
        done < <(find "$fdir" -name "*_meta.json" -type f -print0 2>/dev/null | sort -z)

        if [[ ${#meta_files[@]} -gt 0 ]]; then
            echo "  ${fdir}:"
            for meta_file in "${meta_files[@]:0:10}"; do
                total_findings=$((total_findings + 1))
                local basename
                basename=$(basename "$meta_file")
                if command -v jq &>/dev/null; then
                    local pattern diff_offset source_len
                    pattern=$(jq -r '.pattern // "unknown"' "$meta_file" 2>/dev/null)
                    diff_offset=$(jq -r '.diff_offset // "?"' "$meta_file" 2>/dev/null)
                    source_len=$(jq -r '.source_len // "?"' "$meta_file" 2>/dev/null)
                    echo "    $basename  pattern=$pattern  source=${source_len}chars  diff@byte${diff_offset}"
                else
                    echo "    $basename"
                fi
            done
            if [[ ${#meta_files[@]} -gt 10 ]]; then
                echo "    ... and $((${#meta_files[@]} - 10)) more"
            fi
        fi
    done

    if [[ $total_findings -eq 0 ]]; then
        echo "  No finding artifacts found."
    else
        echo ""
        echo "Replay: ./scripts/fuzz_atheris.sh --replay <target> <findings_dir>"
    fi
}

run_corpus_health() {
    local health_script="$PROJECT_ROOT/scripts/fuzz_atheris_corpus_health.py"
    if [[ ! -f "$health_script" ]]; then
        log_error "Corpus health script not found: $health_script"
        exit 1
    fi
    echo -e "${BOLD}Checking Corpus Health...${NC}"
    uv run --group atheris python "$health_script"
}

parse_and_display_report() {
    local target_key="$1"
    local corpus_dir="$PROJECT_ROOT/.fuzz_atheris_corpus/$target_key"

    # Try to read JSON report from file (written during fuzzing)
    local report_file="$corpus_dir/fuzz_${target_key}_report.json"
    local json_report=""

    if [[ -f "$report_file" ]]; then
        json_report=$(cat "$report_file" 2>/dev/null)
    fi

    if [[ -z "$json_report" ]]; then
        log_warn "No JSON summary found (fuzzer may not have completed enough iterations)"
        return 0
    fi

    # Check for jq availability
    if ! command -v jq &> /dev/null; then
        log_warn "jq not found - install for detailed reporting (brew install jq)"
        # Fallback: extract key metrics with grep/sed
        echo "Raw findings count: $(echo "$json_report" | grep -o '"findings":[0-9]*' | cut -d: -f2)"
        return 0
    fi

    # Parse key metrics
    local status iterations findings
    status=$(echo "$json_report" | jq -r '.status // "unknown"')
    iterations=$(echo "$json_report" | jq -r '.iterations // 0')
    findings=$(echo "$json_report" | jq -r '.findings // 0')

    # Parse identification and timing (optional fields)
    local fuzzer_name fuzzer_target duration throughput
    fuzzer_name=$(echo "$json_report" | jq -r '.fuzzer_name // empty')
    fuzzer_target=$(echo "$json_report" | jq -r '.fuzzer_target // empty')
    duration=$(echo "$json_report" | jq -r '.campaign_duration_sec // empty')
    throughput=$(echo "$json_report" | jq -r '.iterations_per_sec // empty')

    # Display summary header
    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${BOLD}Fuzzing Campaign Summary${NC}"
    echo -e "${BOLD}============================================================${NC}"
    if [[ -n "$fuzzer_name" ]]; then
        echo "Fuzzer:     $fuzzer_name"
    fi
    if [[ -n "$fuzzer_target" ]]; then
        echo "Target:     $fuzzer_target"
    fi
    echo "Status:     $status"
    echo "Iterations: $(printf "%'d" "$iterations")"
    if [[ -n "$duration" ]]; then
        echo "Duration:   ${duration}s"
    fi
    if [[ -n "$throughput" ]]; then
        echo "Throughput: $(printf "%'.1f" "$throughput") iter/s"
    fi
    echo "Findings:   $(printf "%'d" "$findings")"

    # Performance metrics (if available)
    local perf_mean perf_p95 perf_p99
    perf_mean=$(echo "$json_report" | jq -r '.perf_mean_ms // empty')
    perf_p95=$(echo "$json_report" | jq -r '.perf_p95_ms // empty')
    perf_p99=$(echo "$json_report" | jq -r '.perf_p99_ms // empty')

    if [[ -n "$perf_mean" ]]; then
        echo ""
        echo "Performance:"
        echo "  Mean:     ${perf_mean}ms"
        if [[ -n "$perf_p95" ]]; then
            echo "  P95:      ${perf_p95}ms"
        fi
        if [[ -n "$perf_p99" ]]; then
            echo "  P99:      ${perf_p99}ms"
        fi
    fi

    # Memory metrics (if available)
    local mem_peak mem_delta
    mem_peak=$(echo "$json_report" | jq -r '.memory_peak_mb // empty')
    mem_delta=$(echo "$json_report" | jq -r '.memory_delta_mb // empty')

    if [[ -n "$mem_peak" ]]; then
        echo ""
        echo "Memory:"
        echo "  Peak:     ${mem_peak}MB"
        if [[ -n "$mem_delta" ]]; then
            echo "  Delta:    ${mem_delta}MB"
        fi
    fi

    # CRITICAL: Alert on findings
    if [[ "$findings" -gt 0 ]]; then
        echo -e "\n${RED}${BOLD}[WARNING] API Contract Violations Detected${NC}"
        echo -e "${RED}Found $findings violations during fuzzing campaign${NC}"
        echo ""

        # Extract and display top error patterns (handle both flat and nested)
        echo "Top Error Patterns:"
        echo "$json_report" | jq -r '
            to_entries
            | map(select(.key | test("^(error_|contract_)")))
            | sort_by(-.value)
            | limit(10; .[])
            | "  \(.key): \(.value)"
        ' 2>/dev/null || echo "  (Could not parse error patterns)"

        echo ""
        echo -e "${YELLOW}Action Required:${NC}"
        echo "  1. Review error patterns above"
        echo "  2. Inspect full JSON report: $report_file"
        echo "  3. Fix API contract violations in source code"
        echo "  4. Re-run fuzzer to verify fixes"

        echo -e "${BOLD}============================================================${NC}"
        return 1
    else
        echo -e "\n${GREEN}[OK] No API contract violations detected${NC}"
        echo -e "${BOLD}============================================================${NC}"
        return 0
    fi
}

run_fuzz_target() {
    local target_key="$1"
    local target_script="${PARAM_TARGETS[$target_key]:-}"

    if [[ -z "$target_script" ]]; then
        log_error "Unknown target: $target_key"
        show_help
        exit 1
    fi

    echo -e "${BOLD}Starting Fuzzing Campaign${NC}"
    echo "Target:  $target_key ($target_script)"
    echo "Workers: $WORKERS"
    if [[ "$WORKERS" -gt 1 ]]; then
        log_warn "Workers > 1: libFuzzer uses fork(). Each worker has independent state."
        log_warn "JSON report reflects the LAST-EXITING worker only, not aggregate stats."
        log_warn "For reliable metrics, use --workers 1 (the default)."
    fi
    if [[ -n "$TIME_LIMIT" ]]; then
        echo "Time:    ${TIME_LIMIT}s"
    else
        echo "Time:    Indefinite (Ctrl+C to stop)"
    fi
    echo ""

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] Would execute fuzzer with above parameters"
        return 0
    fi

    # Ensure Setup
    run_diagnostics

    # Per-target corpus directory prevents cross-contamination between fuzzers
    local corpus_dir="$PROJECT_ROOT/.fuzz_atheris_corpus/$target_key"
    mkdir -p "$corpus_dir"

    # Build args array (proper quoting)
    local -a fuzz_args=()
    fuzz_args+=("-workers=$WORKERS")
    fuzz_args+=("-jobs=0")
    fuzz_args+=("-artifact_prefix=$corpus_dir/crash_")

    if [[ -n "$TIME_LIMIT" ]]; then
        fuzz_args+=("-max_total_time=$TIME_LIMIT")
    fi

    # Add corpus directory as first positional (read/write)
    fuzz_args+=("$corpus_dir")

    # Add target-specific seed corpus (required; no fallback to generic seeds)
    local seed_dir="$PROJECT_ROOT/fuzz_atheris/seeds/$target_key"
    if [[ -d "$seed_dir" ]]; then
        fuzz_args+=("$seed_dir")
        log_verbose "Using target-specific seeds: $seed_dir"
    else
        log_warn "No seed directory found: $seed_dir (fuzzer will start from empty corpus)"
    fi

    # Run fuzzer (report will be written to .fuzz_atheris_corpus/fuzz_<target>_report.json)
    local exit_code=0
    uv run --group atheris python "$target_script" "${fuzz_args[@]}" || exit_code=$?

    # Parse and display report from file
    local report_exit=0
    if ! parse_and_display_report "$target_key"; then
        report_exit=1

        # Auto-replay finding artifacts to check if they reproduce without Atheris
        local findings_dir="$corpus_dir/findings"
        local replay_script="$PROJECT_ROOT/fuzz_atheris/fuzz_atheris_replay_finding.py"
        if [[ -d "$findings_dir" ]] && [[ -f "$replay_script" ]]; then
            echo ""
            echo -e "${BOLD}Auto-replaying findings without Atheris instrumentation...${NC}"
            uv run python "$replay_script" "$findings_dir" || true
        fi

        log_error "Fuzzer detected API contract violations"
        exit 1
    fi

    # Return fuzzer exit code if non-zero
    if [[ $exit_code -ne 0 ]]; then
        exit $exit_code
    fi
}

run_replay() {
    local target_key="$1"
    local findings_dir="${2:-}"

    # Default findings directory based on target
    if [[ -z "$findings_dir" ]]; then
        findings_dir="$PROJECT_ROOT/.fuzz_atheris_corpus/$target_key/findings"
    fi

    if [[ ! -d "$findings_dir" ]]; then
        log_error "Findings directory not found: $findings_dir"
        echo "Run the fuzzer first, or specify a findings directory."
        exit 1
    fi

    local replay_script="$PROJECT_ROOT/fuzz_atheris/fuzz_atheris_replay_finding.py"
    if [[ ! -f "$replay_script" ]]; then
        log_error "Replay script not found: $replay_script"
        exit 1
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] Would replay findings from $findings_dir"
        return 0
    fi

    echo -e "${BOLD}Replaying Finding Artifacts${NC}"
    echo "Target:     $target_key"
    echo "Directory:  $findings_dir"
    echo "Runner:     Main project venv (NOT .venv-atheris)"
    echo ""

    # Run replay in the main project venv (no Atheris instrumentation)
    uv run python "$replay_script" "$findings_dir"
}

run_minimize() {
    local target_key="$1"
    local crash_file="$2"

    # Validate target
    local target_script="${PARAM_TARGETS[$target_key]:-}"
    if [[ -z "$target_script" ]]; then
        log_error "Unknown target for minimization: $target_key"
        echo "Available targets:"
        for key in "${PARAM_ORDER[@]}"; do
            echo "  $key"
        done
        exit 1
    fi

    # Validate crash file
    if [[ ! -f "$crash_file" ]]; then
        log_error "Crash file not found: $crash_file"
        exit 1
    fi

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] Would minimize $crash_file using $target_key ($target_script)"
        return 0
    fi

    run_diagnostics
    echo -e "${BOLD}Minimizing Crash: $crash_file${NC}"
    echo "Using target: $target_key ($target_script)"

    local minimized="${crash_file}.minimized"

    # Run Atheris with -minimize_crash=1 using the CORRECT target
    uv run --group atheris python "$target_script" \
        -minimize_crash=1 \
        -exact_artifact_path="$minimized" \
        "$crash_file"

    if [[ -f "$minimized" ]]; then
        # Cross-platform file size (prefer wc -c for portability)
        local orig_size new_size
        orig_size=$(wc -c < "$crash_file" | tr -d ' ')
        new_size=$(wc -c < "$minimized" | tr -d ' ')

        echo -e "\n${BOLD}============================================================${NC}"
        echo -e "${GREEN}[SUCCESS] Crash minimized.${NC}"
        echo "Original size:  $orig_size bytes"
        echo "Minimized size: $new_size bytes"
        echo "Saved to:       $minimized"
        echo -e "${BOLD}============================================================${NC}"

        echo -e "\n${YELLOW}Next Steps:${NC}"
        echo "  1. Reproduce: uv run --group atheris python $target_script $minimized"
        echo "  2. Debug: xxd $minimized | head -20"
        echo "  3. Create regression test with minimized input"
    else
        log_error "Minimization failed (no output file generated)."
        exit 1
    fi
}


# =============================================================================
# Main Dispatch
# =============================================================================

# Defaults
WORKERS=1
TIME_LIMIT=""
TARGET=""
MODE="fuzz"
MINIMIZE_TARGET=""
MINIMIZE_FILE=""
REPLAY_TARGET=""
REPLAY_DIR=""

# Strict Argument Parser
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list|--corpus)
            if [[ "$MODE" != "fuzz" && "$MODE" != "${1#--}" ]]; then
                log_error "Conflicting modes selected: $MODE vs ${1#--}"
                exit 1
            fi
            MODE="${1#--}"
            shift
            ;;
        --clean)
            MODE="clean"
            # --clean requires a TARGET (either already parsed or as next arg)
            if [[ -z "$TARGET" ]]; then
                if [[ $# -lt 2 ]] || [[ "$2" == --* ]]; then
                    log_error "--clean requires a TARGET argument"
                    echo "Usage: ./scripts/fuzz_atheris.sh TARGET --clean"
                    echo "       ./scripts/fuzz_atheris.sh --clean TARGET"
                    exit 1
                fi
                TARGET="$2"
                shift
            fi
            shift
            ;;
        --minimize)
            MODE="minimize"
            # --minimize requires TARGET and FILE
            if [[ $# -lt 3 ]]; then
                log_error "--minimize requires TARGET and FILE arguments"
                echo "Usage: ./scripts/fuzz_atheris.sh --minimize TARGET FILE"
                echo "Example: ./scripts/fuzz_atheris.sh --minimize currency .fuzz_atheris_corpus/crash_abc123"
                exit 1
            fi
            MINIMIZE_TARGET="$2"
            MINIMIZE_FILE="$3"
            shift 3
            ;;
        --replay)
            MODE="replay"
            # --replay requires TARGET, optional DIR
            if [[ $# -lt 2 ]]; then
                log_error "--replay requires at least a TARGET argument"
                echo "Usage: ./scripts/fuzz_atheris.sh --replay TARGET [DIR]"
                echo "Example: ./scripts/fuzz_atheris.sh --replay structured"
                exit 1
            fi
            REPLAY_TARGET="$2"
            shift 2
            # Optional directory argument
            if [[ $# -gt 0 ]] && [[ ! "$1" == --* ]]; then
                REPLAY_DIR="$1"
                shift
            fi
            ;;
        --workers)
            if [[ $# -lt 2 ]] || [[ "$2" == --* ]]; then
                log_error "--workers requires a positive integer argument"
                exit 1
            fi
            if ! [[ "$2" =~ ^[1-9][0-9]*$ ]]; then
                log_error "--workers must be a positive integer, got: $2"
                exit 1
            fi
            WORKERS="$2"
            shift 2
            ;;
        --time)
            if [[ $# -lt 2 ]] || [[ "$2" == --* ]]; then
                log_error "--time requires a positive integer argument (seconds)"
                exit 1
            fi
            if ! [[ "$2" =~ ^[1-9][0-9]*$ ]]; then
                log_error "--time must be a positive integer (seconds), got: $2"
                exit 1
            fi
            TIME_LIMIT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=1
            shift
            ;;
        --quiet)
            QUIET=1
            RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            echo "Run './scripts/fuzz_atheris.sh --help' for usage."
            exit 1
            ;;
        *)
            if [[ -n "$TARGET" ]]; then
                log_error "Multiple targets specified: $TARGET and $1"
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

# [SECTION: SIGNAL_HANDLING]
cleanup() {
    # Cleanup on exit if needed (e.g., remove temp files)
    :
}
trap cleanup EXIT INT TERM

case "$MODE" in
    list)
        run_list
        ;;
    corpus)
        run_corpus_health
        ;;
    minimize)
        run_minimize "$MINIMIZE_TARGET" "$MINIMIZE_FILE"
        ;;
    replay)
        run_replay "$REPLAY_TARGET" "$REPLAY_DIR"
        ;;
    clean)
        CLEAN_DIR="$PROJECT_ROOT/.fuzz_atheris_corpus/$TARGET"
        if [[ ! -d "$CLEAN_DIR" ]]; then
            echo -e "${YELLOW}[WARN]${NC} No corpus directory found for target '$TARGET': $CLEAN_DIR"
            exit 0
        fi
        echo -e "${BOLD}Cleaning corpus for target '$TARGET'...${NC}"
        rm -rf "$CLEAN_DIR"
        echo "Done. Removed: $CLEAN_DIR"
        ;;
    fuzz)
        if [[ -z "$TARGET" ]]; then
            run_diagnostics
            show_help
            exit 0
        fi
        run_fuzz_target "$TARGET"
        ;;
esac
