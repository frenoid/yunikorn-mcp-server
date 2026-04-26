# YuniKorn MCP Server

A Model Context Protocol (MCP) server that interfaces with the Apache YuniKorn Scheduler, allowing AI agents to observe and reason about Kubernetes batch workload resource management, queue hierarchies, and application states.

## Features

- **7 MCP Tools**: Query partitions, queues, applications, nodes, user usage, and scheduler health
- **2 MCP Resources**: Static data access for partitions list and node utilization
- **Async HTTP**: Non-blocking API calls using `httpx`
- **Proper Error Mapping**: YuniKorn HTTP errors mapped to standard MCP error responses
- **Resource Awareness**: Handles YuniKorn's raw bytes and millicore values
- **CORS Enabled**: Allows connections from any origin for browser-based MCP Inspector
- **Streamable HTTP**: Default transport with stdio fallback for IDE integration

## Installation

```bash
uv pip install -r requirements.txt
```

If you are using a virtual environment, make sure it is activated first:

```bash
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Usage

### Running the Server

The default transport is **Streamable HTTP** on port 8000:

```bash
uv run python -m main
```

Command-line options:

| Option | Description | Default |
|--------|-------------|---------|
| `--transport` | Transport protocol (`stdio`, `streamable-http`) | `streamable-http` |
| `--host` | Host to bind (HTTP transport only) | `0.0.0.0` |
| `--port` | Port to listen on (HTTP transport only) | `8000` |
| `--log-level` | Logging level | `INFO` |

Examples:

```bash
# Streamable HTTP on custom port
uv run python -m main --transport streamable-http --host 127.0.0.1 --port 8080

# Stdio mode for Claude Code / IDE integration
uv run python -m main --transport stdio
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `YUNIKORN_BASE_URL` | Base URL of the YuniKorn REST API | `http://localhost:9089/ws/v1/` |
| `TLS_INSECURE` | Disable HTTPS certificate verification (`true`/`false`) | `false` |

```bash
# Connect to a remote YuniKorn instance
YUNIKORN_BASE_URL=http://yunikorn.example.com:9089/ws/v1/ uv run python -m main

# Connect to an HTTPS endpoint with a self-signed certificate
YUNIKORN_BASE_URL=https://yunikorn.example.com:9089/ws/v1/ TLS_INSECURE=true uv run python -m main
```

### Connecting with MCP Inspector

The Streamable HTTP endpoint is exposed at the `/mcp` path:

```
http://localhost:8000/mcp
```

## Testing

Run the test suite against a live YuniKorn instance:

```bash
YUNIKORN_BASE_URL=http://your-yunikorn-host:9089/ws/v1/ uv run python test_server.py
```

To run a quick compliance check:

```bash
YUNIKORN_BASE_URL=http://your-yunikorn-host:9089/ws/v1/ uv run python test_updated_server.py
```

### Data Format Notes

- **Memory**: Represented in raw bytes (64-bit signed integers).
- **CPU (vcore)**: Represented in millicores (thousands of a core).
- **Other resources**: No specific unit assigned.
- **Active applications**: The virtual "active" state represents New, Accepted, Running, Completing, and Failing statuses.
- **allocationID vs uuid**: `uuid` is deprecated. `allocationID` contains the same base value as `uuid` with a hyphen-counter suffix (e.g., `-0`, `-1`).
- **allocationDelay**: The difference between `allocationTime` and `requestTime` for an allocation.

## API Conformance

This MCP server conforms to the [Apache YuniKorn Scheduler REST API](https://yunikorn.apache.org/docs/api/scheduler/) (v1.8.0). Each tool maps directly to a documented endpoint.

| Tool | YuniKorn Endpoint |
|------|-------------------|
| `get_partitions` | `GET /ws/v1/partitions` |
| `get_partition_queues` | `GET /ws/v1/partition/{partitionName}/queues` |
| `get_applications_by_state` | `GET /ws/v1/partition/{partitionName}/applications/{state}?status={status}` |
| `inspect_application` | `GET /ws/v1/partition/{partitionName}/application/{appId}` |
| `get_node_details` | `GET /ws/v1/partition/{partitionName}/nodes` or `/node/{nodeId}` |
| `get_user_usage` | `GET /ws/v1/partition/{partitionName}/usage/users` or `/user/{userName}` |
| `check_scheduler_health` | `GET /ws/v1/scheduler/healthcheck` |

**Resources:**

| Resource | YuniKorn Endpoint |
|----------|-------------------|
| `yunikorn://partitions/list` | `GET /ws/v1/partitions` |
| `yunikorn://nodes/utilization` | `GET /ws/v1/scheduler/node-utilizations` |

## Error Mapping

| YuniKorn HTTP Code | MCP Error |
|--------------------|-----------|
| `400 Bad Request` | `INVALID_REQUEST` |
| `404 Not Found` | `INVALID_REQUEST` |
| `500 Internal Server Error` | `INTERNAL_ERROR` |
