<!--
RETRIEVAL_HINTS:
  keywords: [contributing, development, setup, pull request, code style, workflow]
  answers: [how to contribute, development setup, pr process, code standards]
-->
# Contributing

## Setup

```bash
git clone https://github.com/resoltico/ftllexengine.git
cd ftllexengine
pip install -e ".[dev]"
```

Dependencies: pytest, pytest-cov, hypothesis, mypy, ruff, pylint

## Scripts

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `./scripts/lint.sh` | Code quality checks (ruff, mypy, pylint) | During development |
| `./scripts/test.sh` | Run test suite with coverage | After code changes |
| `./scripts/benchmark.sh` | Performance benchmarks | Before/after optimization |
| `./scripts/bump-version.sh` | Update version in pyproject.toml | During release prep |
| `./scripts/extract-changelog.sh` | Extract release notes from CHANGELOG | During release |
| `./scripts/release.sh` | Full release automation | When releasing a version |
| `./scripts/validate_docs.py` | Validate documentation structure | Before documentation PRs |
| `./scripts/validate_version.py` | Check version consistency | During CI/release |

All scripts support:
- `--help` - Show usage documentation
- `--ci` - Non-interactive mode (for CI/CD pipelines)

**Execution order:** lint → test

## Code Standards

Branch naming: `feature/description`, `fix/description`, `docs/description`

Style:
- PEP 8
- 100 char line limit
- Type hints required
- Docstrings for public APIs

Architecture:
- Immutable data structures (frozen dataclasses)
- Pure functions
- No mutable global state

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Message:
    """FTL message node."""
    id: Identifier
    value: Pattern | None
    attributes: tuple[Attribute, ...]
```

## Testing

```bash
./scripts/test.sh           # Full suite with coverage
./scripts/test.sh --quick   # Quick mode (no coverage)

# Or directly with pytest:
pytest tests/
pytest tests/ --cov=ftllexengine --cov-report=term-missing
pytest tests/test_fluent_parser.py
pytest tests/ -x
```

Example tests:
```python
def test_parse_simple_message():
    parser = FluentParserV1()
    resource = parser.parse("hello = World")
    assert len(resource.entries) == 1

from hypothesis import given, strategies as st

@given(st.text())
def test_parser_never_crashes(source):
    resource = FluentParserV1().parse(source)
    assert resource is not None
```

Coverage requirement: 95%+

## Quality Checks

```bash
./scripts/lint.sh           # Run all linters
./scripts/lint.sh --fix     # Auto-fix where possible

# Or individually:
mypy --strict src/ftllexengine
ruff check src/ tests/
pylint src/ftllexengine
```

## Property-Based Testing

FTLLexEngine uses Hypothesis for property-based testing. When Hypothesis discovers edge cases, they are automatically saved to `.hypothesis/examples/` and replayed on subsequent test runs.

If you see `[ALERT] HYPOTHESIS DISCOVERED A BUG`:
1. This is a REAL bug that needs fixing
2. The failing example is automatically saved
3. Fix the bug and re-run tests to verify

## Pull Requests

Commit message format:
```
Short summary (<72 chars)

Detailed description.

Fixes #123
```

Use imperative mood.

CI requirements:
- All tests pass (3,581+ tests)
- Type checking passes (mypy --strict)
- Linting passes (ruff, pylint)
- Coverage 95%+

Before submitting:
```bash
./scripts/lint.sh
./scripts/test.sh
```

## Version Management

**CRITICAL: Single Source of Truth**

Version is managed in ONE location: `pyproject.toml`

The `__version__` attribute auto-populates from package metadata via `importlib.metadata`. This makes version drift structurally impossible.

### Developer Workflow for Version Changes

1. **Edit version in pyproject.toml only:**
   ```bash
   # Edit: version = "0.8.0" in pyproject.toml
   vim pyproject.toml
   ```

2. **Refresh package metadata:**
   ```bash
   pip install -e .
   ```

3. **Verify auto-sync worked:**
   ```bash
   python -c "import ftllexengine; print(ftllexengine.__version__)"
   # Output: 0.8.0
   ```

4. **Run tests to validate:**
   ```bash
   ./scripts/lint.sh
   ./scripts/test.sh
   ```

**NEVER** manually edit `__version__` in `src/ftllexengine/__init__.py` - it auto-updates from metadata.

## Releases

Versioning (Semantic Versioning):
- Patch (0.0.x): Bug fixes
- Minor (0.x.0): New features (backward compatible)
- Major (x.0.0): Breaking changes

### Manual Release Process

1. Run `./scripts/lint.sh` and ./scripts/test.sh` (complete validation)
2. Update version in `pyproject.toml` ONLY
3. Run `pip install -e .` to refresh metadata
4. Verify: `python -c "import ftllexengine; print(ftllexengine.__version__)"`
5. Commit: `Bump version to X.Y.Z`
6. Tag: `git tag vX.Y.Z`
7. Push: `git push origin main && git push origin vX.Y.Z`

### Automated Release Process (Recommended)

Use the release automation script for safer releases:

```bash
# 1. Update version in pyproject.toml
vim pyproject.toml  # Change version to 0.8.0

# 2. Refresh metadata
pip install -e .

# 3. Commit version change
git add pyproject.toml
git commit -m "Bump version to 0.8.0"

# 4. Run release script (validates + creates tag)
./scripts/release.sh

# 5. Push (as displayed by script)
git push origin main --tags
```

The release script will:
- Validate version consistency between pyproject.toml and __version__
- Check git working directory is clean
- Run full test suite
- Create properly formatted git tag
- Display push commands

**Options:**
- `./scripts/release.sh --dry-run` - Validate only, no git operations
- `./scripts/release.sh --help` - Show usage information
