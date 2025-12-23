<!--
RETRIEVAL_HINTS:
  keywords: [contributing, development, setup, pull request, code style, workflow]
  answers: [how to contribute, development setup, pr process, code standards]
-->
# Contributing

## Setup

```bash
git clone https://github.com/resoltico/FTLLexEngine.git
cd ftllexengine
uv sync --all-groups
```

## Scripts

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `uv run scripts/lint.sh` | Code quality checks (ruff, mypy, pylint) | During development |
| `uv run scripts/test.sh` | Run test suite with coverage | After code changes |
| `uv run scripts/benchmark.sh` | Performance benchmarks | Before/after optimization |
| `uv run scripts/bump-version.sh` | Update version in pyproject.toml | During release prep |
| `uv run scripts/release.sh` | Full release automation | When releasing a version |

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
- No mutable global state
- Pure functions

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
uv run scripts/test.sh           # Full suite with coverage
uv run scripts/test.sh --quick   # Quick mode (no coverage)

# Or directly with uv:
uv run pytest tests/
uv run pytest tests/ --cov=src/ftllexengine --cov-report=term-missing
uv run pytest tests/test_fluent_parser.py
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
uv run scripts/lint.sh           # Run all linters

# Or individually via uv run:
uv run mypy --strict src/ftllexengine
uv run ruff check src/ tests/
uv run pylint src/ftllexengine
```

## Property-Based Testing

FTLLexEngine uses Hypothesis for property-based testing. When Hypothesis discovers edge cases, they are automatically saved to `.hypothesis/examples/` and replayed on subsequent test runs.

If you see `HYPOTHESIS DETECTED A LOGIC FLAW`:
1. This should be a bug that needs fixing
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
uv run scripts/lint.sh
uv run scripts/test.sh
```

## Version Management

**CRITICAL: Single Source of Truth**

Version is managed in ONE location: `pyproject.toml`

The `__version__` attribute auto-populates from package metadata via `importlib.metadata`. This makes version drift structurally impossible.

### Developer Workflow for Version Changes

1. **Edit version in pyproject.toml only:**
   ```bash
   # Edit: version = "0.28.0" in pyproject.toml
   vim pyproject.toml
   ```

2. **Refresh environment:**
   ```bash
   uv sync
   ```

3. **Verify auto-sync worked:**
   ```bash
   python -c "import ftllexengine; print(ftllexengine.__version__)"
   # Output: 0.28.0
   ```

4. **Run tests to validate:**
   ```bash
   uv run scripts/lint.sh
   uv run scripts/test.sh
   ```

**NEVER** manually edit `__version__` in `src/ftllexengine/__init__.py` - it auto-updates from metadata.

## Releases

Versioning (Semantic Versioning):
- Patch (0.0.x): Bug fixes
- Minor (0.x.0): New features (backward compatible)
- Major (x.0.0): Breaking changes

### Manual Release Process

1. Run `uv run scripts/lint.sh` and `uv run scripts/test.sh` (complete validation)
2. Update version in `pyproject.toml` ONLY
3. Run `uv sync` to refresh metadata
4. Verify: `uv run python -c "import ftllexengine; print(ftllexengine.__version__)"`
5. Commit: `Bump version to X.Y.Z`
6. Tag: `git tag vX.Y.Z`
7. Push: `git push origin main && git push origin vX.Y.Z`

### Automated Release Process (Recommended)

Use the release automation script for safer releases:

```bash
# 1. Update version in pyproject.toml
vim pyproject.toml  # Change version to 0.28.0

# 2. Refresh metadata
uv sync

# 3. Commit version change
git add pyproject.toml
git commit -m "Bump version to 0.28.0"

# 4. Run release script (validates + creates tag)
uv run scripts/release.sh

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
- `uv run scripts/release.sh --dry-run` - Validate only, no git operations
- `uv run scripts/release.sh --help` - Show usage information
