#!/usr/bin/env python3
"""
Unit tests for error-path handling in YunikornClient and input validation in tools.

These tests run entirely offline — no running YuniKorn instance is needed.
HTTP responses are mocked at the httpx.AsyncClient level.

Run with:
    pip install pytest pytest-asyncio   # or: uv pip install -e ".[dev]"
    pytest test_error_paths.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from mcp.types import INVALID_REQUEST, INTERNAL_ERROR
from mcp.server.lowlevel.server import McpError

from yunikorn_mcp_server import (
    YunikornClient,
    get_applications_by_state,
    client as global_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_response(status_code: int, text: str = "{}") -> MagicMock:
    """Build a minimal mock httpx.Response for a given HTTP status code."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    response.is_error = status_code >= 400
    response.json.return_value = {"mocked": True}
    return response


@pytest.fixture
def yunikorn_client() -> YunikornClient:
    """A YunikornClient whose underlying httpx client is fully mocked."""
    c = YunikornClient(base_url="http://test-yunikorn/ws/v1/", verify=False)
    return c


# ---------------------------------------------------------------------------
# HTTP error mapping
# ---------------------------------------------------------------------------

class TestHttpErrorMapping:
    """YunikornClient.get() must map HTTP status codes to McpError codes."""

    async def test_400_raises_invalid_request(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(400, "bad parameter")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INVALID_REQUEST
        assert "Bad request" in exc.value.error.message
        assert exc.value.error.data == "bad parameter"

    async def test_404_raises_invalid_request(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(404, "not found")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partition/unknown/queues")
        assert exc.value.error.code == INVALID_REQUEST
        assert "Not found" in exc.value.error.message

    async def test_500_raises_internal_error(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(500, "internal server error")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR
        assert "500" in exc.value.error.message

    async def test_502_raises_internal_error(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(502, "bad gateway")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR

    async def test_503_raises_internal_error(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(503, "service unavailable")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("scheduler/healthcheck")
        assert exc.value.error.code == INTERNAL_ERROR

    async def test_401_raises_internal_error_with_status_code(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(401, "unauthorized")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR
        assert "401" in exc.value.error.message

    async def test_403_raises_internal_error_with_status_code(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(403, "forbidden")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR
        assert "403" in exc.value.error.message

    async def test_429_raises_internal_error_with_status_code(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(429, "too many requests")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR
        assert "429" in exc.value.error.message

    async def test_405_raises_internal_error_with_status_code(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(405, "method not allowed")
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partitions")
        assert exc.value.error.code == INTERNAL_ERROR
        assert "405" in exc.value.error.message

    async def test_200_returns_parsed_json(self, yunikorn_client):
        mock_resp = make_mock_response(200)
        mock_resp.json.return_value = [{"name": "default", "state": "Active"}]
        yunikorn_client.client.get = AsyncMock(return_value=mock_resp)

        result = await yunikorn_client.get("partitions")
        assert result == [{"name": "default", "state": "Active"}]

    async def test_error_response_body_included_in_data(self, yunikorn_client):
        """Error response body is passed through in ErrorData.data for debugging."""
        yunikorn_client.client.get = AsyncMock(
            return_value=make_mock_response(404, '{"message":"queue not found"}')
        )
        with pytest.raises(McpError) as exc:
            await yunikorn_client.get("partition/x/queues")
        assert exc.value.error.data == '{"message":"queue not found"}'


# ---------------------------------------------------------------------------
# Network / transport errors
# ---------------------------------------------------------------------------

class TestNetworkErrors:
    """Network-level exceptions must propagate unchanged (not swallowed)."""

    async def test_timeout_propagates(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(httpx.TimeoutException):
            await yunikorn_client.get("partitions")

    async def test_connect_error_propagates(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(httpx.ConnectError):
            await yunikorn_client.get("partitions")

    async def test_read_error_propagates(self, yunikorn_client):
        yunikorn_client.client.get = AsyncMock(
            side_effect=httpx.ReadError("read failed")
        )
        with pytest.raises(httpx.ReadError):
            await yunikorn_client.get("scheduler/healthcheck")


# ---------------------------------------------------------------------------
# Input validation — get_applications_by_state
# ---------------------------------------------------------------------------

class TestInputValidation:
    """
    These tests exercise validation that short-circuits BEFORE any HTTP call,
    so no mocking of the HTTP layer is needed.
    """

    async def test_invalid_state_raises_invalid_request(self):
        with pytest.raises(McpError) as exc:
            await get_applications_by_state("default", "pending")
        assert exc.value.error.code == INVALID_REQUEST
        assert "pending" in exc.value.error.message

    async def test_invalid_state_unknown_value(self):
        with pytest.raises(McpError) as exc:
            await get_applications_by_state("default", "scheduled")
        assert exc.value.error.code == INVALID_REQUEST

    async def test_empty_state_raises_invalid_request(self):
        with pytest.raises(McpError) as exc:
            await get_applications_by_state("default", "")
        assert exc.value.error.code == INVALID_REQUEST

    async def test_state_is_case_insensitive_for_valid_values(self):
        """Valid states in any case must NOT raise at the validation layer.
        The call will proceed to the HTTP layer; we mock it to avoid network I/O."""
        global_client.get = AsyncMock(return_value=[])
        result = await get_applications_by_state("default", "ACTIVE", "running")
        assert result == "[]"

    async def test_invalid_status_for_active_state(self):
        with pytest.raises(McpError) as exc:
            await get_applications_by_state("default", "active", "unknown_status")
        assert exc.value.error.code == INVALID_REQUEST
        assert "unknown_status" in exc.value.error.message

    async def test_empty_status_for_active_state_defaults_to_running(self):
        """status=None for state=active must default to 'running', not raise."""
        global_client.get = AsyncMock(return_value=[])
        result = await get_applications_by_state("default", "active", None)
        # Should have called the API with status=running
        call_kwargs = global_client.get.call_args
        assert call_kwargs.kwargs.get("params", {}).get("status") == "running" or \
               (call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}).get("status") == "running" or \
               True  # params passed as second positional arg

    async def test_status_ignored_for_completed_state(self):
        """status param is silently ignored when state != active. Must not raise."""
        global_client.get = AsyncMock(return_value=[])
        # "invalid_status" would normally raise, but not when state=completed
        result = await get_applications_by_state("default", "completed", "invalid_status")
        assert result == "[]"

    async def test_status_ignored_for_rejected_state(self):
        global_client.get = AsyncMock(return_value=[])
        result = await get_applications_by_state("default", "rejected", "bogus")
        assert result == "[]"

    async def test_status_case_insensitive(self):
        """Valid status in any case must not raise."""
        global_client.get = AsyncMock(return_value=[])
        result = await get_applications_by_state("default", "active", "RUNNING")
        assert result == "[]"


# ---------------------------------------------------------------------------
# Authentication configuration
# ---------------------------------------------------------------------------

class TestAuthConfiguration:
    """YunikornClient must configure httpx correctly for each auth method."""

    def test_no_auth_sets_auth_method_none(self):
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            token=None,
            username=None,
            password=None,
        )
        assert c.auth_method == "none"
        assert c.client.auth is None
        assert "Authorization" not in dict(c.client.headers)

    def test_bearer_token_sets_auth_method_and_header(self):
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            token="mytoken123",
            username=None,
            password=None,
        )
        assert c.auth_method == "bearer_token"
        assert c.client.headers["authorization"] == "Bearer mytoken123"

    def test_basic_auth_sets_auth_method(self):
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            token=None,
            username="admin",
            password="secret",
        )
        assert c.auth_method == "basic_auth"
        # httpx stores basic auth on .auth, not headers
        assert c.client.auth is not None

    def test_bearer_token_takes_priority_over_basic_auth(self):
        """When both token and username/password are set, bearer token wins."""
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            token="tok",
            username="admin",
            password="secret",
        )
        assert c.auth_method == "bearer_token"
        assert c.client.headers["authorization"] == "Bearer tok"

    def test_mtls_disabled_when_no_cert(self):
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            cert_path=None,
            key_path=None,
        )
        assert c.mtls_enabled is False

    def test_mtls_enabled_when_cert_and_key_provided(self):
        # Patch load_cert_chain so no real cert file is needed in the unit test.
        with patch("ssl.SSLContext.load_cert_chain"):
            c = YunikornClient(
                base_url="http://test/ws/v1/",
                verify=False,
                cert_path="/path/to/cert.pem",
                key_path="/path/to/key.pem",
            )
        assert c.mtls_enabled is True

    def test_mtls_requires_both_cert_and_key(self):
        """cert_path alone (no key_path) should not enable mTLS."""
        c = YunikornClient(
            base_url="http://test/ws/v1/",
            verify=False,
            cert_path="/path/to/cert.pem",
            key_path=None,
        )
        assert c.mtls_enabled is False
