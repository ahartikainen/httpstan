"""Install and discover the Windows C++ toolchain used by httpstan."""

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict

PORTABLE_URL = (
    "https://gist.githubusercontent.com/mmozeiko/7f3162ec2988e81e56d5c4e22cde9977/"
    "raw/49b58850aa5e5c1e65f090d4651ee76607883e11/portable-msvc.py"
)
PORTABLE_SHA256 = "1791cccca594ff083ce8d3e0a139e6156d2c312e24332a909e608010f0230a51"
LLVM_VERSION = "20.1.8"
LLVM_ARCHIVE = f"clang+llvm-{LLVM_VERSION}-x86_64-pc-windows-msvc.tar.xz"
LLVM_URL = f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{LLVM_VERSION}/{LLVM_ARCHIVE}"
LLVM_SHA256 = "f229769f11d6a6edc8ada599c0cda964b7dee6ab1a08c6cf9dd7f513e85b107f"
LICENSE_URL = "https://visualstudio.microsoft.com/license-terms/"


def toolchain_directory() -> Path:
    """Return the persistent portable toolchain directory, honoring the environment override."""
    override = os.environ.get("HTTPSTAN_TOOLCHAIN_DIR")
    if override:
        return Path(os.path.expandvars(override)).expanduser().resolve()
    import appdirs

    return Path(appdirs.user_data_dir("httpstan", appauthor=False)) / "toolchain"


def download(url: str, target: Path, sha256: str) -> None:
    """Download a pinned toolchain asset and verify its SHA-256 digest."""
    print(f"Downloading {url}", flush=True)
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        target.unlink()
        raise RuntimeError(f"SHA-256 mismatch for {url}")
    print(f"Verified {target.name}: {target.stat().st_size:,} bytes", flush=True)


def install_portable(root: Path, family: str, accept_license: bool = False) -> None:
    """Install portable MSVC and, for clang-cl wheels, LLVM into root.

    Existing installations are reused. Downloading Microsoft components
    requires explicit license acceptance. The installer does not change PATH.
    """
    if sys.platform != "win32":
        raise RuntimeError("Portable MSVC installation is supported on Windows only")
    if family not in {"cl", "clang-cl"}:
        raise ValueError(f"Unsupported compiler: {family}")
    msvc = root / "msvc"
    llvm = root / "llvm"
    if not (msvc / "setup_x64.bat").is_file():
        if msvc.exists():
            raise RuntimeError(f"Incomplete MSVC installation: {msvc}. Remove or relocate it before retrying.")
        if not accept_license:
            raise RuntimeError(f"Review the Microsoft Build Tools and SDK license terms: {LICENSE_URL}")
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="install-", dir=root) as tmp:
            work = Path(tmp)
            script = work / "portable-msvc.py"
            download(PORTABLE_URL, script, PORTABLE_SHA256)
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--vs",
                    "2022",
                    "--target",
                    "x64",
                    "--host",
                    "x64",
                    "--msvc-version",
                    os.environ.get("HTTPSTAN_PORTABLE_MSVC_VERSION") or "14.44",
                    "--sdk-version",
                    os.environ.get("HTTPSTAN_PORTABLE_SDK_VERSION") or "26100",
                    "--accept-license",
                ],
                cwd=work,
                check=True,
            )
            if not (work / "msvc" / "setup_x64.bat").is_file():
                raise RuntimeError("Portable MSVC installer did not produce setup_x64.bat")
            (work / "msvc").rename(msvc)
    if family == "clang-cl" and not (llvm / "bin" / "clang-cl.exe").is_file():
        if llvm.exists():
            raise RuntimeError(f"Incomplete LLVM installation: {llvm}. Remove or relocate it before retrying.")
        with tempfile.TemporaryDirectory(prefix="install-", dir=root) as tmp:
            work = Path(tmp)
            archive = work / LLVM_ARCHIVE
            download(LLVM_URL, archive, LLVM_SHA256)
            extracted = work / "extracted"
            extracted.mkdir()
            with tarfile.open(archive, "r:xz") as tar:
                tar.extractall(extracted, filter="data")
            candidates = [p.parent.parent for p in extracted.glob("*/bin/clang-cl.exe")]
            if (extracted / "bin" / "clang-cl.exe").is_file():
                candidates.append(extracted)
            if len(candidates) != 1:
                raise RuntimeError("LLVM archive did not contain a single clang-cl installation")
            candidates[0].rename(llvm)
    print(f"Portable toolchain: {root}", flush=True)


