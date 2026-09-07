"""Managed Uvicorn runner: drain API requests, then close its owned UI tree."""
from __future__ import annotations

import argparse
import logging

import uvicorn

from utils.stack_control import finish_shutdown, mark_shutdown_requested
from web_api.app import app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, timeout_graceful_shutdown=10))
    def request_shutdown():
        mark_shutdown_requested()
        server.should_exit = True
    app.state.request_shutdown = request_shutdown
    server.run()
    if not finish_shutdown():
        logging.getLogger(__name__).error("Clear API stopped, but an owned UI process could not be closed. See the stack control record.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
