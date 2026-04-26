#!/usr/bin/env python3
"""Quick test for updated applications_by_state with optional status param."""

import asyncio
import json
import sys
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "main", "--transport", "stdio"],
        env={"YUNIKORN_BASE_URL": os.environ.get("YUNIKORN_BASE_URL", "http://localhost:9089/ws/v1/")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== Test 1: active with default status ===")
            result = await session.call_tool("get_applications_by_state", {
                "partitionName": "default",
                "state": "active"
            })
            data = json.loads(result.content[0].text)
            print(f"Found {len(data)} apps (default status=running)")

            print("\n=== Test 2: active with status=running ===")
            result = await session.call_tool("get_applications_by_state", {
                "partitionName": "default",
                "state": "active",
                "status": "running"
            })
            data = json.loads(result.content[0].text)
            print(f"Found {len(data)} apps (explicit status=running)")

            print("\n=== Test 3: active with status=new ===")
            result = await session.call_tool("get_applications_by_state", {
                "partitionName": "default",
                "state": "active",
                "status": "new"
            })
            data = json.loads(result.content[0].text)
            print(f"Found {len(data)} apps (status=new)")

            print("\n=== Test 4: completed ===")
            result = await session.call_tool("get_applications_by_state", {
                "partitionName": "default",
                "state": "completed"
            })
            data = json.loads(result.content[0].text)
            print(f"Found {len(data)} apps (completed, no status param applied)")

            print("\n=== All tests passed ===")

asyncio.run(test())