def activate_batch(batch: Path, env: Dict[str, str]) -> Dict[str, str]:
    """Run a Windows activation script and return its environment without changing the parent."""
    with tempfile.TemporaryDirectory(prefix="httpstan-env-") as tmp:
        script = Path(tmp) / "activate.cmd"
        script.write_text('@echo off\ncall "%HTTPSTAN_ACTIVATE_BATCH%" >&2\nif errorlevel 1 exit /b 1\nset\n')
        env = {**env, "HTTPSTAN_ACTIVATE_BATCH": str(batch)}
        result = subprocess.run(
            [env.get("COMSPEC", "cmd.exe"), "/d", "/u", "/c", "call", str(script)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            encoding = "utf-16-le" if b"\0" in result.stderr[:200] else "utf-8"
            diagnostics = result.stderr.decode(encoding, errors="replace")
            raise RuntimeError(f"Toolchain activation failed ({result.returncode}): {batch}\n{diagnostics[-4000:]}")
    activated = {}
    for line in result.stdout.decode("utf-16-le").splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            activated[key.upper()] = value
    activated.pop("HTTPSTAN_ACTIVATE_BATCH", None)
    return activated


def unactivated_environment(env: Dict[str, str]) -> Dict[str, str]:
    """Remove Visual Studio and SDK activation variables and paths from an environment."""
    env = {key.upper(): value for key, value in env.items()}
    for key in tuple(env):
        if key in {
            "INCLUDE",
            "LIB",
            "LIBPATH",
            "VCINSTALLDIR",
            "VSINSTALLDIR",
            "VCTOOLSINSTALLDIR",
            "VCTOOLSVERSION",
            "WINDOWSSDKDIR",
            "WINDOWSSDKVERSION",
            "UNIVERSALCRTSDKDIR",
            "UCRTVERSION",
        } or key.startswith("VSCMD_"):
            env.pop(key)
    env["PATH"] = os.pathsep.join(
        p
        for p in env.get("PATH", "").split(os.pathsep)
        if "microsoft visual studio" not in p.lower() and "windows kits" not in p.lower()
    )
    return env


def portable_environment(root: Path, family: str, env: Dict[str, str]) -> Dict[str, str]:
    """Activate and verify a portable MSVC/SDK installation and optional LLVM."""
    msvc = (root / "msvc").resolve()
    batch = msvc / "setup_x64.bat"
    if not batch.is_file():
        raise RuntimeError(f"Portable MSVC not found: {batch}. Run python -m httpstan install portable")
    activated = activate_batch(batch, unactivated_environment(env))
    if family == "clang-cl":
        llvm = root / "llvm" / "bin"
        if not (llvm / "clang-cl.exe").is_file():
            raise RuntimeError(f"Portable LLVM not found: {llvm}. Run python -m httpstan install portable")
        activated["PATH"] = str(llvm) + os.pathsep + activated["PATH"]
        actual = shutil.which("clang-cl.exe", path=activated["PATH"])
        if not actual or Path(actual).resolve() != (llvm / "clang-cl.exe").resolve():
            raise RuntimeError(f"Portable clang-cl.exe was not resolved inside {llvm}: {actual}")
    for name in ("cl", "link", "lib"):
        actual = shutil.which(name + ".exe", path=activated["PATH"])
        if not actual or not Path(actual).resolve().is_relative_to(msvc):
            raise RuntimeError(f"Portable {name}.exe was not resolved inside {msvc}: {actual}")
    for key in ("INCLUDE", "LIB"):
        values = [value for value in activated.get(key, "").split(os.pathsep) if value]
        if not values or any(not Path(value).resolve().is_relative_to(msvc) for value in values):
            raise RuntimeError(f"Portable {key} must contain only paths inside {msvc}")
    return activated


def official_environment(family: str, env: Dict[str, str]) -> Dict[str, str]:
    """Discover and activate an installed Visual Studio 2022 x64 toolchain."""
    vswhere = (
        Path(env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    if not vswhere.is_file():
        raise RuntimeError("Visual Studio Build Tools not found")
    root = subprocess.check_output(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-version",
            "[17.0,18.0)",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
            "-utf8",
        ],
        env=env,
        encoding="utf-8",
    ).strip()
    if not root:
        raise RuntimeError("Visual Studio 2022 C++ Build Tools not found")
    activated = activate_batch(Path(root) / "VC/Auxiliary/Build/vcvars64.bat", unactivated_environment(env))
    if family == "clang-cl":
        existing = shutil.which("clang-cl.exe", path=env.get("PATH", ""))
        directories = [
            Path(env.get("PROGRAMFILES", r"C:\Program Files")) / "LLVM/bin",
            Path(root) / "VC/Tools/Llvm/x64/bin",
        ]
        if existing:
            directories.insert(0, Path(existing).parent)
        for directory in directories:
            if (directory / "clang-cl.exe").is_file():
                activated["PATH"] = str(directory) + os.pathsep + activated["PATH"]
                break
    if not shutil.which(family + ".exe", path=activated["PATH"]):
        raise RuntimeError(f"{family}.exe not found in the activated Visual Studio toolchain")
    return activated


def toolchain_environment(family: str) -> Dict[str, str]:
    """Resolve the toolchain for a model build without downloading or modifying the process environment.

    An explicit portable directory takes precedence over an activated compiler,
    followed by the default portable installation and installed Visual Studio.
    """
    env = {key.upper(): value for key, value in os.environ.items()}
    root = toolchain_directory()
    if env.get("HTTPSTAN_TOOLCHAIN_DIR"):
        return portable_environment(root, family, env)
    if (
        env.get("INCLUDE")
        and env.get("LIB")
        and all(shutil.which(name + ".exe", path=env.get("PATH", "")) for name in (family, "link", "lib"))
    ):
        return env
    if (root / "msvc" / "setup_x64.bat").is_file() and (
        family == "cl" or (root / "llvm" / "bin" / "clang-cl.exe").is_file()
    ):
        return portable_environment(root, family, env)
    try:
        return official_environment(family, env)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"No usable {family} toolchain found. Install Visual Studio Build Tools or run "
            f"python -m httpstan install portable. ({exc})"
        ) from exc
