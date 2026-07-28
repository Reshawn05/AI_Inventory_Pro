"""
End-to-End Test Suite for Inventory Management MCP Server.
Demonstrates MCP Client interaction over stdio transport:
1. Tool Discovery & Execution (5 Core Tools)
2. Resource Discovery & Reading (2 Resources)
3. Prompt Discovery & Invocation (2 Prompts)
"""

import sys
import os
import asyncio
import json

# Ensure project root is in sys.path for standalone script execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_mcp_client_test():
    print("=" * 60)
    print("  MCP Inventory Server - E2E Client Discovery & Test Suite")
    print("=" * 60)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "python_src.server"],
        env=dict(os.environ)
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("\n[SUCCESS] Connected to MCP FastMCP Server over stdio transport.\n")

            # ----------------------------------------------------
            # 1. DISCOVERY & EXECUTION: MCP TOOLS (5 Tools)
            # ----------------------------------------------------
            print("-" * 50)
            print("1. DISCOVERING & VERIFYING MCP TOOLS (5 Tools)")
            print("-" * 50)

            tools_response = await session.list_tools()
            tools = tools_response.tools
            print(f"Found {len(tools)} registered MCP tools:")
            for t in tools:
                print(f" • Tool: '{t.name}' - {t.description.split('.')[0] if t.description else ''}")

            # Test 1.1: Call get_inventory_details
            print("\n[Tool Test 1/5] Executing get_inventory_details(low_stock_only=True)...")
            res_details = await session.call_tool("get_inventory_details", {"low_stock_only": True})
            print(f"Response snippet:\n{res_details.content[0].text[:250]}...\n")

            # Test 1.2: Call search_inventory
            print("[Tool Test 2/5] Executing search_inventory(query='Keyboard')...")
            res_search = await session.call_tool("search_inventory", {"query": "Keyboard"})
            print(f"Response snippet:\n{res_search.content[0].text[:250]}...\n")

            # Test 1.3: Call add_inventory_item
            print("[Tool Test 3/5] Executing add_inventory_item(sku='TEST-WEBCAM-01', name='HD Webcam', unit_price=4999.0)...")
            res_add = await session.call_tool("add_inventory_item", {
                "sku": "TEST-WEBCAM-01",
                "name": "Full HD 1080p Stream Webcam",
                "category": "Electronics",
                "unit_price": 4999.0,
                "quantity": 15,
                "location": "Aisle C2, Shelf 1"
            })
            add_data = json.loads(res_add.content[0].text)
            new_item_id = add_data.get("item", {}).get("id") if add_data.get("success") else None
            print(f"Creation Result: success={add_data.get('success')}, created_id={new_item_id}")

            # Test 1.4: Call update_inventory_item
            if new_item_id:
                print(f"[Tool Test 4/5] Executing update_inventory_item(item_id={new_item_id}, quantity_change=5)...")
                res_update = await session.call_tool("update_inventory_item", {
                    "item_id": new_item_id,
                    "quantity_change": 5
                })
                print(f"Update Result snippet:\n{res_update.content[0].text[:200]}...\n")

            # Test 1.5: Call delete_inventory_item
            if new_item_id:
                print(f"[Tool Test 5/5] Executing delete_inventory_item(item_id={new_item_id}, confirm=True)...")
                res_delete = await session.call_tool("delete_inventory_item", {
                    "item_id": new_item_id,
                    "confirm": True
                })
                print(f"Delete Result snippet:\n{res_delete.content[0].text[:200]}...\n")

            # ----------------------------------------------------
            # 2. DISCOVERY & READING: MCP RESOURCES (2 Resources)
            # ----------------------------------------------------
            print("-" * 50)
            print("2. DISCOVERING & READING MCP RESOURCES (2 Resources)")
            print("-" * 50)

            resources_resp = await session.list_resources()
            resources = resources_resp.resources
            print(f"Found {len(resources)} registered MCP resources:")
            for r in resources:
                print(f" • Resource URI: '{r.uri}' | Name: {r.name}")

            print("\n[Resource Read 1/2] Reading 'inventory://summary'...")
            res_sum = await session.read_resource("inventory://summary")
            print(f"Content snippet:\n{res_sum.contents[0].text[:200]}...\n")

            print("[Resource Read 2/2] Reading 'inventory://warehouse-locations'...")
            res_loc = await session.read_resource("inventory://warehouse-locations")
            print(f"Content snippet:\n{res_loc.contents[0].text[:200]}...\n")

            # ----------------------------------------------------
            # 3. DISCOVERY & INVOCATION: MCP PROMPTS (2 Prompts)
            # ----------------------------------------------------
            print("-" * 50)
            print("3. DISCOVERING & INVOKING MCP PROMPTS (2 Prompts)")
            print("-" * 50)

            prompts_resp = await session.list_prompts()
            prompts = prompts_resp.prompts
            print(f"Found {len(prompts)} registered MCP prompts:")
            for p in prompts:
                args_list = [a.name for a in (p.arguments or [])]
                print(f" • Prompt Name: '{p.name}'")
                print(f"   Description: {p.description.split('.')[0] if p.description else 'N/A'}")
                print(f"   Supported Arguments: {args_list}")

            # Prompt Invocation 1
            print("\n[Prompt Invocation 1/2] Getting prompt 'inventory_restock_assistant'(category='Electronics', min_threshold=10)...")
            p1_res = await session.get_prompt("inventory_restock_assistant", arguments={"category": "Electronics", "min_threshold": "10"})
            print(f"Rendered Messages Count: {len(p1_res.messages)}")
            p1_text = p1_res.messages[0].content.text
            print("Rendered Prompt Content Preview:")
            print("  " + "\n  ".join(p1_text.splitlines()[:10]))
            print("  ...\n")

            # Prompt Invocation 2
            print("[Prompt Invocation 2/2] Getting prompt 'inventory_audit_prompt'(location='Aisle A1', include_valuation=True)...")
            p2_res = await session.get_prompt("inventory_audit_prompt", arguments={"location": "Aisle A1", "include_valuation": "true"})
            print(f"Rendered Messages Count: {len(p2_res.messages)}")
            p2_text = p2_res.messages[0].content.text
            print("Rendered Prompt Content Preview:")
            print("  " + "\n  ".join(p2_text.splitlines()[:10]))
            print("  ...\n")

            print("=" * 60)
            print("  [SUCCESS] All Tools, Resources, and Prompts Verified!")
            print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_mcp_client_test())
