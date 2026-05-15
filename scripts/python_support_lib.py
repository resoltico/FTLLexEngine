"""Own and validate the repository's Python support contract.

Premise:
    Python compatibility truth spans metadata, workflows, shell gates, and
    public maintainer docs, so a one-file script quickly becomes a mixed owner.

Reason:
    This library keeps the structured contract logic in one importable module
    while the CLI entrypoint remains small and the validation rules stay easy
    to expand without violating the repository size budgets.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CONTRACT_PATH: Final = Path("scripts/lib/python_support_contract.sh")
SHELL_TARGETS: Final[tuple[Path, ...]] = (
    Path("check.sh"),
    Path("scripts/lint.sh"),
    Path("scripts/test.sh"),
    Path("scripts/fuzz_hypofuzz.sh"),
    Path("scripts/fuzz_atheris.sh"),
    Path("scripts/benchmark.sh"),
)


@dataclass(frozen=True, slots=True)
class PythonSupportContract:
    """Canonical repository Python support values."""

    minimum: str
    supported: tuple[str, ...]
    latest: str
    freethreaded: str
    unsupported_floor: str

    @property
    def ruff_target(self) -> str:
        """Return Ruff's target-version representation for the minimum version."""
        return f"py{self.minimum.replace('.', '')}"


def repo_root() -> Path:
    """Return the repository root from this helper module."""
    return Path(__file__).resolve().parent.parent


def load_contract(root: Path | None = None) -> PythonSupportContract:
    """Load and validate the canonical shell-readable support contract."""
    active_root = root or repo_root()
    contract_text = (active_root / CONTRACT_PATH).read_text(encoding="utf-8")
    values: dict[str, str] = {}

    for raw_line in contract_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r'([A-Z0-9_]+)="([^"]*)"', line)
        if match is None:
            msg = f"Unsupported contract line format: {raw_line!r}"
            raise SystemExit(msg)
        values[match.group(1)] = match.group(2)

    required = {
        "FTLLEXENGINE_PYTHON_MIN",
        "FTLLEXENGINE_PYTHON_SUPPORTED",
        "FTLLEXENGINE_PYTHON_LATEST",
        "FTLLEXENGINE_PYTHON_FREETHREADED",
        "FTLLEXENGINE_PYTHON_UNSUPPORTED_FLOOR",
    }
    missing = sorted(required - values.keys())
    if missing:
        msg = f"Missing contract keys: {missing}"
        raise SystemExit(msg)

    contract = PythonSupportContract(
        minimum=values["FTLLEXENGINE_PYTHON_MIN"],
        supported=tuple(values["FTLLEXENGINE_PYTHON_SUPPORTED"].split()),
        latest=values["FTLLEXENGINE_PYTHON_LATEST"],
        freethreaded=values["FTLLEXENGINE_PYTHON_FREETHREADED"],
        unsupported_floor=values["FTLLEXENGINE_PYTHON_UNSUPPORTED_FLOOR"],
    )
    validate_contract_shape(contract)
    return contract


def validate_contract_shape(contract: PythonSupportContract) -> None:
    """Reject internally inconsistent contract declarations."""
    if contract.minimum not in contract.supported:
        msg = "Minimum Python version must appear in supported set"
        raise SystemExit(msg)
    if contract.latest not in contract.supported:
        msg = "Latest supported Python version must appear in supported set"
        raise SystemExit(msg)
    if contract.supported[-1] != contract.latest:
        msg = "Latest supported Python version must be the final supported entry"
        raise SystemExit(msg)
    if not contract.freethreaded.startswith(contract.minimum):
        msg = "Free-threaded lane must be anchored to the minimum CPython release"
        raise SystemExit(msg)


def emit_github_outputs(contract: PythonSupportContract) -> None:
    """Emit GitHub Actions outputs derived from the canonical contract."""
    print(f"minimum-version={contract.minimum}")
    print(f"latest-version={contract.latest}")
    print(f"supported-json={json.dumps(list(contract.supported))}")
    print(f"freethreaded-version={contract.freethreaded}")
    print(f"unsupported-version={contract.unsupported_floor}")


