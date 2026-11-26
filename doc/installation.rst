============
Installation
============

.. These instructions appear in both README.rst and installation.rst

**httpstan** runs on Linux and macOS (gcc ≥9.0 or clang ≥10.0).
Windows x64 source builds are supported with CPython 3.12 and MSVC or clang-cl.

::

    $ python3 -m pip install httpstan

In order to install httpstan from PyPI make sure your system satisfies the requirements:

- Linux or macOS
- x86-64 CPU
- C++ compiler: gcc ≥9.0 or clang ≥10.0.

If your system uses a different kind of CPU, you should be able to install from source.

Installation from source
========================

Download the source code associated with a release from `https://github.com/stan-dev/httpstan/tags <https://github.com/stan-dev/httpstan/tags>`_.
Extract the contents of the ``zip`` or ``tar.gz`` release bundle. Alternatively, clone the git repository and checkout the commit associated with the version of httpstan you want.

Executing the following commands will build and install httpstan from source:

::

    # Build shared libraries
    make

    # Build the httpstan wheel on your system
    python3 -m pip install poetry
    python3 -m poetry build

    # Install the wheel
    python3 -m pip install dist/*.whl

Windows (from source)
---------------------

On Windows x64, use CPython 3.12 and an activated MSVC-compatible x64
compiler environment (Visual Studio 2022 Build Tools or a standalone MSVC
and Windows SDK installation). Install LLVM as well if using clang-cl.
Build the wheel in a clean checkout::

    set DISTUTILS_USE_SDK=1
    set MSSDK=1
    python -m pip install "poetry~=1.8.0" "setuptools<81"
    python scripts\build_windows.py all --compiler clang-cl
    python -m poetry build -f wheel
    python -m pip install dist\httpstan-4.17.0-cp312-cp312-win_amd64.whl

Use ``--compiler cl`` for MSVC instead. Keep the same toolchain activated when
compiling Stan models at runtime. The Windows build does not bundle the
compiler or Windows SDK. Windows wheels on PyPI are not assumed to be available.
