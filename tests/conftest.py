"""Pytest configuration for FTLLexEngine test suite.

Single Source of Truth for Hypothesis max_examples:
- dev: Local development with 500 examples (thorough property testing)
- ci: GitHub Actions with 50 examples (fast CI feedback)

Profile auto-detection:
- CI=true environment variable -> "ci" profile (GitHub Actions sets this)
- HYPOTHESIS_PROFILE env var -> explicit override
- Otherwise -> "dev" profile (local development)

Override manually: HYPOTHESIS_PROFILE=ci pytest tests/
"""

from hypothesis import Phase, settings

# =============================================================================
# HYPOTHESIS PROFILES - SINGLE SOURCE OF TRUTH
# =============================================================================

# Development profile: thorough local testing (500 examples)
settings.register_profile(
    "dev",
    max_examples=500,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=False,
)

# CI profile: fast feedback for GitHub Actions (50 examples)
settings.register_profile(
    "ci",
    max_examples=50,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=True,
    print_blob=True,
)


# =============================================================================
# AUTO-DETECT EXECUTION CONTEXT
# =============================================================================


def _detect_profile() -> str:
    """Detect appropriate Hypothesis profile based on execution context.

    Priority:
    1. HYPOTHESIS_PROFILE env var (explicit override)
    2. CI=true env var (GitHub Actions auto-detection)
    3. Default to "dev" (local development)
    """
    import os

    # Explicit override via env var
    explicit = os.environ.get("HYPOTHESIS_PROFILE")
    if explicit in ("dev", "ci"):
        return explicit

    # GitHub Actions sets CI=true automatically
    if os.environ.get("CI") == "true":
        return "ci"

    # Local development
    return "dev"


# Load appropriate profile automatically
settings.load_profile(_detect_profile())
