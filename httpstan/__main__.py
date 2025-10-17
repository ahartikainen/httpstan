"""Top-level script environment for httpstan.

``python3 -m httpstan`` starts a server listening on ``127.0.0.1:8080``.

"""
import argparse
import logging

from aiohttp import web

import httpstan.app

def main() -> None:
    parser = argparse.ArgumentParser(description="Launch httpstan HTTP server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port number (default: 8080)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    
    app = httpstan.app.make_app()
    try:
        web.run_app(app, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")

if __name__ == "__main__":
    main()
