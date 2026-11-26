"""Top-level script environment for httpstan.

``python3 -m httpstan`` starts a server listening on ``127.0.0.1``.
``python -m httpstan install portable`` installs the Windows compiler tools.
"""

import argparse
import os
import subprocess
import sys


def main() -> None:
    """Start the server or install its portable Windows toolchain."""
    parser = argparse.ArgumentParser(description="Launch httpstan HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8080")
    commands = parser.add_subparsers(dest="command")
    install = commands.add_parser("install", help="Install a Windows toolchain.")
    install.add_argument("toolchain", choices=["portable"])
    install.add_argument("--accept-license", action="store_true", help="Accept Microsoft Build Tools and SDK terms.")
    args = parser.parse_args()
    if args.command == "install":
        if sys.platform != "win32":
            parser.error("Portable MSVC installation is supported on Windows only")
        from httpstan._toolchain import (
            LICENSE_URL,
            install_portable,
            portable_environment,
            toolchain_directory,
        )
        from httpstan._windows import read_manifest

        root = toolchain_directory()
        family = read_manifest()["compiler"]
        accepted = args.accept_license or os.environ.get("HTTPSTAN_ACCEPT_MSVC_LICENSE", "").lower() == "yes"
        if not accepted and not (root / "msvc" / "setup_x64.bat").is_file():
            print(f"Review the Microsoft Build Tools and Windows SDK terms: {LICENSE_URL}")
            reply = input("Accept the licence terms? [y/N] ") if sys.stdin.isatty() else ""
            if reply.strip().lower() not in {"y", "yes"}:
                parser.error("License acceptance is required; use --accept-license after reviewing the terms.")
            accepted = True
        try:
            install_portable(root, family, accepted)
            portable_environment(root, family, os.environ.copy())
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
        return

    import aiohttp.web

    import httpstan.app

    app = httpstan.app.make_app()
    aiohttp.web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
