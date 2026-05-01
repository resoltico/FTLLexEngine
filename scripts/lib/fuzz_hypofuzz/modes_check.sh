#!/usr/bin/env bash

run_preflight() {
    log_group_start "Preflight Infrastructure Audit"

    local audit_exit=0

    python << PREFLIGHT_EOF || audit_exit=$?
import ast
import re
import sys
from pathlib import Path
from collections import defaultdict

tests_dir = Path("$PROJECT_ROOT/tests")
strategies_dir = tests_dir / "strategies"

given_count = 0
given_by_file = defaultdict(int)
event_count = 0
event_by_file = defaultdict(int)

for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        g_matches = len(re.findall(r'@given\(', content))
        if g_matches > 0:
            given_count += g_matches
            given_by_file[py_file.relative_to(tests_dir)] = g_matches
        e_matches = len(re.findall(r'(?<![a-zA-Z_])event\(', content))
        if e_matches > 0:
            event_count += e_matches
            event_by_file[py_file.relative_to(tests_dir)] = e_matches
    except Exception:
        pass

fuzz_modules = []
fuzz_modules_without_events = []
for py_file in tests_dir.rglob("*.py"):
    try:
        if py_file.name == "conftest.py":
            continue
        content = py_file.read_text()
        if "pytest.mark.fuzz" in content or "pytestmark = pytest.mark.fuzz" in content:
            rel_path = py_file.relative_to(tests_dir)
            fuzz_modules.append(str(rel_path))
            has_given = given_by_file.get(rel_path, 0) > 0
            has_events = rel_path in event_by_file
            if has_given and not has_events:
                fuzz_modules_without_events.append(str(rel_path))
    except Exception:
        pass

tests_without_events = []
for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        if "@given" not in content:
            continue
        tree = ast.parse(content, filename=str(py_file))
        rel_path = str(py_file.relative_to(tests_dir))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_given = any(
                isinstance(dec, ast.Call)
                and (
                    (isinstance(dec.func, ast.Name) and dec.func.id == "given")
                    or (
                        isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "given"
                    )
                )
                for dec in node.decorator_list
            )
            if not has_given:
                continue
            has_event = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "event"
                for child in ast.walk(node)
            )
            if not has_event:
                tests_without_events.append(f"{rel_path}::{node.name}")
    except Exception:
        pass

_STRATEGY_SUPPORT_FILES = {"__init__.py", "ftl.py", "ftl_shared.py"}
strategy_coverage = {}
strategy_gaps = []
has_strategies_dir = strategies_dir.exists()

if has_strategies_dir:
    for strat_file in strategies_dir.glob("*.py"):
        try:
            if strat_file.name in _STRATEGY_SUPPORT_FILES:
                continue
            content = strat_file.read_text()
            events = len(re.findall(r'(?<![a-zA-Z_])event\(', content))
            strategy_coverage[strat_file.name] = events
            if events == 0:
                strategy_gaps.append(strat_file.name)
        except Exception:
            pass

print(f"Test Files:          {len(list(tests_dir.rglob('*.py')))}")
print(f"@given Tests:        {given_count}")
print(f"event() Calls:       {event_count}")
print(f"Fuzz Modules:        {len(fuzz_modules)}")
print()

if has_strategies_dir:
    if strategy_coverage:
        print("Strategy Coverage:")
        for name, count in sorted(strategy_coverage.items()):
            status = "[  OK  ]" if count > 0 else "[ FAIL ]"
            print(f"  {status} {name:<20} {count} events")
        print()

    if strategy_gaps:
        print("[FAIL] Strategy files without event() calls (HypoFuzz guidance gap):")
        for name in sorted(strategy_gaps):
            print(f"  [ FAIL ] {name}")
        print()
else:
    print("[ INFO ] No tests/strategies directory found (skipped strategy audit)")
    print()

if fuzz_modules_without_events:
    print("[WARN] Fuzz Modules WITHOUT Events (File-Level Gap):")
    for mod in sorted(fuzz_modules_without_events):
        given = given_by_file.get(Path(mod), 0)
        print(f"  [ WARN ] {mod} ({given} @given tests, 0 events)")
    print()
else:
    print("[  OK  ] All fuzz modules have events (file-level)")
    print()

if tests_without_events:
    print("[FAIL] @given Tests WITHOUT event() Calls (ALL test files):")
    for test_id in sorted(tests_without_events):
        print(f"  [ FAIL ] {test_id}")
    print()
else:
    print("[  OK  ] All @given tests emit events (per-test, all files)")
    print()

