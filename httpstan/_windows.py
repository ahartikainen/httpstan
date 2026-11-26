"""Native Windows builds using an activated x64 MSVC-compatible toolchain."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

PACKAGE_DIR = Path(__file__).resolve().parent
MANIFEST = PACKAGE_DIR / "windows-build.json"
MACROS = (
    "BOOST_DISABLE_ASSERTS",
    "BOOST_PHOENIX_NO_VARIADIC_EXPRESSION",
    "BOOST_ALL_NO_LIB",
    "__TBB_NO_IMPLICIT_LINKAGE=1",
    "STAN_THREADS",
    "NOMINMAX",
    "WIN32_LEAN_AND_MEAN",
    "_USE_MATH_DEFINES",
    "_BOOST_LGAMMA=1",
    "SUNDIALS_STATIC_DEFINE",
    "_ITERATOR_DEBUG_LEVEL=0",
)
LIBRARIES = ("sundials_cvodes", "sundials_idas", "sundials_nvecserial", "sundials_kinsol", "tbb")


def compiler(family: str, env: Optional[Dict[str, str]] = None) -> str:
    """Locate cl.exe or clang-cl.exe in the supplied or active environment."""
    if family not in {"cl", "clang-cl"}:
        raise ValueError(f"Unsupported Windows compiler: {family}")
    return tool(family, env)


def tool(name: str, env: Optional[Dict[str, str]] = None) -> str:
    """Return the path to a Windows toolchain executable in the given environment."""
    path = shutil.which(name + ".exe", path=env.get("PATH", "") if env is not None else None)
    if path is None:
        raise RuntimeError(f"{name}.exe not found; activate the toolchain first")
    return path


def flags(family: str, optimization: str = "/O2") -> List[str]:
    """Return the shared MSVC-ABI C++ compiler flags and Stan macros."""
    args = [
        "/nologo",
        "/std:c++17",
        "/EHsc",
        "/MD",
        "/bigobj",
        "/Zc:__cplusplus",
        optimization,
        "/fp:precise",
        "/DNDEBUG",
    ]
    if family == "cl":
        args += ["/permissive-", "/utf-8"]
    return args + ["/D" + macro for macro in MACROS]


def run(command: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> str:
    """Run a native command in the given environment and return its merged diagnostics."""
    invocation = subprocess.list2cmdline([str(arg) for arg in command])
    print(f"[native] cwd={cwd}\n[native] {invocation}", flush=True)
    start = time.monotonic()
    lines = []
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
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            lines.append(line)
        status = process.wait()
    elapsed = time.monotonic() - start
    print(f"[native] exit={status} elapsed={elapsed:.2f}s", flush=True)
    output = invocation + "\n" + "".join(lines)
    if status:
        raise RuntimeError(f"Native command failed ({status}):\n{output[-30000:]}")
    return output


def clang_link_args(family: str, env: Optional[Dict[str, str]] = None) -> List[str]:
    """Locate Clang runtime libraries using the given compiler environment."""
    if family != "clang-cl":
        return []
    resource = Path(
        subprocess.check_output([compiler(family, env), "--print-resource-dir"], env=env, text=True).strip()
    )
    directory = resource / "lib" / "windows"
    if not directory.is_dir():
        return []
    args = ["/LIBPATH:" + str(directory)]
    builtins = directory / "clang_rt.builtins-x86_64.lib"
    if builtins.is_file():
        args.append(str(builtins))
    return args


def python_import_lib() -> Path:
    """Locate the import library for the running CPython version."""
    name = f"python{sys.version_info.major}{sys.version_info.minor}.lib"
    candidates = [Path(sys.base_prefix) / "libs" / name, Path(sys.prefix) / "libs" / name]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(f"Cannot find CPython import library {name}: {candidates}")


def compile_cpp(
    family: str,
    source: Path,
    target: Path,
    optimization: str = "/O2",
    extra_compile_args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Compile a C++ source into an object file and return compiler output.

    Additional compiler arguments follow the shared flags. If env is
    supplied, use it for compiler discovery and execution.
    """
    return run(
        [
            compiler(family, env),
            *flags(family, optimization),
            *(extra_compile_args or []),
            "/I" + str(PACKAGE_DIR / "include"),
            "/I" + sysconfig.get_path("include"),
            "/c",
            str(source),
            "/Fo" + str(target),
        ],
        target.parent,
        env,
    )


def read_manifest() -> dict:
    """Read the compiler configuration used to build the services object."""
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def cache_identity() -> bytes:
    """Return a digest of the native build configuration for the model cache."""
    return hashlib.sha256(MANIFEST.read_bytes()).digest()


def build_model(source: Path, directory: Path, extra_compile_args: List[str]) -> str:
    """Compile and link a model extension in its cache directory.

    Return combined compiler and linker output. The extension uses the same
    compiler family as the precompiled services object.
    """
    from httpstan._toolchain import toolchain_environment

    config = read_manifest()
    family = config["compiler"]
    optimization = config["optimization"]
    override = os.environ.get("HTTPSTAN_WINDOWS_CXX")
    if override and override != family:
        raise RuntimeError(f"Wheel uses {family}, not {override}; rebuild the service object to change compiler")
    env = toolchain_environment(family)
    # A unique filename makes deletion/recompilation independent of loaded DLLs.
    obj = directory / (source.stem + ".obj")
    target = directory / ("stan_services_" + source.stem + "_" + uuid.uuid4().hex[:12] + ".pyd")
    output = compile_cpp(family, source, obj, optimization, extra_compile_args, env)
    # Publish only after a successful link to avoid caching incomplete modules.
    with tempfile.TemporaryDirectory(prefix="link-", dir=directory) as tmp:
        staged = Path(tmp) / target.name
        output += run(
            [
                tool("link", env),
                "/NOLOGO",
                "/DLL",
                "/MACHINE:X64",
                "/INCREMENTAL:NO",
                "/OUT:" + str(staged),
                str(obj),
                str(PACKAGE_DIR / "stan_services.obj"),
                str(python_import_lib()),
                *[str(PACKAGE_DIR / "lib" / (name + ".lib")) for name in LIBRARIES],
                "Ws2_32.lib",
                *clang_link_args(family, env),
            ],
            directory,
            env,
        )
        staged.replace(target)
    return output
