"""Resource loading infrastructure for FluentLocalization.

Provides the protocol for FTL resource loaders, a filesystem implementation
with path-traversal security, and result/summary data structures for
tracking load attempts.

Components:
    ResourceLoader - Protocol for loading FTL resources (structural typing)
    PathResourceLoader - Disk-based loader with path-traversal prevention
    FallbackInfo - Immutable record of a locale fallback event
    ResourceLoadResult - Immutable result of a single resource load attempt
    LoadSummary - Immutable aggregate of all load results from initialization

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ftllexengine.enums import LoadStatus
from ftllexengine.localization.types import FTLSource, LocaleCode, ResourceId

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import Junk

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Protocol
    "ResourceLoader",
    # Concrete loader
    "PathResourceLoader",
    # Fallback observability
    "FallbackInfo",
    # Load result types
    "ResourceLoadResult",
    "LoadSummary",
]


class ResourceLoader(Protocol):
    """Protocol for loading FTL resources for specific locales.

    Implementations must provide a load() method that retrieves FTL source
    for a given locale and resource identifier.

    This is a Protocol (structural typing) rather than ABC to allow
    maximum flexibility for users implementing custom loaders.

    The optional describe_path() method provides a human-readable path
    string for diagnostics. Implementations that know the physical path
    should override it; the default returns a generic "{locale}/{resource_id}"
    description.

    Example:
        >>> class DiskLoader:
        ...     def load(self, locale: str, resource_id: str) -> str:
        ...         path = Path(f"locales/{locale}/{resource_id}")
        ...         return path.read_text(encoding="utf-8")
        ...     def describe_path(self, locale: str, resource_id: str) -> str:
        ...         return f"locales/{locale}/{resource_id}"
        ...
        >>> loader = DiskLoader()
        >>> l10n = FluentLocalization(['en', 'fr'], ['main.ftl'], loader)
    """

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource:
        """Load FTL resource for given locale.

        Args:
            locale: Locale code (e.g., 'en', 'fr', 'lv')
            resource_id: Resource identifier (e.g., 'main.ftl', 'errors.ftl')

        Returns:
            FTL source code as string

        Raises:
            FileNotFoundError: If resource doesn't exist for this locale
            OSError: If file cannot be read
        """

    def describe_path(self, locale: LocaleCode, resource_id: ResourceId) -> str:
        """Return human-readable path for diagnostics.

        Default implementation returns a generic "{locale}/{resource_id}" string.
        Override in concrete loaders that know the physical path.

        Args:
            locale: Locale code
            resource_id: Resource identifier

        Returns:
            Human-readable path string for error messages and load results
        """
        return f"{locale}/{resource_id}"


@dataclass(frozen=True, slots=True)
class PathResourceLoader:
    """File system resource loader using path templates.

    Implements ResourceLoader protocol for loading FTL files from disk.
    Uses {locale} placeholder in path template for locale substitution.

    Uses Python 3.13 frozen dataclass with slots for low memory overhead.

    Security:
        Validates both locale and resource_id to prevent directory traversal attacks.
        Locale codes containing path separators or ".." are rejected.
        Resource IDs containing ".." or absolute paths are rejected.
        All resolved paths are validated against a fixed root directory.

    Example:
        >>> loader = PathResourceLoader("locales/{locale}")
        >>> ftl = loader.load("en", "main.ftl")
        # Loads from: locales/en/main.ftl

    Attributes:
        base_path: Path template with {locale} placeholder
        root_dir: Fixed root directory for path traversal validation.
                  Defaults to parent of base_path if not specified.
    """

    base_path: str
    root_dir: str | None = None
    _resolved_root: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Cache resolved root directory and validate template at initialization.

        Raises:
            ValueError: If base_path does not contain {locale} placeholder
        """
        # Fail-fast validation: Require {locale} placeholder in path template.
        # Without this placeholder, all locales would load from the same path,
        # causing silent data corruption where wrong locale files are loaded.
        if "{locale}" not in self.base_path:
            msg = (
                f"base_path must contain '{{locale}}' placeholder for locale substitution, "
                f"got: '{self.base_path}'"
            )
            raise ValueError(msg)

        if self.root_dir is not None:
            resolved = Path(self.root_dir).resolve()
        else:
            # Extract static prefix from base_path template.
            # e.g., "locales/{locale}" -> "locales"
            # Note: split() always returns non-empty list, so template_parts[0] always exists
            template_parts = self.base_path.split("{locale}")
            static_prefix = template_parts[0].rstrip("/\\")
            resolved = Path(static_prefix).resolve() if static_prefix else Path.cwd().resolve()
        object.__setattr__(self, "_resolved_root", resolved)

    @staticmethod
    def _validate_locale(locale: LocaleCode) -> None:
        """Validate locale code for path traversal attacks.

        Args:
            locale: Locale code to validate

        Raises:
            ValueError: If locale contains unsafe path components
        """
        if ".." in locale:
            msg = f"Path traversal sequences not allowed in locale: '{locale}'"
            raise ValueError(msg)
        if "/" in locale or "\\" in locale:
            msg = f"Path separators not allowed in locale: '{locale}'"
            raise ValueError(msg)
        if not locale:
            msg = "Locale code cannot be empty"
            raise ValueError(msg)

    @staticmethod
    def _validate_resource_id(resource_id: ResourceId) -> None:
        """Validate resource_id for path traversal attacks and whitespace.

        Args:
            resource_id: Resource identifier to validate

        Raises:
            ValueError: If resource_id contains unsafe path components or
                       leading/trailing whitespace
        """
        stripped = resource_id.strip()
        if stripped != resource_id:
            msg = (
                f"Resource ID contains leading/trailing whitespace: {resource_id!r}. "
                f"Stripped would be: {stripped!r}"
            )
            raise ValueError(msg)
        if Path(resource_id).is_absolute():
            msg = f"Absolute paths not allowed in resource_id: '{resource_id}'"
            raise ValueError(msg)
        if ".." in resource_id:
            msg = f"Path traversal sequences not allowed in resource_id: '{resource_id}'"
            raise ValueError(msg)
        if resource_id.startswith(("/", "\\")):
            msg = f"Leading path separator not allowed in resource_id: '{resource_id}'"
            raise ValueError(msg)

    @staticmethod
    def _is_safe_path(base_dir: Path, full_path: Path) -> bool:
        """Check if full_path is safely within base_dir.

        Security Note:
            Explicitly resolves both paths before comparison to prevent
            path manipulation attacks. This follows defense-in-depth:
            even if caller provides un-resolved paths, this method
            canonicalizes them before the security check.

        Args:
            base_dir: Base directory (will be resolved)
            full_path: Full path to check (will be resolved)

        Returns:
            True if resolved full_path is within resolved base_dir
        """
        try:
            resolved_base = base_dir.resolve()
            resolved_path = full_path.resolve()
            resolved_path.relative_to(resolved_base)
            return True
        except ValueError:
            return False

    def describe_path(self, locale: LocaleCode, resource_id: ResourceId) -> str:
        """Return human-readable path for diagnostics.

        Args:
            locale: Locale code
            resource_id: Resource identifier

        Returns:
            Constructed path string showing the locale-substituted directory
        """
        locale_path = self.base_path.replace("{locale}", locale)
        return f"{locale_path}/{resource_id}"

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource:
        """Load FTL file from disk.

        Args:
            locale: Locale code to substitute in path template
            resource_id: FTL filename (e.g., 'main.ftl')

        Returns:
            FTL source code

        Raises:
            ValueError: If locale or resource_id contains path traversal sequences
            FileNotFoundError: If file doesn't exist
            OSError: If file cannot be read

        Security:
            Validates both locale and resource_id to prevent directory traversal.
            All resolved paths are verified against a fixed root directory.
        """
        self._validate_locale(locale)
        self._validate_resource_id(resource_id)

        # Use replace() instead of format() to avoid KeyError if template
        # contains other braces like "{version}" for future extensibility
        locale_path = self.base_path.replace("{locale}", locale)
        base_dir = Path(locale_path).resolve()
        full_path = (base_dir / resource_id).resolve()

        if not self._is_safe_path(self._resolved_root, full_path):
            msg = (
                f"Path traversal detected: resolved path escapes root directory. "
                f"locale='{locale}', resource_id='{resource_id}'"
            )
            raise ValueError(msg)

        return full_path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class FallbackInfo:
    """Information about a locale fallback event.

    Provided to the on_fallback callback when FluentLocalization resolves
    a message using a fallback locale instead of the primary locale.

    Attributes:
        requested_locale: The primary (first) locale in the chain
        resolved_locale: The locale that actually contained the message
        message_id: The message identifier that was resolved

    Example:
        >>> def log_fallback(info: FallbackInfo) -> None:
        ...     print(f"Fallback: {info.message_id} resolved from "
        ...           f"{info.resolved_locale} (requested {info.requested_locale})")
        >>> l10n = FluentLocalization(['lv', 'en'], on_fallback=log_fallback)
    """

    requested_locale: LocaleCode
    resolved_locale: LocaleCode
    message_id: str


