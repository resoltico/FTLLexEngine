#!/usr/bin/env python3
"""CLI wrapper for the repository Python support contract tooling.

Premise:
    The executable entrypoint should stay small enough to make the command
    surface obvious and keep the implementation owner easy to audit.

Reason:
    The heavy validation logic lives in a library module so this file remains a
    thin command adapter rather than growing into another multi-purpose owner.
"""

from __future__ import annotations

import sys

from python_support_lib import emit_github_outputs, load_contract, validate_contract


def main() -> int:
    """Dispatch the requested contract command."""
    contract = load_contract()

    if len(sys.argv) != 2 or sys.argv[1] not in {"github-outputs", "validate"}:
        print("Usage: python_support.py {github-outputs|validate}", file=sys.stderr)
        return 2

    if sys.argv[1] == "github-outputs":
        emit_github_outputs(contract)
        return 0

    return validate_contract(contract)


if __name__ == "__main__":
    raise SystemExit(main())