def validate_contract(contract: PythonSupportContract) -> int:
    """Validate repository surfaces against the canonical Python contract."""
    root = repo_root()
    errors: list[str] = []
    _validate_pyproject(root, contract, errors)
    _validate_shell_scripts(root, errors)
    _validate_workflows(root, errors)
    _validate_docs(root, contract, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    print("[PASS] Python support contract is consistent.")
    return 0


def _expect(condition: bool, message: str, *, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _validate_pyproject(root: Path, contract: PythonSupportContract, errors: list[str]) -> None:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    mypy = data["tool"]["mypy"]
    ruff = data["tool"]["ruff"]

    _expect(
        project["requires-python"] == f">={contract.minimum}",
        "pyproject.toml [project].requires-python must match the contract minimum",
        errors=errors,
    )

    minor_classifier_re = re.compile(r"Programming Language :: Python :: (\d+\.\d+)$")
    actual_minors = {
        match.group(1)
        for classifier in project["classifiers"]
        if (match := minor_classifier_re.fullmatch(classifier))
    }
    _expect(
        actual_minors == set(contract.supported),
        (
            "pyproject.toml Python minor-version classifiers must equal the contract "
            f"supported set: expected {sorted(contract.supported)!r}, got {sorted(actual_minors)!r}"
        ),
        errors=errors,
    )

    _expect(
        str(mypy["python_version"]) == contract.minimum,
        "pyproject.toml [tool.mypy].python_version must match the contract minimum",
        errors=errors,
    )
    _expect(
        str(ruff["target-version"]) == contract.ruff_target,
        "pyproject.toml [tool.ruff].target-version must match the contract minimum",
        errors=errors,
    )

    tests_mypy = (root / "tests" / "mypy.ini").read_text(encoding="utf-8")
    _expect(
        f"python_version = {contract.minimum}" in tests_mypy,
        "tests/mypy.ini must match the contract minimum",
        errors=errors,
    )


def _validate_shell_scripts(root: Path, errors: list[str]) -> None:
    for relative_path in SHELL_TARGETS:
        text = (root / relative_path).read_text(encoding="utf-8")
        _expect(
            "python_support_contract.sh" in text,
            f"{relative_path} must source the canonical Python support contract",
            errors=errors,
        )
        _expect(
            'PY_VERSION="${PY_VERSION:-3.13}"' not in text,
            f"{relative_path} must not hard-code the default Python version",
            errors=errors,
        )


def _validate_workflows(root: Path, errors: list[str]) -> None:
    test_workflow = (root / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    publish_workflow = (root / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    for marker in (
        "python-support:",
        "fromJSON(needs.python-support.outputs.supported-json)",
        "needs.python-support.outputs.freethreaded-version",
        "permissions:\n      contents: read",
    ):
        _expect(
            marker in test_workflow,
            f"test workflow missing contract-driven marker: {marker}",
            errors=errors,
        )

    publish_markers = (
        "release-contract:",
        "fromJSON(needs.release-contract.outputs.supported-json)",
        "needs.release-contract.outputs.release-commit",
        "needs.release-contract.outputs.freethreaded-version",
        "Resolve immutable annotated release tag",
        "/git/ref/tags/",
        "/git/tags/",
        "Release tags must be annotated tag objects",
        "Release tag signature is not verified by GitHub",
    )
    for marker in publish_markers:
        _expect(
            marker in publish_workflow,
            f"publish workflow missing contract-driven marker: {marker}",
            errors=errors,
        )

    forbidden_workflow_snippets = (
        'python-version: ["3.13", "3.14"]',
        "When Python 3.15 releases",
        (
            "ref: ${{ github.event_name == 'workflow_dispatch' && "
            "inputs.release_tag || github.ref_name }}"
        ),
        "permissions:\n  contents: write\n  id-token: write",
    )
    for snippet in forbidden_workflow_snippets:
        _expect(
            snippet not in test_workflow and snippet not in publish_workflow,
            f"workflow drift marker must be absent: {snippet}",
            errors=errors,
        )


def _validate_docs(root: Path, contract: PythonSupportContract, errors: list[str]) -> None:
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    release_protocol = (root / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")
    developer_devcontainer = (root / "docs" / "DEVELOPER_DEVCONTAINER.md").read_text(
        encoding="utf-8"
    )
    testing_doc = (root / "docs" / "DOC_06_Testing.md").read_text(encoding="utf-8")

    expected_release_commands = (
        f"PY_VERSION={contract.latest} ./scripts/lint.sh",
        f"PY_VERSION={contract.latest} ./scripts/test.sh",
        f"uv run --group dev --python {contract.latest} python scripts/validate_docs.py",
        f"uv run --group dev --python {contract.latest} python scripts/validate_version.py",
    )
    for command in expected_release_commands:
        _expect(
            command in contributing,
            f"CONTRIBUTING.md missing command: {command}",
            errors=errors,
        )
        _expect(
            command in release_protocol,
            f"docs/RELEASE_PROTOCOL.md missing command: {command}",
            errors=errors,
        )

    _expect(
        f"Python {contract.minimum} as the canonical contributor interpreter"
        in developer_devcontainer,
        (
            "docs/DEVELOPER_DEVCONTAINER.md must name the contract minimum "
            "as the contributor interpreter"
        ),
        errors=errors,
    )
    _expect(
        f"PY_VERSION={contract.latest}" in developer_devcontainer,
        (
            "docs/DEVELOPER_DEVCONTAINER.md must use the contract latest "
            "version in forward-compat examples"
        ),
        errors=errors,
    )
    _expect(
        f".venv-{contract.minimum}" in testing_doc
        and f".venv-devcontainer-{contract.minimum}" in testing_doc,
        "docs/DOC_06_Testing.md must describe the contract minimum venv naming",
        errors=errors,
    )
    _expect(
        f"uv venv --python {contract.minimum} --seed" in release_protocol,
        (
            "docs/RELEASE_PROTOCOL.md must verify the minimum supported "
            "Python installer path"
        ),
        errors=errors,
    )
    _expect(
        f"Python {contract.unsupported_floor}" in release_protocol,
        (
            "docs/RELEASE_PROTOCOL.md must name the unsupported floor used "
            "for negative packaging verification"
        ),
        errors=errors,
    )
