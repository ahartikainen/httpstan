"""Compile a Stan model extension module given code written in Stan.

These functions manage the process of compiling a Python extension module
from C++ code generated and loading the resulting module.

"""
import asyncio
import base64
import hashlib
import importlib
import importlib.resources
import logging
import os
import pathlib
import platform
import sys
from importlib.machinery import EXTENSION_SUFFIXES
from types import ModuleType
from typing import List, Optional, Tuple

import setuptools

import httpstan.build_ext
import httpstan.cache
import httpstan.compile

PACKAGE_DIR = pathlib.Path(__file__).resolve(strict=True).parents[0]
logger = logging.getLogger("httpstan")


def calculate_model_name(program_code: str) -> str:
    """Calculate model name from Stan program code.

    Names look like this: ``models/2uxewutp``. Name uses a hash of the
    concatenation of the following:

    - UTF-8 encoded Stan program code
    - UTF-8 encoded string recording the httpstan version
    - UTF-8 encoded string identifying the system platform
    - UTF-8 encoded string identifying the system bit architecture
    - UTF-8 encoded string identifying the Python version
    - UTF-8 encoded string identifying the Python executable

    Arguments:
        program_code: Stan program code.

    Returns:
        str: model name

    """
    # digest_size of 5 means we expect a collision after a million models
    digest_size = 5
    hash = hashlib.blake2b(digest_size=digest_size)
    hash.update(program_code.encode())

    # system identifiers
    hash.update(httpstan.__version__.encode())
    hash.update(sys.platform.encode())
    hash.update(str(sys.maxsize).encode())
    hash.update(sys.version.encode())
    # include sys.executable in hash to account for different `venv`s
    hash.update(sys.executable.encode())

    id = base64.b32encode(hash.digest()).decode().lower()
    return f"models/{id}"


def import_services_extension_module(model_name: str) -> ModuleType:
    """Load an existing model-specific stan::services extension module.

    Arguments:
        model_name

    Returns:
        module: loaded module handle.

    Raises:
        KeyError: Model not found.

    """
    model_directory = pathlib.Path(httpstan.cache.model_directory(model_name))
    try:
        module_path = next(filter(lambda p: p.suffix in EXTENSION_SUFFIXES, model_directory.iterdir()))
    except (FileNotFoundError, StopIteration):
        raise KeyError(f"No module for `{model_name}` found in `{model_directory}`")
    # The module name, which is independent of the filename, is always "stan_services". The module
    # name must be defined in stan_services.cpp, which is compiled before we know with which
    # specific stan model it will be linked with. Since we want to compile stan_services.cpp in
    # advance, we are stuck with a fixed module name.
    spec = importlib.util.spec_from_file_location("stan_services", module_path)  # type: ignore
    module: ModuleType = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(module)

    return module


async def build_services_extension_module(program_code: str, extra_compile_args: Optional[List[str]] = None) -> str:
    """Compile a model-specific stan::services extension module.

    Since compiling an extension module takes a long time, compilation takes
    place in a different thread.

    Messages generated by the compiler—normally sent to stderr—are collected
    and saved. These messages are returned by the function.

    Returns compiler messages.

    This is a coroutine function.

    IMPORTANT NOTE: This function builds the extension module in the cache
    directory, making it available for later `import`ing. This "side-effect" is
    why there are no functions called `load_services_extension_module` and
    `dump_services_extension_module`.

    """
    model_name = calculate_model_name(program_code)
    model_directory_path = pathlib.Path(httpstan.cache.model_directory(model_name))

    os.makedirs(model_directory_path, exist_ok=True)

    stan_model_name = f"model_{model_name.split('/')[1]}"
    cpp_code, _ = httpstan.compile.compile(program_code, stan_model_name)
    cpp_code_path = model_directory_path / f"{stan_model_name}.cpp"
    with open(cpp_code_path, "w") as fh:
        fh.write(cpp_code)

    httpstan_dir = os.path.dirname(__file__)
    include_dirs = [
        httpstan_dir,  # for socket_writer.hpp and socket_logger.hpp
        model_directory_path.as_posix(),
        os.path.join(httpstan_dir, "include"),
        os.path.join(httpstan_dir, "include", "lib", "eigen_3.3.7"),
        os.path.join(httpstan_dir, "include", "lib", "boost_1.72.0"),
        os.path.join(httpstan_dir, "include", "lib", "sundials_5.2.0", "include"),
        os.path.join(httpstan_dir, "include", "lib", "tbb_2019_U8", "include"),
    ]

    stan_macros: List[Tuple[str, Optional[str]]] = [
        ("BOOST_DISABLE_ASSERTS", None),
        ("BOOST_PHOENIX_NO_VARIADIC_EXPRESSION", None),
        ("STAN_THREADS", None),
        ("_REENTRANT", None),  # required by stan math / std:lgamma
        # the following is needed on linux for compatibility with libraries built with the manylinux2014 image
        ("_GLIBCXX_USE_CXX11_ABI", "0"),
    ]

    if extra_compile_args is None:
        extra_compile_args = ["-O3", "-std=c++14"]

    # Note: `library_dirs` is only relevant for linking. It does not tell an extension
    # where to find shared libraries during execution. There are two ways for an
    # extension module to find shared libraries: LD_LIBRARY_PATH and rpath.
    libraries = ["sundials_cvodes", "sundials_idas", "sundials_nvecserial", "tbb"]
    if platform.system() == "Darwin":  # pragma: no cover
        libraries.extend(["tbbmalloc", "tbbmalloc_proxy"])
    extension = setuptools.Extension(
        f"stan_services_{stan_model_name}",  # filename only. Module name is "stan_services"
        language="c++",
        sources=[cpp_code_path.as_posix()],
        define_macros=stan_macros,
        include_dirs=include_dirs,
        library_dirs=[f"{PACKAGE_DIR / 'lib'}"],
        libraries=libraries,
        extra_compile_args=extra_compile_args,
        extra_link_args=[f"-Wl,-rpath,{PACKAGE_DIR / 'lib'}"],
        extra_objects=[
            (PACKAGE_DIR / "stan_services.cpp").with_suffix(".o").as_posix(),
        ],
    )

    extensions = [extension]
    build_lib = model_directory_path.as_posix()

    # Building the model takes a long time. Run in a different thread.
    compiler_output = await asyncio.get_event_loop().run_in_executor(
        None, httpstan.build_ext.run_build_ext, extensions, build_lib
    )
    return compiler_output