@dataclass(frozen=True, slots=True)
class ResourceLoadResult:
    """Result of loading a single FTL resource.

    Tracks the outcome of loading a resource for a specific locale,
    including any errors encountered and any Junk entries from parsing.

    Attributes:
        locale: Locale code for this resource
        resource_id: Resource identifier (e.g., 'main.ftl')
        status: Load status (success, not_found, error)
        error: Exception if status is ERROR, None otherwise
        source_path: Human-readable path to resource (if available)
        junk_entries: Junk entries from parsing (unparseable content)
    """

    locale: LocaleCode
    resource_id: ResourceId
    status: LoadStatus
    error: Exception | None = None
    source_path: str | None = None
    junk_entries: tuple[Junk, ...] = ()

    @property
    def is_success(self) -> bool:
        """Check if resource loaded successfully."""
        return self.status == LoadStatus.SUCCESS

    @property
    def is_not_found(self) -> bool:
        """Check if resource was not found (expected for optional locales)."""
        return self.status == LoadStatus.NOT_FOUND

    @property
    def is_error(self) -> bool:
        """Check if resource load failed with an error."""
        return self.status == LoadStatus.ERROR

    @property
    def has_junk(self) -> bool:
        """Check if resource had unparseable content (Junk entries)."""
        return len(self.junk_entries) > 0


