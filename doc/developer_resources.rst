===================
Developer Resources
===================

Notes for httpstan developers are collected here.

Updating CmdStan Sampler Parameter Defaults
===========================================

If CmdStan changes default values for arguments, pipe the output of ``modelbinary --help-all`` to a
file and then point ``scripts/parse_cmdstan_help.py`` at that file. The output
should replace the file ``httpstan/services/cmdstan-help-all.json``.

DEBUG mode
==========

If the environment variable ``HTTPSTAN_DEBUG`` is set to ``1`` or ``true``, the
call to the stan::services sampling function will block until finished instead
of being run in the background. This should make debugging crashes with ``gdb``
much easier.  There is, however, one complication. The number of samples drawn
must be set to be a very low number (e.g., ``10``) otherwise the call to the
sampling function will freeze up. The call will freeze up because the socket
used to communicate from C++ to Python will fill up. If the socket runs out of
buffer space the stan::services call will never return.

On Windows debug mode runs the sampling function in a server thread so that
callback sockets can be read concurrently.

Windows builds and tests
========================

The separate ``.github/workflows/windows.yml`` builds Windows x64 wheels with
CPython 3.12. A push to ``support/windows`` runs all four toolchain profiles
with the full suite. Individual ``windows-test/<profile>`` branches run smoke
tests. The profiles are ``official-clang``, ``official-msvc``, ``portable-clang``
and ``portable-msvc``. Append ``-full``, ``-headers`` or ``-services`` to select
a test stage. The two official ``-od`` profiles disable C++ optimization.

The portable profiles require reviewing the Microsoft license and setting the
repository variable ``HTTPSTAN_ACCEPT_MSVC_LICENSE=yes``. Optional variables
``HTTPSTAN_PORTABLE_MSVC_VERSION`` and ``HTTPSTAN_PORTABLE_SDK_VERSION`` select
versions. Portable Clang requires LLVM separately. The same CI driver can be
run locally::

    python scripts\windows_ci.py --profile official-clang --through full

Use a clean checkout when changing the compiler profile. Model compilation
requires the same compiler family as the wheel. The compiler and SDK are not
bundled. Actions publishes logs and wheels as artifacts. For failures, inspect
``summary.txt``, ``toolchain.json`` and the first failed stage log.

On Windows, callbacks use authenticated TCP loopback and workers use spawn.
Native extensions load from process-local copies under the cache's ``loaded``
directory; stale copies can be removed when httpstan processes have exited.

Signing key
===========
The signing key for httpstan is the same as for pystan.
The key has id ``85107A96512971B8C55932085D5D0CFF0A51A83D``.
Git tags are signed with this key.

Accounts with Continuous Integration, PyPI, and Readthedocs
===========================================================

- readthedocs: riddell-stan

Making a release of `httpstan`
==============================

The following assumes you are releasing httpstan version 4.8.0. Adjust as needed.

- Update `version` in `pyproject.toml`.
- Tag a release: `git tag -u 85107A96512971B8C55932085D5D0CFF0A51A83D -m "httpstan 4.8.0" 4.8.0`
- Push the tag to upstream: `git push upstream 4.8.0`
- Wait a few days, the stan-dev/httpstan-wheels repository tries to build (and publish) new wheels every two days.

If no wheels appear, check <https://github.com/stan-dev/httpstan-wheels/actions>.
