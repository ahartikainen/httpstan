"""Build and test Windows wheels with stage-specific logs."""

import argparse
import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "windows-logs"
BUILD = ROOT / "build" / "win"
spec = importlib.util.spec_from_file_location("httpstan_toolchain", ROOT / "httpstan" / "_toolchain.py")
assert spec is not None and spec.loader is not None
toolchain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toolchain)
PROFILES = (
    "official-clang",
    "official-msvc",
    "portable-clang",
    "portable-msvc",
    "official-clang-od",
    "official-msvc-od",
)


def stage(name: str, command: List[str], cwd: Path = ROOT, env: Optional[dict] = None) -> None:
    """Run one CI stage and save its combined output and exit status."""
    LOGS.mkdir(exist_ok=True)
    command = [str(x) for x in command]
    if not Path(command[0]).is_absolute():
        executable = shutil.which(command[0], path=(env or os.environ).get("PATH"))
        if executable:
            command[0] = executable
    path = LOGS / (name + ".log")
    start = time.monotonic()
    invocation = subprocess.list2cmdline([str(x) for x in command])
    print(f"\n=== STAGE {name} ===\n{invocation}", flush=True)
    with path.open("w", encoding="utf-8") as log:
        log.write(f"cwd={cwd}\n{invocation}\n")
        log.flush()
        with subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            status = process.wait()
        result = f"=== STAGE {name} {'PASS' if status == 0 else 'FAIL'} exit={status} seconds={time.monotonic()-start:.1f} ==="
        print(result, flush=True)
        log.write(result + "\n")
    with (LOGS / "summary.txt").open("a", encoding="utf-8") as summary:
        summary.write(result + "\n")
    if status:
        raise SystemExit(status)