gaps = len(fuzz_modules_without_events) + len(tests_without_events) + len(strategy_gaps)
if gaps > 0:
    print(f"[FAIL] {gaps} gap(s) detected. Add hypothesis.event() calls for semantic guidance.")
    sys.exit(1)
else:
    print("[  OK  ] Infrastructure audit passed. Run --deep for coverage-guided fuzzing.")
PREFLIGHT_EOF

    log_group_end
    return "$audit_exit"
}

run_check() {
    run_diagnostics
    log_group_start "Property Tests"

    if [[ "$VERBOSE" == "true" ]]; then
        export HYPOTHESIS_PROFILE="verbose"
    fi

    local test_target="${TARGET:-tests/}"

    if [[ ! -e "$test_target" ]]; then
        log_err "Target not found: $test_target"
        log_group_end
        return 1
    fi

    log_info "Target: $test_target"
    if [[ "$VERBOSE" == "true" ]]; then
        log_info "Profile: verbose"
    else
        log_info "Profile: default (dev)"
    fi

    local temp_log
    temp_log=$(mktemp)

    local cmd=(uv run --python "$PY_VERSION" pytest "$test_target" -v --tb=short)

    local exit_code=0
    set +e
    _run_with_heartbeat "$temp_log" false -- "${cmd[@]}"
    exit_code=$?
    set -e

    python << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$temp_log")
exit_code = $exit_code

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

summary_match = re.search(r'=+ (.*?) =+', log_content)
summary_text = summary_match.group(1) if summary_match else ""

passed_match = re.search(r'(\d+) passed', summary_text)
failed_match = re.search(r'(\d+) failed', summary_text)
skipped_match = re.search(r'(\d+) skipped', summary_text)

tests_passed = int(passed_match.group(1)) if passed_match else 0
tests_failed = int(failed_match.group(1)) if failed_match else 0
tests_skipped = int(skipped_match.group(1)) if skipped_match else 0

hypo_count = log_content.count('Falsifying example')

failures = []
failed_test_pattern = r'FAILED (tests/.+?)(?: - |$)'
failed_tests = sorted(list(set(re.findall(failed_test_pattern, log_content))))

for test_path in failed_tests:
    failure_entry = {"test": test_path}
    test_section_start = log_content.find(test_path)
    if test_section_start != -1:
        test_section = log_content[test_section_start:test_section_start + 2000]
        error_match = re.search(r'E\s+(\w+Error|\w+Exception):', test_section)
        if error_match:
            failure_entry["error_type"] = error_match.group(1)
    if 'Falsifying example' in log_content:
        test_func = test_path.split("::")[-1] if "::" in test_path else ""
        example_pattern = rf'Falsifying example:\s*{re.escape(test_func)}\(([^\)]+)\)'
        example_match = re.search(example_pattern, log_content, re.DOTALL)
        if example_match:
            failure_entry["example"] = example_match.group(1).strip()[:500]
    failures.append(failure_entry)

fail_ex = ""
if 'Falsifying example' in log_content:
    try:
        fail_ex = log_content.split('Falsifying example')[1].split('\n')[0][:200].strip()
    except IndexError:
        pass

if exit_code == 0:
    status = 'pass'
elif exit_code in (130, 2):
    status = 'stopped'
elif tests_failed > 0 or hypo_count > 0:
    status = 'finding'
else:
    status = 'error'

report = {
    'script': '$SCRIPT_NAME',
    'script_version': '$SCRIPT_VERSION',
    'mode': 'check',
    'status': status,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'tests_passed': tests_passed,
    'tests_failed': tests_failed,
    'tests_skipped': tests_skipped,
    'hypothesis_failures': hypo_count,
    'falsifying_example': fail_ex,
    'failures': failures,
    'exit_code': exit_code
}
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps(report, indent=2))
print('[SUMMARY-JSON-END]')
PYEOF

    if [[ $exit_code -eq 0 ]]; then
        log_pass "All property tests passed."
    elif [[ $exit_code -eq 130 || $exit_code -eq 2 ]]; then
        log_info "Run interrupted by user."
    elif [[ $exit_code -eq 1 ]]; then
        log_fail "Failures detected. See JSON summary above."
        if [[ "$VERBOSE" == "false" ]]; then
            log_warn "Failure output:"
            if [[ -s "$temp_log" ]]; then
                grep -A 20 "Falsifying example" "$temp_log" || head -n 20 "$temp_log"
            fi
        fi
    else
        log_err "Test execution failed (code $exit_code)."
    fi

    rm -f "$temp_log"
    log_group_end
    return "$exit_code"
}
