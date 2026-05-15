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

import codecs
import os
import stat as stat_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ftllexengine.constants import MAX_SOURCE_SIZE
from ftllexengine.core._limits import LimitArg, resolve_limit_arg
from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.enums import LoadStatus

if TYPE_CHECKING:
    from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId, ResourceId
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
        >>> class DiskLoader:  # doctest: +SKIP
        ...     def load(self, locale: str, resource_id: str) -> str:
        ...         path = Path(f"locales/{locale}/{resource_id}")
        ...         return path.read_text(encoding="utf-8")
        ...     def describe_path(self, locale: str, resource_id: str) -> str:
        ...         return f"locales/{locale}/{resource_id}"
        ...
        >>> loader = DiskLoader()  # doctest: +SKIP
        >>> l10n = FluentLocalization(['en', 'fr'], ['main.ftl'], loader)  # doctest: +SKIP
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
        >>> loader = PathResourceLoader("locales/{locale}")  # doctest: +SKIP
        >>> ftl = loader.load("en", "main.ftl")  # doctest: +SKIP
        # Loads from: locales/en/main.ftl

    Attributes:
        base_path: Path template with {locale} placeholder
        root_dir: Fixed root directory for path traversal validation.
                  Defaults to parent of base_path if not specified.
        max_source_bytes: Maximum bytes read from disk before aborting.
        max_source_chars: Maximum decoded characters produced before aborting.
    """

    base_path: str
    root_dir: str | None = None
    max_source_bytes: LimitArg = None
    max_source_chars: LimitArg = None
    _resolved_root: Path = field(init=False, repr=False)
    _effective_max_source_bytes: int | None = field(init=False, repr=False)
    _effective_max_source_chars: int | None = field(init=False, repr=False)

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
        object.__setattr__(
            self,
            "_effective_max_source_bytes",
            resolve_limit_arg(
                self.max_source_bytes,
                field_name="max_source_bytes",
                default=MAX_SOURCE_SIZE,
            ),
        )
        object.__setattr__(
            self,
            "_effective_max_source_chars",
            resolve_limit_arg(
                self.max_source_chars,
                field_name="max_source_chars",
                default=MAX_SOURCE_SIZE,
            ),
        )

    @staticmethod
    def _validate_locale(locale: LocaleCode) -> LocaleCode:
        """Validate and canonicalize locale code for path substitution.

        Args:
            locale: Locale code to validate

        Raises:
            TypeError: If locale is not a string
            ValueError: If locale is blank or structurally invalid
        """
        return require_locale_code(locale, "locale")

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
        normalized_locale = self._validate_locale(locale)
        locale_path = self.base_path.replace("{locale}", normalized_locale)
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
        normalized_locale = self._validate_locale(locale)
        self._validate_resource_id(resource_id)

        # Use replace() instead of format() to avoid KeyError if template
        # contains other braces like "{version}" for future extensibility.
        locale_path = self.base_path.replace("{locale}", normalized_locale)
        lexical_base_dir = Path(locale_path).resolve(strict=False)
        lexical_full_path = (lexical_base_dir / resource_id).resolve(strict=False)

        try:
            lexical_base_dir.relative_to(self._resolved_root)
            lexical_full_path.relative_to(self._resolved_root)
        except ValueError as error:
            msg = (
                "Path traversal detected: lexical path escapes root directory. "
                f"locale='{locale}', resource_id='{resource_id}'"
            )
            raise ValueError(msg) from error

        file_fd = self._open_secure_file_fd(lexical_full_path)
        try:
            return self._read_text_bounded(file_fd)
        finally:
            os.close(file_fd)

    def _open_secure_file_fd(self, full_path: Path) -> int:
        """Open a resource file without trusting symlinks or TOCTOU windows."""
        relative_parts = full_path.relative_to(self._resolved_root).parts
        if len(relative_parts) == 0:
            msg = f"Resource path {full_path!s} does not identify a file"
            raise ValueError(msg)

        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            return self._open_secure_file_fd_posix(relative_parts)
        return self._open_secure_file_fd_fallback(full_path)

    def _open_secure_file_fd_posix(self, relative_parts: tuple[str, ...]) -> int:
        """Open one resource via root-relative file descriptors on POSIX.

        Premise:
            Validation and open must happen in the same ownership domain.

        Reason:
            Walking the path one component at a time with ``dir_fd`` and
            ``O_NOFOLLOW`` closes the race between "path looked safe" and
            "path was opened".
        """
        root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(self._resolved_root, root_flags)
        current_fd = root_fd
        file_fd: int | None = None
        try:
            for part in relative_parts[:-1]:
                next_fd = os.open(
                    part,
                    root_flags | nofollow,
                    dir_fd=current_fd,
                )
                if current_fd != root_fd:
                    os.close(current_fd)
                current_fd = next_fd

            file_fd = os.open(
                relative_parts[-1],
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow,
                dir_fd=current_fd,
            )
            file_stat = os.fstat(file_fd)
            self._require_regular_file(file_stat.st_mode, relative_parts[-1])
            return file_fd
        except Exception:
            if file_fd is not None:
                os.close(file_fd)
            raise
        finally:
            if current_fd != root_fd:
                os.close(current_fd)
            os.close(root_fd)

    @staticmethod
    def _open_secure_file_fd_fallback(full_path: Path) -> int:
        """Fallback open path when POSIX dir-fd walking is unavailable."""
        pre_stat = os.lstat(full_path)
        if stat_module.S_ISLNK(pre_stat.st_mode):
            msg = f"Symlink resources are not allowed: {full_path!s}"
            raise OSError(msg)
        file_fd = os.open(full_path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        post_stat = os.fstat(file_fd)
        if not stat_module.S_ISREG(post_stat.st_mode):
            os.close(file_fd)
            msg = f"Resource path must point to a regular file: {full_path!s}"
            raise OSError(msg)
        if (
            hasattr(pre_stat, "st_dev")
            and hasattr(pre_stat, "st_ino")
            and (pre_stat.st_dev, pre_stat.st_ino) != (post_stat.st_dev, post_stat.st_ino)
        ):
            os.close(file_fd)
            msg = f"Resource path changed while opening: {full_path!s}"
            raise OSError(msg)
        return file_fd

    @staticmethod
    def _require_regular_file(mode: int, display_path: str) -> None:
        """Reject non-regular filesystem objects at the ownership seam."""
        if stat_module.S_ISREG(mode):
            return
        msg = f"Resource path must point to a regular file: {display_path!r}"
        raise OSError(msg)

    def _read_text_bounded(self, file_fd: int) -> str:
        """Read UTF-8 text with byte and decoded-character budgets."""
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        byte_total = 0
        char_total = 0
        parts: list[str] = []

        while True:
            chunk = os.read(file_fd, 65_536)
            if not chunk:
                break
            byte_total += len(chunk)
            if (
                self._effective_max_source_bytes is not None
                and byte_total > self._effective_max_source_bytes
            ):
                msg = (
                    f"Resource byte length ({byte_total:,}) exceeds maximum "
                    f"({self._effective_max_source_bytes:,})."
                )
                raise ValueError(msg)

            decoded = decoder.decode(chunk, final=False)
            char_total += len(decoded)
            if (
                self._effective_max_source_chars is not None
                and char_total > self._effective_max_source_chars
            ):
                msg = (
                    f"Resource text length ({char_total:,} characters) exceeds maximum "
                    f"({self._effective_max_source_chars:,})."
                )
                raise ValueError(msg)
            parts.append(decoded)

        tail = decoder.decode(b"", final=True)
        char_total += len(tail)
        if (
            self._effective_max_source_chars is not None
            and char_total > self._effective_max_source_chars
        ):
            msg = (
                f"Resource text length ({char_total:,} characters) exceeds maximum "
                f"({self._effective_max_source_chars:,})."
            )
            raise ValueError(msg)
        parts.append(tail)
        return "".join(parts)


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
        >>> def log_fallback(info: FallbackInfo) -> None:  # doctest: +SKIP
        ...     print(f"Fallback: {info.message_id} resolved from "
        ...           f"{info.resolved_locale} (requested {info.requested_locale})")
        >>> l10n = FluentLocalization(['lv', 'en'], on_fallback=log_fallback)  # doctest: +SKIP
    """

    requested_locale: LocaleCode
    resolved_locale: LocaleCode
    message_id: MessageId


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
        >>> l10n = FluentLocalization(['en', 'de'], ['ui.ftl'], loader)  # doctest: +SKIP
        >>> summary = l10n.get_load_summary()  # doctest: +SKIP
        >>> if summary.errors > 0:  # doctest: +SKIP
        ...     for result in summary.get_errors():
        ...         print(f"Failed: {result.locale}/{result.resource_id}: {result.error}")
        >>> if summary.has_junk:  # doctest: +SKIP
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
        return tuple(j for r in self.results for j in r.junk_entries)

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
