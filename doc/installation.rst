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

Use ``--compiler cl`` for MSVC instead. The compiler and Windows SDK are not
bundled. Windows wheels on PyPI are not assumed to be available.

Windows (portable compiler)
---------------------------

After installing a Windows wheel, install the matching portable compiler and
Windows SDK from an ordinary Command Prompt::

    python -m httpstan install portable

The installer asks you to accept the applicable Microsoft Build Tools and SDK
license terms before downloading Microsoft components. After reviewing those
terms, pass ``--accept-license`` for non-interactive installation. The compiler
family is determined by the wheel: MSVC wheels install MSVC and the Windows
SDK, and clang-cl wheels additionally install LLVM 20.1.8. The LLVM download is
approximately 896 MiB. Several gigabytes of free space may be needed.

The default installation directory is ``%LOCALAPPDATA%\httpstan\toolchain``.
It is independent of the versioned model cache and is shared by Python
environments. To install and use a different directory::

    set "HTTPSTAN_TOOLCHAIN_DIR=D:\httpstan-tools"
    python -m httpstan install portable

The directory contains ``msvc`` and, when needed, ``llvm``. Set the same
variable when using PyStan or launching the server. Without an override,
httpstan first checks an activated compiler environment, then its default
portable installation, then Visual Studio 2022 Build Tools. No developer
command prompt is required for the latter two. Compiler activation affects
only compilation subprocesses. Existing installations are reused; a failed or
incomplete installation is not automatically overwritten.

The portable installation does not normally require administrator privileges,
but Windows Installer (used by the upstream MSVC extraction script) must be
permitted on the machine. The toolchain is downloaded separately from the
wheel and is subject to its own license terms. No Microsoft compiler or SDK
is redistributed by httpstan.
