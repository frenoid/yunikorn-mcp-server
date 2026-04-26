#!/usr/bin/env python3
"""Test script for the YuniKorn MCP server."""

import asyncio
import json
import sys
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_tests():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "main", "--transport", "stdio"],
        env={"YUNIKORN_BASE_URL": os.environ.get("YUNIKORN_BASE_URL", "http://localhost:9089/ws/v1/")}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=" * 60)
            print("TOOL TESTS")
            print("=" * 60)

            # List tools
            tools_result = await session.list_tools()
            tools = tools_result.tools
            print(f"\nAvailable tools ({len(tools)}):")
            for tool in tools:
                print(f"  - {tool.name}")

            # Test get_partitions
            print("\n--- get_partitions ---")
            result = await session.call_tool("get_partitions", {})
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test get_partition_queues
            print("\n--- get_partition_queues (default) ---")
            result = await session.call_tool(
                "get_partition_queues", {"partitionName": "default"}
            )
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test get_applications_by_state (active / running)
            print("\n--- get_applications_by_state (active, running) ---")
            result = await session.call_tool(
                "get_applications_by_state",
                {"partitionName": "default", "state": "active"},
            )
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test get_applications_by_state (completed)
            print("\n--- get_applications_by_state (completed) ---")
            result = await session.call_tool(
                "get_applications_by_state",
                {"partitionName": "default", "state": "completed"},
            )
            data = json.loads(result.content[0].text)
            print(f"Completed apps count: {len(data)}")
            if data:
                print(json.dumps(data[0], indent=2))

            # Test get_applications_by_state (rejected)
            print("\n--- get_applications_by_state (rejected) ---")
            result = await session.call_tool(
                "get_applications_by_state",
                {"partitionName": "default", "state": "rejected"},
            )
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test get_node_details (all nodes)
            print("\n--- get_node_details (all) ---")
            result = await session.call_tool(
                "get_node_details", {"partitionName": "default"}
            )
            data = json.loads(result.content[0].text)
            print(f"Nodes count: {len(data)}")
            for node in data:
                print(f"  - {node['nodeID']}: vcore={node['capacity'].get('vcore')}, memory={node['capacity'].get('memory')}")

            # Test get_node_details (single node)
            print("\n--- get_node_details (single) ---")
            node_id = data[0]["nodeID"] if data else "llmops-control-plane"
            result = await session.call_tool(
                "get_node_details", {"partitionName": "default", "nodeId": node_id}
            )
            single_node = json.loads(result.content[0].text)
            print(json.dumps(single_node, indent=2))

            # Test get_user_usage (all users)
            print("\n--- get_user_usage (all) ---")
            result = await session.call_tool(
                "get_user_usage", {"partitionName": "default"}
            )
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test check_scheduler_health
            print("\n--- check_scheduler_health ---")
            result = await session.call_tool("check_scheduler_health", {})
            data = json.loads(result.content[0].text)
            print(json.dumps(data, indent=2))

            # Test inspect_application (need to find an app first)
            print("\n--- inspect_application ---")
            result = await session.call_tool(
                "get_applications_by_state",
                {"partitionName": "default", "state": "completed"},
            )
            apps = json.loads(result.content[0].text)
            if apps:
                app_id = apps[0]["applicationID"]
                print(f"Inspecting application: {app_id}")
                result = await session.call_tool(
                    "inspect_application",
                    {"partitionName": "default", "appId": app_id},
                )
                app_data = json.loads(result.content[0].text)
                print(json.dumps(app_data, indent=2))
            else:
                print("No applications found to inspect.")

            print("\n" + "=" * 60)
            print("RESOURCE TESTS")
            print("=" * 60)

            # List resources
            resources_result = await session.list_resources()
            resources = resources_result.resources
            print(f"\nAvailable resources ({len(resources)}):")
            for res in resources:
                print(f"  - {res.uri}")

            # Read partitions resource
            print("\n--- resource: yunikorn://partitions/list ---")
            content = await session.read_resource("yunikorn://partitions/list")
            print(content.contents[0].text[:500])

            # Read node utilizations resource
            print("\n--- resource: yunikorn://nodes/utilization ---")
            content = await session.read_resource("yunikorn://nodes/utilization")
            print(content.contents[0].text[:500])

            print("\n" + "=" * 60)
            print("ALL TESTS COMPLETED SUCCESSFULLY")
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