def configure(profile: str) -> dict:
    """Activate the selected official or portable toolchain."""
    env = {key.upper(): value for key, value in os.environ.items()}
    family = "clang-cl" if "clang" in profile else "cl"
    if profile.startswith("portable"):
        root = BUILD / "portable"
        toolchain.install_portable(root, family, env.get("HTTPSTAN_ACCEPT_MSVC_LICENSE", "").lower() == "yes")
        env = toolchain.portable_environment(root, family, env)
    else:
        env = toolchain.official_environment(family, env)
    # Make the dummy setuptools extension use the already activated toolchain.
    env["DISTUTILS_USE_SDK"] = "1"
    env["MSSDK"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Do not inherit arbitrary external compiler flags that change the ABI.
    for name in ("CL", "_CL_", "LINK", "_LINK_", "CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS", "PYTHONPATH"):
        env.pop(name, None)
    info = {
        "profile": profile,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "AF_UNIX": hasattr(socket, "AF_UNIX"),
        "tools": {
            name: shutil.which(name + ".exe", path=env["PATH"])
            for name in ("cl", "clang-cl", "link", "lib", "dumpbin")
        },
        "INCLUDE": env.get("INCLUDE"),
        "LIB": env.get("LIB"),
        "VCToolsVersion": env.get("VCTOOLSVERSION"),
        "WindowsSDKVersion": env.get("WINDOWSSDKVERSION"),
        "VCToolsInstallDir": env.get("VCTOOLSINSTALLDIR"),
        "ImageVersion": env.get("IMAGEVERSION"),
        "ImageOS": env.get("IMAGEOS"),
    }
    text = json.dumps(info, indent=2)
    print(text, flush=True)
    (LOGS / "toolchain.json").write_text(text, encoding="utf-8")
    return env


def validate_wheel(wheel: Path) -> None:
    """Check the Windows wheel tag and required native files."""
    with zipfile.ZipFile(wheel) as archive:
        files = set(archive.namelist())
        required = {
            "httpstan/stanc.exe",
            "httpstan/stan_services.obj",
            "httpstan/windows-build.json",
            "httpstan/_toolchain.py",
            "httpstan/lib/tbb.dll",
            "httpstan/lib/tbb.lib",
            "httpstan/lib/sundials_cvodes.lib",
            "httpstan/lib/sundials_idas.lib",
            "httpstan/lib/sundials_nvecserial.lib",
            "httpstan/lib/sundials_kinsol.lib",
            "httpstan/include/stan/math.hpp",
            "httpstan/include/pybind11/pybind11.h",
            "httpstan/include/boost/version.hpp",
            "httpstan/include/Eigen/Core",
            "httpstan/include/tbb/tbb.h",
            "httpstan/include/rapidjson/document.h",
            "httpstan/empty.cp312-win_amd64.pyd",
        }
        missing = required - files
        if missing or not wheel.name.endswith("win_amd64.whl"):
            raise RuntimeError(f"Wrong wheel tag or missing wheel contents: {wheel.name}, {sorted(missing)}")
        print(f"[wheel] {wheel.name} size={wheel.stat().st_size} members={len(files)}", flush=True)
        (LOGS / "wheel-files.txt").write_text("\n".join(sorted(files)), encoding="utf-8")


def main() -> None:
    """Run the selected build and test stages."""
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=PROFILES, required=True)
    p.add_argument("--through", choices=["headers", "services", "smoke", "full"], default="smoke")
    args = p.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise SystemExit("Windows x64 and CPython 3.12 required")
    LOGS.mkdir(exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    (LOGS / "summary.txt").write_text(f"profile={args.profile} through={args.through}\n", encoding="utf-8")
    env = configure(args.profile)
    family = "clang-cl" if "clang" in args.profile else "cl"
    opt = "Od" if args.profile.endswith("-od") else "O2"
    stage("04-compiler-version", [env["COMSPEC"], "/d", "/c", "cl /Bv 2>&1 & exit /b 0"], env=env)
    if family == "clang-cl":
        stage("05-clang-version", ["clang-cl.exe", "--version"], env=env)
    stage(
        "09-socket-smoke",
        [sys.executable, str(ROOT / "scripts/windows_socket_smoke.py"), "--compiler", family],
        env=env,
    )
    native = [sys.executable, str(ROOT / "scripts/build_windows.py")]
    for number, name in enumerate(("prepare", "headers", "sundials", "link", "services"), 10):
        stage(f"{number}-{name}", [*native, name, "--compiler", family, "--optimization", opt], env=env)
        if args.through == name:
            return
    stage(
        "20-install-build-tools", [sys.executable, "-m", "pip", "install", "poetry~=1.8.0", "setuptools<81"], env=env
    )
    stage("21-wheel", [sys.executable, "-m", "poetry", "build", "-f", "wheel", "-v"], env=env)
    wheels = sorted((ROOT / "dist").glob("*.whl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not wheels:
        raise RuntimeError("No wheel produced")
    wheel = wheels[0].resolve()
    validate_wheel(wheel)
    test_root = Path(tempfile.mkdtemp(prefix="httpstan-test-", dir=os.environ.get("RUNNER_TEMP")))
    print(f"[test] isolated test directory: {test_root}", flush=True)
    venv = test_root / "venv"
    stage("22-test-venv", [sys.executable, "-m", "venv", str(venv)], env=env)
    py = str(venv / "Scripts/python.exe")
    stage(
        "23-install-wheel",
        [
            py,
            "-m",
            "pip",
            "install",
            str(wheel),
            "pytest>=8.3,<9",
            "pytest-asyncio>=0.24,<0.25",
            "apispec[yaml]>=6,<7",
        ],
        env=env,
    )
    stage(
        "24-import-wheel",
        [
            py,
            "-c",
            "import sys, pathlib, httpstan, httpstan.app, httpstan.empty; print(httpstan.__file__); print(httpstan.__version__); assert pathlib.Path(httpstan.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()); httpstan.empty.noop()",
        ],
        cwd=test_root,
        env=env,
    )
    # Compile models without the activated build environment.
    env = toolchain.unactivated_environment(os.environ.copy())
    env.pop("PYTHONPATH", None)
    if args.profile.startswith("portable"):
        env["HTTPSTAN_TOOLCHAIN_DIR"] = str(BUILD / "portable")
        stage(
            "24-portable-cli",
            [py, "-m", "httpstan", "install", "portable", "--accept-license"],
            cwd=test_root,
            env=env,
        )
    else:
        env.pop("HTTPSTAN_TOOLCHAIN_DIR", None)
    # Test the installed package, not the checkout.
    tests = test_root / "installed-tests"
    shutil.copytree(ROOT / "tests", tests, dirs_exist_ok=True)
    smoke = [
        str(tests / name)
        for name in (
            "test_health_check.py",
            "test_windows_smoke.py",
            "test_cvodes.py",
            "test_fixed_param.py",
            "test_log_prob_grad.py",
        )
    ]
    if args.through == "full":
        stage(
            "26-full-pytest",
            [py, "-m", "pytest", "-s", "-vv", "--log-cli-level=INFO", "--asyncio-mode=auto", str(tests)],
            cwd=test_root,
            env=env,
        )
    else:
        stage(
            "25-runtime-smoke",
            [py, "-m", "pytest", "-s", "-vv", "--log-cli-level=INFO", "--asyncio-mode=auto", *smoke],
            cwd=test_root,
            env=env,
        )
    # Keep the local httpstan wheel when installing PyStan.
    stage(
        "27-install-pystan",
        [py, "-m", "pip", "install", "--pre", "pystan==3.14.0", str(wheel)],
        cwd=test_root,
        env=env,
    )
    client = test_root / "pystan_smoke.py"
    shutil.copy2(ROOT / "scripts/pystan_windows_smoke.py", client)
    stage("28-pystan", [py, str(client)], cwd=test_root, env=env)
    print("=== ALL REQUESTED STAGES PASSED ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        LOGS.mkdir(exist_ok=True)
        with (LOGS / "summary.txt").open("a", encoding="utf-8") as log:
            log.write(f"STOP: {type(exc).__name__}: {exc}\n")
        if not isinstance(exc, SystemExit):
            (LOGS / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
