#!/usr/bin/env python3
"""
Apache YuniKorn Model Context Protocol (MCP) Server.

Interfaces with the YuniKorn Scheduler REST API to provide AI agents with
observability into Kubernetes batch workload resource management, queue
hierarchies, and application states.
"""

import os
import json
import ssl
from urllib.parse import quote
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ErrorData, INTERNAL_ERROR, INVALID_REQUEST
from mcp.server.lowlevel.server import McpError


DEFAULT_BASE_URL = "http://localhost:9089/ws/v1/"
YUNIKORN_BASE_URL = os.environ.get("YUNIKORN_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/"
TLS_INSECURE = os.environ.get("TLS_INSECURE", "false").lower() in ("true", "1", "yes", "on")

# Authentication — read at import time; override via YunikornClient constructor in tests.
# Priority: bearer token > basic auth > none. mTLS is orthogonal and can combine with either.
YUNIKORN_TOKEN = os.environ.get("YUNIKORN_TOKEN")
YUNIKORN_USERNAME = os.environ.get("YUNIKORN_USERNAME")
YUNIKORN_PASSWORD = os.environ.get("YUNIKORN_PASSWORD")
YUNIKORN_CERT_PATH = os.environ.get("YUNIKORN_CERT_PATH")
YUNIKORN_KEY_PATH = os.environ.get("YUNIKORN_KEY_PATH")

# Allowed values for the get_applications_by_state tool. Validating these
# up-front gives a clear MCP INVALID_REQUEST instead of an opaque 404 from
# YuniKorn when a caller passes a typo or wrong casing.
VALID_APPLICATION_STATES = {"active", "rejected", "completed"}
VALID_APPLICATION_STATUSES = {
    "new", "accepted", "running", "completing", "failing",
}


class YunikornClient:
    """Async HTTP client for the YuniKorn REST API."""

    def __init__(
        self,
        base_url: str = YUNIKORN_BASE_URL,
        verify: bool = not TLS_INSECURE,
        token: str | None = YUNIKORN_TOKEN,
        username: str | None = YUNIKORN_USERNAME,
        password: str | None = YUNIKORN_PASSWORD,
        cert_path: str | None = YUNIKORN_CERT_PATH,
        key_path: str | None = YUNIKORN_KEY_PATH,
    ):
        self.base_url = base_url
        self.verify = verify

        headers: dict[str, str] = {}
        auth: tuple[str, str] | None = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
            self.auth_method = "bearer_token"
        elif username and password:
            auth = (username, password)
            self.auth_method = "basic_auth"
        else:
            self.auth_method = "none"

        self.mtls_enabled = bool(cert_path and key_path)

        # Build the SSL context so we can optionally load a client certificate.
        # Using an explicit ssl.SSLContext avoids the deprecated cert= kwarg in httpx.
        ssl_context: ssl.SSLContext | bool
        if self.mtls_enabled:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if not verify:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            assert cert_path and key_path  # already checked above
            ssl_context.load_cert_chain(cert_path, key_path)
        else:
            ssl_context = verify  # True / False / existing SSLContext

        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30.0,
            verify=ssl_context,
            headers=headers,
            auth=auth,
        )

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request and return parsed JSON."""
        response = await self.client.get(path, params=params)
        content = response.text

        if response.status_code == 400:
            raise McpError(
                ErrorData(
                    code=INVALID_REQUEST,
                    message=f"Bad request: invalid parameter or malformed query for {path}",
                    data=content,
                )
            )
        elif response.status_code == 404:
            raise McpError(
                ErrorData(
                    code=INVALID_REQUEST,
                    message=f"Not found: requested resource does not exist at {path}",
                    data=content,
                )
            )
        elif response.status_code >= 500:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"YuniKorn scheduler internal error ({response.status_code}) for {path}",
                    data=content,
                )
            )

        elif response.is_error:
            # Catches 401, 403, 405, 408, 429, etc. that the explicit branches
            # above do not handle. Without this, httpx raises HTTPStatusError
            # which surfaces to the MCP client as an unwrapped exception.
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"YuniKorn returned HTTP {response.status_code} for {path}",
                    data=content,
                )
            )
        return response.json()

    async def close(self):
        await self.client.aclose()


app = FastMCP("yunikorn-mcp-server")
client = YunikornClient()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.tool(
    description=(
        "Retrieves general information and statistics for all partitions in the cluster. "
        "Useful for seeing total cluster capacity, used capacity, and node counts. "
        "IMPORTANT: resource values (memory, cpu) are returned as raw integers "
        "(bytes for memory, millicores for CPU). Convert these to human-readable "
        "formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def get_partitions() -> str:
    """Get all cluster partitions."""
    data = await client.get("partitions")
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Fetches the full queue hierarchy for a specific partition. "
        "Includes maxResource, guaranteedResource, and pendingResource for each queue. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def get_partition_queues(partitionName: str) -> str:
    """Get queue hierarchy for a partition."""
    partition = quote(partitionName, safe="")
    data = await client.get(f"partition/{partition}/queues")
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Retrieves applications filtered by their current lifecycle state (active, rejected, or completed). "
        "Active is a virtual state representing New, Accepted, Running, Completing, or Failing apps. "
        "When state is 'active', you can optionally set status to new, accepted, running, completing, "
        "or failing (case-insensitive) to narrow results. Defaults to running if not specified. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def get_applications_by_state(
    partitionName: str, state: str, status: str | None = None
) -> str:
    """Get applications filtered by state."""
    state_normalized = state.lower()
    if state_normalized not in VALID_APPLICATION_STATES:
        raise McpError(
            ErrorData(
                code=INVALID_REQUEST,
                message=f"Invalid state '{state}'. Must be one of: {sorted(VALID_APPLICATION_STATES)}",
            )
        )
    partition = quote(partitionName, safe="")
    params = {}
    if state_normalized == "active":
        status_normalized = status.lower() if status else "running"
        if status_normalized not in VALID_APPLICATION_STATUSES:
            raise McpError(
                ErrorData(
                    code=INVALID_REQUEST,
                    message=f"Invalid status '{status}'. Must be one of: {sorted(VALID_APPLICATION_STATUSES)}",
                )
            )
        params["status"] = status_normalized
    data = await client.get(
        f"partition/{partition}/applications/{quote(state_normalized, safe='')}",
        params=params,
    )
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Provides detailed metadata for a single application, including its allocation log "
        "and resource requests. Both uuid (deprecated) and allocationID fields may appear in "
        "allocations; allocationID contains the same base value as uuid plus a hyphen-counter suffix "
        "(e.g., -0, -1). Use allocationID to identify specific task allocations. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def inspect_application(partitionName: str, appId: str) -> str:
    """Inspect a single application."""
    partition = quote(partitionName, safe="")
    app_id = quote(appId, safe="")
    data = await client.get(f"partition/{partition}/application/{app_id}")
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Fetches all nodes or a specific node managed by YuniKorn, including capacity and utilization percentages. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def get_node_details(partitionName: str, nodeId: str | None = None) -> str:
    """Get node details for a partition."""
    partition = quote(partitionName, safe="")
    if nodeId:
        nid = quote(nodeId, safe="")
        data = await client.get(f"partition/{partition}/node/{nid}")
    else:
        data = await client.get(f"partition/{partition}/nodes")
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Retrieves resource usage and quota information for all users or a specific user. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def get_user_usage(partitionName: str, userName: str | None = None) -> str:
    """Get user resource usage."""
    partition = quote(partitionName, safe="")
    if userName:
        uname = quote(userName, safe="")
        data = await client.get(f"partition/{partition}/usage/user/{uname}")
    else:
        data = await client.get(f"partition/{partition}/usage/users")
    return json.dumps(data, indent=2)


@app.tool(
    description=(
        "Returns the health status of the scheduler, checking for critical logs and negative resource values. "
        "IMPORTANT: resource values are raw integers (bytes for memory, millicores for CPU). "
        "Convert these to human-readable formats (e.g., GiB or Cores) before presenting to the user."
    )
)
async def check_scheduler_health() -> str:
    """Check scheduler health."""
    data = await client.get("scheduler/healthcheck")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@app.resource("yunikorn://partitions/list")
async def partitions_list() -> str:
    """Current cluster partitions and their status."""
    data = await client.get("partitions")
    return json.dumps(data, indent=2)


@app.resource("yunikorn://nodes/utilization")
async def nodes_utilization() -> str:
    """Cluster-wide node utilization distribution across buckets."""
    data = await client.get("scheduler/node-utilizations")
    return json.dumps(data, indent=2)
