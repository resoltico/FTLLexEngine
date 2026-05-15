# Canonical Python support contract for repository tooling, CI, and release flows.
#
# Premise:
# A Python support claim is not one number. The repository simultaneously owns a
# minimum supported interpreter, a tested supported set, a latest supported
# release-verification interpreter, a free-threaded verification lane, and an
# intentionally unsupported floor used for negative packaging checks.
#
# Reason:
# Keeping those values in one shell-readable contract file gives every shell
# gate, workflow, validator, and document a single owner. Drift becomes a build
# failure instead of a silent metadata or CI mismatch.

FTLLEXENGINE_PYTHON_MIN="3.13"
FTLLEXENGINE_PYTHON_SUPPORTED="3.13 3.14"
FTLLEXENGINE_PYTHON_LATEST="3.14"
FTLLEXENGINE_PYTHON_FREETHREADED="3.13t"
FTLLEXENGINE_PYTHON_UNSUPPORTED_FLOOR="3.12"
