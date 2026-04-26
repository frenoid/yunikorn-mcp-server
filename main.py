#!/usr/bin/env python3
"""Entry point for the YuniKorn MCP server."""

import argparse
import logging
import sys
import os

from starlette.middleware.cors import CORSMiddleware

from yunikorn_mcp_server import app, client

def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apache YuniKorn MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="streamable-http",
        help="Transport protocol to use (default: streamable-http)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind when using HTTP transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on when using HTTP transport (default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("yunikorn-mcp")

    logger.info("Starting Apache YuniKorn MCP Server")
    logger.info("YuniKorn URL: %s", client.base_url)
    if not client.verify:
        logger.info("TLS certificate verification is DISABLED (TLS_INSECURE=true)")
    else:
        logger.info("TLS certificate verification is ENABLED")

    if args.transport == "streamable-http":
        app.settings.host = args.host
        app.settings.port = args.port
        logger.info(
            "Transport: Streamable HTTP (http://%s:%d%s)",
            args.host,
            args.port,
            app.settings.streamable_http_path,
        )
        _run_streamable_http_with_cors()
    else:
        logger.info("Transport: stdio")
        app.run(transport=args.transport)


def _run_streamable_http_with_cors() -> None:
    import anyio
    import uvicorn

    app.settings.transport_security.enable_dns_rebinding_protection = False
    starlette_app = app.streamable_http_app()
    starlette_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
        allow_credentials=True,
    )

    config = uvicorn.Config(
        starlette_app,
        host=app.settings.host,
        port=app.settings.port,
        log_level=app.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    anyio.run(server.serve)


if __name__ == "__main__":
    main()
