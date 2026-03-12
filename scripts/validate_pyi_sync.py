#!/usr/bin/env python3
# @lint-plugin: PISync
"""Validate that src/ftllexengine/__init__.pyi is in sync with __init__.py.

Enforces two invariants:
1. __all__ in __init__.pyi exactly matches __all__ in __init__.py (set equality).
2. Every name in __init__.pyi's __all__ is declared in the stub body
   (as a from-import, def, class, or type annotation).

Rationale:
    __init__.pyi is the type-authoritative interface for external callers when
    py.typed is present. Mypy uses the stub exclusively — any symbol in __init__.py
    that is absent from the stub is invisible to typed callers and causes mypy errors.
    More critically: CI lint plugins run `import ftllexengine` in a subprocess whose
    venv may diverge from the local pre-built venv; when stub/__all__ diverge the
    install metadata becomes inconsistent and the VersionSync plugin reports
    "Package not installed or import failed".

    This plugin is a dead-man's switch: any __all__ change that is not reflected in
    __init__.pyi breaks the build immediately at the lint stage.

Dead-man's switch property:
    Runs as a zero-cost AST-only check (no imports, no subprocess) in under 100ms.
    Adding a symbol to __init__.py without updating __init__.pyi → build fails.
    Adding a symbol to __init__.pyi without updating __init__.py → build fails.

Exit Codes:
    0: Stubs are in sync
    1: Divergence detected or file missing
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

# Plugin targets the package root regardless of where lint.sh runs from.
_SCRIPT_DIR = Path(__file__).parent
ROOT = _SCRIPT_DIR.parent


def _find_package_dir(root: Path) -> Path:
    """Dynamically discover the primary package directory under src/."""
    src_dir = root / "src"
    if not src_dir.exists():
        print("[ERROR] PISync: src/ directory not found.")
        sys.exit(3)

    # 1. Try to read from pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            with pyproject.open("rb") as f:
                data: dict[str, dict[str, str]] = tomllib.load(f)
            pkg_name = data.get("project", {}).get("name")
            if pkg_name and isinstance(pkg_name, str):
                # E.g., ftllexengine -> src/ftllexengine
                target = src_dir / pkg_name.replace("-", "_")
                if target.exists() and target.is_dir():
                    return target
        except tomllib.TOMLDecodeError:
            pass

    # 2. Fallback: just find the single directory under src/
    subdirs = [
        d for d in src_dir.iterdir()
        if d.is_dir() and d.name != "__pycache__" and not d.name.endswith(".egg-info")
    ]
    if len(subdirs) == 1:
        return subdirs[0]

    print("[ERROR] PISync: Could not unambiguously determine package directory in src/.")
    sys.exit(3)


PKG_DIR = _find_package_dir(ROOT)
PY_INIT = PKG_DIR / "__init__.py"
PYI_INIT = PKG_DIR / "__init__.pyi"


def extract_all_list(path: Path) -> list[str] | None:
    """Extract __all__ string-literal list from a .py or .pyi file via AST.

    Returns None if the file cannot be parsed or has no __all__ assignment.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        print(f"[ERROR] PISync: cannot parse {path.name}: {exc}")
        return None

    for node in ast.walk(tree):
        # Handle both plain assignment (in .py) and annotated assignment (in .pyi):
        #   __all__ = [...]               → ast.Assign
        #   __all__: list[str] = [...]    → ast.AnnAssign
        # Split into separate isinstance branches so mypy can narrow node.value correctly.
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
            and isinstance(node.value, ast.List)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and node.value is not None
            and isinstance(node.value, ast.List)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]

    return None


def extract_pyi_declared(path: Path) -> set[str]:
    """Extract all top-level declared names from a .pyi stub file.

    Collects names from:
    - from X import Y (as Y)  -- re-exports
    - def name(...)            -- stub function declarations
    - class Name:              -- stub class declarations
    - name: Type               -- annotated assignments (e.g. __version__: str)
    - name = ...               -- plain assignments
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        print(f"[ERROR] PISync: cannot parse {path.name}: {exc}")
        return set()

    declared: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        match node:
            case ast.ImportFrom(names=aliases):
                for alias in aliases:
                    # `from X import Y as Y` → the asname is the public name;
                    # `from X import Y` without as → name is the public name.
                    name = alias.asname or alias.name
                    declared.add(name)
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
                declared.add(name)
            case ast.ClassDef(name=name):
                declared.add(name)
            case ast.AnnAssign(target=tgt) if isinstance(tgt, ast.Name):
                declared.add(tgt.id)
            case ast.Assign(targets=targets):
                for assign_tgt in targets:
                    if isinstance(assign_tgt, ast.Name):
                        declared.add(assign_tgt.id)
    return declared


def main() -> int:
    """Run the PISync check. Returns 0 on pass, 1 on any failure."""
    failures: list[str] = []

    # Guard: both files must exist.
    for path in (PY_INIT, PYI_INIT):
        if not path.exists():
            print(f"[FAIL] PISync: file not found: {path}")
            return 1

    # Extract __all__ from both files.
    py_all = extract_all_list(PY_INIT)
    pyi_all = extract_all_list(PYI_INIT)

    if py_all is None:
        failures.append(f"No __all__ found in {PY_INIT.name}")
    if pyi_all is None:
        failures.append(f"No __all__ found in {PYI_INIT.name}")
    if failures:
        for f in failures:
            print(f"[FAIL] PISync: {f}")
        return 1

    assert py_all is not None  # narrowing for mypy
    assert pyi_all is not None

    py_set = set(py_all)
    pyi_set = set(pyi_all)

    # Check 1: __all__ set equality.
    missing_from_pyi = py_set - pyi_set
    extra_in_pyi = pyi_set - py_set

    if missing_from_pyi:
        # fmt: off
        hdr = "  Missing from __init__.pyi __all__ (add re-export + __all__ entry):\n"
        # fmt: on
        hdr += "".join(f"    {n!r}\n" for n in sorted(missing_from_pyi))
        failures.append(hdr.rstrip())

    if extra_in_pyi:
        hdr = "  Extra in __init__.pyi __all__ (not in __init__.py __all__):\n"
        hdr += "".join(f"    {n!r}\n" for n in sorted(extra_in_pyi))
        failures.append(hdr.rstrip())

    # Check 2: every name in pyi __all__ must be declared in the stub body.
    # __all__ itself is always a valid self-reference; skip it.
    declared = extract_pyi_declared(PYI_INIT)
    undeclared = pyi_set - declared - {"__all__"}
    if undeclared:
        lines = "  In __init__.pyi __all__ but not declared in stub body:\n"
        lines += "".join(f"    {n!r}\n" for n in sorted(undeclared))
        failures.append(lines.rstrip())

    if failures:
        print("[FAIL] PISync: __init__.pyi out of sync with __init__.py")
        for msg in failures:
            print(msg)
        print()
        print("  Resolution:")
        print("    1. Add `from .submodule import Name as Name` to __init__.pyi")
        print("    2. Add the name to __all__ in __init__.pyi")
        print("    3. Run lint.sh to verify")
        return 1

    count = len(py_set)
    print(f"[PASS] PISync: __init__.pyi in sync with __init__.py ({count} public symbols).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
