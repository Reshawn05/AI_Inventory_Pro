# Inventory Management System - Custom MCP Server

A custom Model Context Protocol (MCP) server written in Python using the official **MCP SDK** (`mcp.server.fastmcp`). This server provides an end-to-end **Inventory Management System** interface enabling LLM assistants to retrieve stock data, search inventory, insert new products, update stock levels/metadata, and safely delete items.

---

## Features & Capabilities

- **Official MCP SDK Integration**: Built with `FastMCP` from `mcp.server.fastmcp`.
- **Local SQLite Database Storage**: Automatic database setup and seed data generation upon initial launch (`inventory.db`) with pricing in INR (₹).
- **Core 5-Toolsuite & 2 Resources**: Exactly 5 custom tools and 2 MCP resources (`inventory://summary` and `inventory://warehouse-locations`) for AI consumption.
- **Automated E2E Client Test Suite**: Included async test client using standard MCP `stdio` transport.

---

## Project Structure

```
MCP/
├── python_src/
│   ├── __init__.py           # Package initializer
│   ├── database.py           # SQLite database schema, CRUD functions, and INR seed data
│   ├── models.py             # Pydantic data schemas & response validation models
│   ├── server.py             # Main FastMCP Server with 5 core tools & 2 resources
│   ├── web_app.py            # Dashboard REST API and FastMCP tool/resource runner
│   └── client_test.py        # End-to-end automated test suite demonstrating MCP client interactions
├── static/                   # Web dashboard frontend (HTML, CSS, JS)
├── mcp_config_example.json   # Configuration file template for Claude Desktop / MCP Clients
├── requirements.txt          # Python project dependencies
├── inventory.db              # SQLite database (auto-generated)
└── README.md                 # Project documentation
```

---

## MCP Tools Implemented

The server exposes **exactly 5 tools** that fulfill all inventory management requirements with pricing in **INR (₹)**:

| Tool Name | Type / Capability | Description | Input Parameters |
| :--- | :--- | :--- | :--- |
| `get_inventory_details` | **Data Retrieval Tool** | Fetch full product details by item_id or SKU, or list all stock items with totals in INR (₹) | `item_id`, `sku`, `category`, `low_stock_only` |
| `search_inventory` | **Search Tool** | Case-insensitive multi-field search across SKU, name, category, location, and description | `query` |
| `add_inventory_item` | **Insert Tool** | Insert a new item into inventory with unit price in INR (₹) and SKU validation | `sku`, `name`, `category`, `unit_price`, `quantity`, `location`, `min_stock_threshold`, `description` |
| `update_inventory_item` | **Update Tool** | Adjust stock quantities (relative +/- change or absolute set) and update price in INR (₹) or location | `item_id`, `quantity_change`, `new_quantity`, `unit_price`, `location`, `min_stock_threshold`, `description` |
| `delete_inventory_item` | **Delete Tool** | Safely remove an item by ID (requires explicit safety confirmation) | `item_id`, `confirm` |

---

## MCP Resources Implemented

The server exposes **2 structured MCP resources** for AI agents to consume context directly:

| Resource URI | Resource Name | Description | MIME Type |
| :--- | :--- | :--- | :--- |
| `inventory://summary` | **Inventory Summary** | Aggregate summary metrics: total items, total quantity, total stock valuation in INR (₹), low-stock count, category count | `application/json` |
| `inventory://warehouse-locations` | **Warehouse Locations** | Minimal summary containing only locations list with `name`, `products` count, and `units` stored | `application/json` |

---

## MCP Prompts Implemented

The server exposes **2 custom MCP prompt templates** (`@mcp.prompt()`) for LLM client discovery and dynamic prompt rendering with live context:

| Prompt Name | Prompt Title | Description | Supported Arguments |
| :--- | :--- | :--- | :--- |
| `inventory_restock_assistant` | **Inventory Restock Assistant Prompt** | Generates a structured stock reordering & purchasing recommendation prompt pre-populated with live database low-stock alerts and pricing in INR (₹) | `category` (str, optional), `min_threshold` (int, default 10) |
| `inventory_audit_prompt` | **Inventory Audit Prompt** | Generates an executive stock auditing, risk compliance, and location verification prompt for governance checks | `location` (str, optional), `include_valuation` (bool, default True) |

### How MCP Prompts are Discovered & Invoked

1. **Discovery Protocol (`prompts/list`)**:
   - MCP clients (Claude Desktop, custom agents) request available prompts from the server via JSON-RPC `prompts/list`.
   - The server returns metadata including prompt names, descriptions, and argument schemas.
   - **Python SDK Client**: `prompts_resp = await session.list_prompts()`

2. **Invocation Protocol (`prompts/get`)**:
   - Clients call `prompts/get` specifying the `name` of the prompt and input `arguments`.
   - The FastMCP server executes the prompt handler function, injects live metrics from SQLite database, and returns formatted LLM `messages`.
   - **Python SDK Client**: `prompt_res = await session.get_prompt("inventory_restock_assistant", arguments={"category": "Electronics"})`

---


## Installation & Setup

### Prerequisites
- Python 3.10 or higher installed.

### 1. Clone / Navigate to Directory
```bash
cd a:/Work/MCP
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Running the Server Locally

To run the MCP server manually over standard `stdio` transport:
```bash
python -m python_src.server
```

---

## Running End-to-End Verification Tests

To verify that the MCP server initializes, exposes tools and resources, and executes all 5 tool capabilities and 2 resource reads correctly over an active MCP client session:

```bash
python -m python_src.client_test
```

### Expected Output Summary:
```
==================================================
  MCP Inventory Management Server - E2E Test Suite
==================================================

[1] Starting MCP Server process: python -m python_src.server...
[2] Initializing MCP Session...
    Session initialized successfully!

--------------------------------------------------
  Test 1: Discovering MCP Tools
--------------------------------------------------
Total Tools Discovered: 5

  Test 2: Data Retrieval Tool (get_inventory_details) -> Passed
  Test 3: Search Tool (search_inventory) -> Passed
  Test 4: Create/Insert Tool (add_inventory_item) -> Passed
  Test 5: Update Tool (update_inventory_item) -> Passed
  Test 6: Delete Tool (delete_inventory_item) -> Passed
  Test 7: Discovering MCP Resources (2 Discovered) -> Passed
  Test 8: Reading Resource (inventory://summary) -> Passed
  Test 9: Reading Resource (inventory://warehouse-locations) -> Passed

==================================================
  ALL 5 TOOL & 2 RESOURCE TESTS PASSED SUCCESSFULLY!
==================================================
```

---

## Configuring with MCP Clients (Claude Desktop / Cursor / Antigravity)

To connect this custom MCP server to Claude Desktop or any compatible MCP client, add the following entry to your `claude_desktop_config.json` (or client settings):

```json
{
  "mcpServers": {
    "inventory-management": {
      "command": "python",
      "args": [
        "-m",
        "python_src.server"
      ],
      "cwd": "a:/Work/MCP"
    }
  }
}
```