@dataclass(frozen=True, slots=True)
class LoadSummary:
    """Immutable aggregate of resource load results from FluentLocalization initialization.

    Provides aggregated information about resource loading success/failure
    across all locales. All statistics are computed properties derived from
    the ``results`` tuple.

    Attributes:
        results: All individual load results (immutable tuple)

    Example:
        >>> l10n = FluentLocalization(['en', 'de'], ['ui.ftl'], loader)
        >>> summary = l10n.get_load_summary()
        >>> if summary.errors > 0:
        ...     for result in summary.get_errors():
        ...         print(f"Failed: {result.locale}/{result.resource_id}: {result.error}")
        >>> if summary.has_junk:
        ...     for result in summary.get_with_junk():
        ...         print(f"Junk in {result.source_path}: {len(result.junk_entries)} entries")
    """

    results: tuple[ResourceLoadResult, ...]

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"LoadSummary(total={self.total_attempted}, "
            f"ok={self.successful}, "
            f"not_found={self.not_found}, "
            f"errors={self.errors}, "
            f"junk={self.junk_count})"
        )

    @property
    def total_attempted(self) -> int:
        """Total number of load attempts."""
        return len(self.results)

    @property
    def successful(self) -> int:
        """Number of successful loads."""
        return sum(1 for r in self.results if r.is_success)

    @property
    def not_found(self) -> int:
        """Number of resources not found."""
        return sum(1 for r in self.results if r.is_not_found)

    @property
    def errors(self) -> int:
        """Number of load errors."""
        return sum(1 for r in self.results if r.is_error)

    @property
    def junk_count(self) -> int:
        """Total number of Junk entries across all resources."""
        return sum(len(r.junk_entries) for r in self.results)

    def get_errors(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results with errors."""
        return tuple(r for r in self.results if r.is_error)

    def get_not_found(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results where resource was not found."""
        return tuple(r for r in self.results if r.is_not_found)

    def get_successful(self) -> tuple[ResourceLoadResult, ...]:
        """Get all successful load results."""
        return tuple(r for r in self.results if r.is_success)

    def get_by_locale(self, locale: LocaleCode) -> tuple[ResourceLoadResult, ...]:
        """Get all results for a specific locale."""
        return tuple(r for r in self.results if r.locale == locale)

    def get_with_junk(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results with Junk entries (unparseable content)."""
        return tuple(r for r in self.results if r.has_junk)

    def get_all_junk(self) -> tuple[Junk, ...]:
        """Get all Junk entries across all resources.

        Returns:
            Flattened tuple of all Junk entries from all resources.
        """
        junk_list: list[Junk] = []
        for result in self.results:
            junk_list.extend(result.junk_entries)
        return tuple(junk_list)

    @property
    def has_errors(self) -> bool:
        """Check if any resources failed to load with errors."""
        return self.errors > 0

    @property
    def has_junk(self) -> bool:
        """Check if any resources had Junk entries (unparseable content)."""
        return self.junk_count > 0

    @property
    def all_successful(self) -> bool:
        """Check if all attempted resources loaded successfully.

        Success means no I/O errors and all files were found. Resources with
        Junk entries (unparseable content) are still considered "successful"
        because the parse operation completed.

        For stricter validation that also checks for Junk, use all_clean.

        Returns:
            True if errors == 0 and not_found == 0, regardless of junk_count
        """
        return self.errors == 0 and self.not_found == 0

    @property
    def all_clean(self) -> bool:
        """Check if all resources loaded successfully without any Junk entries.

        Stricter than all_successful: requires no errors, all files found,
        AND zero Junk entries. Use this for validation workflows where
        unparseable content should be treated as a failure.

        Returns:
            True if errors == 0 and not_found == 0 and junk_count == 0
        """
        return self.errors == 0 and self.not_found == 0 and self.junk_count == 0
