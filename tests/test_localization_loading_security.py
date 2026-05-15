"""Security-boundary tests for filesystem resource loading."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from ftllexengine.localization.loading import PathResourceLoader


class TestPathResourceLoaderSecureOpen:
    """Secure-open helpers should fail closed on path and file boundary issues."""

    def test_is_safe_path_accepts_descendant_inside_root(self, tmp_path: Path) -> None:
        """Resolved descendants under the trusted root should be accepted."""
        base_dir = tmp_path / "locales"
        child = base_dir / "en" / "main.ftl"
        child.parent.mkdir(parents=True)
        child.write_text("msg = inside", encoding="utf-8")

        assert PathResourceLoader._is_safe_path(base_dir, child) is True

    def test_is_safe_path_rejects_escape_outside_root(self, tmp_path: Path) -> None:
        """Resolved paths outside the trusted root must be rejected."""
        base_dir = tmp_path / "locales"
        base_dir.mkdir()
        outside = tmp_path / "outside.ftl"
        outside.write_text("msg = outside", encoding="utf-8")

        assert PathResourceLoader._is_safe_path(base_dir, outside) is False

    def test_open_secure_file_fd_rejects_root_directory_as_resource(self, tmp_path: Path) -> None:
        """A resource path must identify a file beneath the resolved root."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        loader = PathResourceLoader(str(locales_dir / "{locale}"), root_dir=str(locales_dir))

        with pytest.raises(ValueError, match="does not identify a file"):
            loader._open_secure_file_fd(loader._resolved_root)

    def test_open_secure_file_fd_can_fall_back_when_dir_fd_walking_is_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The fallback path remains covered for platforms without dir-fd support."""
        locales_dir = tmp_path / "locales"
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        target = en_dir / "main.ftl"
        target.write_text("msg = fallback", encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"), root_dir=str(locales_dir))
        monkeypatch.setattr(os, "supports_dir_fd", set())
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)

        file_fd = loader._open_secure_file_fd(target)
        try:
            assert os.read(file_fd, 64) == b"msg = fallback"
        finally:
            os.close(file_fd)

    def test_open_secure_file_fd_posix_closes_non_regular_targets(self, tmp_path: Path) -> None:
        """Directory targets must be rejected after open without leaking file descriptors."""
        locales_dir = tmp_path / "locales"
        en_dir = locales_dir / "en"
        en_dir.mkdir(parents=True)
        loader = PathResourceLoader(str(locales_dir / "{locale}"), root_dir=str(locales_dir))

        with pytest.raises(OSError, match="regular file"):
            loader._open_secure_file_fd_posix(("en",))

    def test_open_secure_file_fd_fallback_rejects_symlink(self, tmp_path: Path) -> None:
        """Symlink resources must be refused by the fallback path."""
        target = tmp_path / "target.ftl"
        target.write_text("msg = safe", encoding="utf-8")
        symlink = tmp_path / "link.ftl"
        symlink.symlink_to(target)

        with pytest.raises(OSError, match="Symlink resources are not allowed"):
            PathResourceLoader._open_secure_file_fd_fallback(symlink)

    def test_open_secure_file_fd_fallback_returns_fd_for_regular_file(self, tmp_path: Path) -> None:
        """Fallback opening should succeed for an ordinary regular file."""
        target = tmp_path / "main.ftl"
        target.write_text("msg = regular", encoding="utf-8")

        file_fd = PathResourceLoader._open_secure_file_fd_fallback(target)
        try:
            assert os.read(file_fd, 64) == b"msg = regular"
        finally:
            os.close(file_fd)

    def test_open_secure_file_fd_fallback_rejects_directory_target(self, tmp_path: Path) -> None:
        """Fallback opening must reject non-regular directory targets."""
        directory = tmp_path / "not-a-file"
        directory.mkdir()

        with pytest.raises(OSError, match="regular file"):
            PathResourceLoader._open_secure_file_fd_fallback(directory)

    def test_open_secure_file_fd_fallback_detects_target_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The fallback path must reject TOCTOU-style inode swaps."""
        target = tmp_path / "main.ftl"
        target.write_text("msg = race", encoding="utf-8")
        real_fstat = os.fstat

        def mismatched_fstat(file_fd: int) -> SimpleNamespace:
            post_stat = real_fstat(file_fd)
            return SimpleNamespace(
                st_mode=post_stat.st_mode,
                st_dev=post_stat.st_dev,
                st_ino=post_stat.st_ino + 1,
            )

        monkeypatch.setattr(os, "fstat", mismatched_fstat)

        with pytest.raises(OSError, match="changed while opening"):
            PathResourceLoader._open_secure_file_fd_fallback(target)

    def test_require_regular_file_rejects_non_regular_mode(self) -> None:
        """The regular-file gate should reject directory modes directly."""
        with pytest.raises(OSError, match="must point to a regular file"):
            PathResourceLoader._require_regular_file(stat.S_IFDIR, "directory")


class TestPathResourceLoaderBoundedRead:
    """Read-side quotas must fire before oversized content becomes visible."""

    def test_read_text_bounded_rejects_byte_overflow(self, tmp_path: Path) -> None:
        """Byte quotas should trip before the decoded payload is returned."""
        target = tmp_path / "bytes.ftl"
        target.write_text("abcd", encoding="utf-8")
        loader = PathResourceLoader(
            str(tmp_path / "{locale}"),
            root_dir=str(tmp_path),
            max_source_bytes=3,
        )

        file_fd = os.open(target, os.O_RDONLY)
        try:
            with pytest.raises(ValueError, match="Resource byte length"):
                loader._read_text_bounded(file_fd)
        finally:
            os.close(file_fd)

    def test_read_text_bounded_rejects_character_overflow_during_stream(self, tmp_path: Path) -> None:
        """Character quotas should fail once decoded output crosses the bound."""
        target = tmp_path / "chars.ftl"
        target.write_text("abcd", encoding="utf-8")
        loader = PathResourceLoader(
            str(tmp_path / "{locale}"),
            root_dir=str(tmp_path),
            max_source_chars=3,
        )

        file_fd = os.open(target, os.O_RDONLY)
        try:
            with pytest.raises(ValueError, match="Resource text length"):
                loader._read_text_bounded(file_fd)
        finally:
            os.close(file_fd)

    def test_read_text_bounded_rejects_character_overflow_from_decoder_tail(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The final decoder flush is budgeted too, not only streamed chunks."""
        target = tmp_path / "tail.ftl"
        target.write_text("x", encoding="utf-8")
        loader = PathResourceLoader(
            str(tmp_path / "{locale}"),
            root_dir=str(tmp_path),
            max_source_chars=1,
        )

        class TailOnlyDecoder:
            """Buffer bytes until final flush to exercise the tail-budget guard."""

            def __init__(self, _errors: str) -> None:
                self._buffer = bytearray()

            def decode(self, chunk: bytes, *, final: bool = False) -> str:
                if final:
                    return "zz"
                self._buffer.extend(chunk)
                return ""

        monkeypatch.setattr(
            "ftllexengine.localization.loading.codecs.getincrementaldecoder",
            lambda _encoding: TailOnlyDecoder,
        )

        file_fd = os.open(target, os.O_RDONLY)
        try:
            with pytest.raises(ValueError, match="Resource text length"):
                loader._read_text_bounded(file_fd)
        finally:
            os.close(file_fd)
