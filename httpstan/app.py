"""Helper function to launch httpstan server.

Configure the server and schedule startup and shutdown tasks.
"""

import asyncio
import logging
from typing import Any

from aiohttp import web

import httpstan.routes

try:
    import uvloop
except ModuleNotFoundError:
    uvloop = None


logger = logging.getLogger("httpstan")


async def _warn_unfinished_operations(app: web.Application) -> None:
    """Warn if tasks (e.g., operations) are unfinished.

    Called immediately before tasks are cancelled.

    """
    operations: dict[str, dict[str, Any]] = app.get("operations", {})
    for name, operation in operations.items():
        if not operation["done"]:
            logger.critical("Operation `%s` cancelled before finishing.", name)


def make_app() -> web.Application:
    """Assemble aiohttp Application.

    Returns:
        aiohttp.web.Application: assembled aiohttp application.

    """
    # default `client_max_size` is 1 MiB. Model `data` is often greater. Set to generous 512 GiB.
    app = web.Application(client_max_size=512 * 1024**3)
    httpstan.routes.setup_routes(app)
    # startup and shutdown tasks
    app["operations"] = {}
    app.on_cleanup.append(_warn_unfinished_operations)

    # Enable uvloop globally if it’s installed
    if uvloop is not None:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    return app
