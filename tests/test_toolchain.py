"""Tests for the Windows toolchain installer and discovery helpers."""

import hashlib
import io
import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

import httpstan._toolchain as toolchain
import httpstan._windows as windows


def test_toolchain_directory_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A custom toolchain root takes precedence over the default."""
    root = tmp_path / "Stan tools"
    monkeypatch.setenv("HTTPSTAN_TOOLCHAIN_DIR", str(root))
    assert toolchain.toolchain_directory() == root.resolve()


def test_download_digest(tmp_path: Path) -> None:
    """Verify download integrity and reject incorrect hashes."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"test toolchain asset")
    toolchain.download(source.as_uri(), target, hashlib.sha256(source.read_bytes()).hexdigest())
    assert source.read_bytes() == target.read_bytes()
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        toolchain.download(source.as_uri(), target, "0" * 64)
    assert not target.exists()


def test_explicit_toolchain_overrides_active_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An explicit portable root takes precedence over an active toolchain."""
    monkeypatch.setenv("HTTPSTAN_TOOLCHAIN_DIR", str(tmp_path))
    monkeypatch.setenv("INCLUDE", "active")
    monkeypatch.setenv("LIB", "active")
    portable = Mock(return_value={"PATH": "portable"})
    monkeypatch.setattr(toolchain, "portable_environment", portable)
    assert toolchain.toolchain_environment("cl") == {"PATH": "portable"}
    assert portable.call_args.args[:2] == (tmp_path.resolve(), "cl")
    assert os.environ["INCLUDE"] == "active"


def test_default_toolchain_discovery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Discover the default portable installation before Visual Studio."""
    monkeypatch.delenv("HTTPSTAN_TOOLCHAIN_DIR", raising=False)
    monkeypatch.delenv("INCLUDE", raising=False)
    monkeypatch.delenv("LIB", raising=False)
    monkeypatch.setattr(toolchain, "toolchain_directory", lambda: tmp_path)
    portable = Mock(return_value={"PATH": "portable"})
    official = Mock(return_value={"PATH": "official"})
    monkeypatch.setattr(toolchain, "portable_environment", portable)
    monkeypatch.setattr(toolchain, "official_environment", official)
    assert toolchain.toolchain_environment("cl") == {"PATH": "official"}
    (tmp_path / "msvc").mkdir()
    (tmp_path / "msvc" / "setup_x64.bat").touch()
    assert toolchain.toolchain_environment("cl") == {"PATH": "portable"}
    assert toolchain.toolchain_environment("clang-cl") == {"PATH": "official"}


def test_active_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An activated compatible toolchain is reused when no override is set."""
    monkeypatch.delenv("HTTPSTAN_TOOLCHAIN_DIR", raising=False)
    monkeypatch.setenv("INCLUDE", "active-include")
    monkeypatch.setenv("LIB", "active-lib")
    monkeypatch.setattr(toolchain, "toolchain_directory", lambda: tmp_path)
    monkeypatch.setattr(toolchain.shutil, "which", Mock(return_value="compiler.exe"))
    assert toolchain.toolchain_environment("cl")["INCLUDE"] == "active-include"


def test_compile_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The selected compiler and its environment are passed to the subprocess."""
    env = {"PATH": "compiler-path", "INCLUDE": "compiler-include", "LIB": "compiler-lib"}
    compiler = Mock(return_value="compiler.exe")
    run = Mock(return_value="compiled")
    monkeypatch.setattr(windows, "compiler", compiler)
    monkeypatch.setattr(windows, "run", run)
    result = windows.compile_cpp("cl", tmp_path / "model.cpp", tmp_path / "model.obj", env=env)
    assert result == "compiled"
    compiler.assert_called_once_with("cl", env)
    assert run.call_args.args[-1] == env


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch activation")
def test_activate_batch(tmp_path: Path) -> None:
    """Capture batch variables without modifying the caller environment."""
    batch = tmp_path / "test activation.bat"
    batch.write_text('@echo off\nset "HTTPSTAN_ACTIVATION_TEST=works"\n')
    env = os.environ.copy()
    env.pop("HTTPSTAN_ACTIVATION_TEST", None)
    activated = toolchain.activate_batch(batch, env)
    assert activated["HTTPSTAN_ACTIVATION_TEST"] == "works"
    assert "HTTPSTAN_ACTIVATION_TEST" not in env


def test_install_portable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install the matching toolchain and reuse existing downloads."""

    def fake_download(url: str, target: Path, sha256: str) -> None:
        """Create a small local substitute for each downloaded asset."""
        if target.name == toolchain.LLVM_ARCHIVE:
            with tarfile.open(target, "w:xz") as tar:
                member = tarfile.TarInfo("llvm-dist/bin/clang-cl.exe")
                member.size = 1
                tar.addfile(member, io.BytesIO(b"x"))
        else:
            target.write_text("# portable installer")

    def fake_run(args: list, cwd: Path, check: bool) -> None:
        """Simulate the upstream installer output."""
        (cwd / "msvc").mkdir()
        (cwd / "msvc" / "setup_x64.bat").touch()

    root = tmp_path / "toolchain"
    with monkeypatch.context() as patch:
        patch.setattr(toolchain.sys, "platform", "win32")
        patch.setattr(toolchain, "download", fake_download)
        patch.setattr(toolchain.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="license terms"):
            toolchain.install_portable(root, "cl")
        toolchain.install_portable(root, "cl", accept_license=True)
        toolchain.install_portable(root, "clang-cl")
        toolchain.install_portable(root, "clang-cl")
    assert (root / "msvc" / "setup_x64.bat").is_file()
    assert (root / "llvm" / "bin" / "clang-cl.exe").is_file()
