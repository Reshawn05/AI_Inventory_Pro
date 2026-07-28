import os
import sys
import json
from typing import Optional, Dict, Any

# Ensure project root is in sys.path for standalone script execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

try:
    from python_src.database import (
        init_db,
        list_items,
        get_item_by_id,
        get_item_by_sku,
        search_items,
        add_item,
        update_item,
        delete_item,
        get_inventory_summary
    )
    import python_src.server as server_module
    from python_src.gemini_service import get_gemini_service
except ImportError:
    from database import (
        init_db,
        list_items,
        get_item_by_id,
        get_item_by_sku,
        search_items,
        add_item,
        update_item,
        delete_item,
        get_inventory_summary
    )
    import server as server_module
    from gemini_service import get_gemini_service

# Initialise the Gemini service once at startup (singleton).
# Logs a warning and sets available=False if GEMINI_API_KEY is not configured.
_gemini = get_gemini_service()

app = FastAPI(
    title="Inventory Management System - MCP Dashboard",
    description="Professional Presentation Web Dashboard & MCP Tool Tester (INR ₹)"
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("MCP.WebApp").error(f"Global unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "An internal server error occurred."}
    )

# Ensure DB is initialized with fresh INR seed data
init_db(reset_seed=True)

# Path to static directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend index.html missing</h1>"

# ----------------------------------------------------
# REST API Endpoints for Web Dashboard (Powered by MCP Engine)
# ----------------------------------------------------

@app.get("/api/summary")
def api_get_summary():
    """Retrieve aggregate inventory summary metrics using MCP Resource inventory://summary."""
    res_str = server_module.get_inventory_summary_resource()
    res_json = json.loads(res_str)
    raw_summary = get_inventory_summary()
    return {
        "mcp_resource": "inventory://summary",
        "clean_report": res_json,
        "total_items": raw_summary["total_items"],
        "total_quantity": raw_summary["total_quantity"],
        "total_inventory_value": raw_summary["total_inventory_value"],
        "low_stock_items_count": raw_summary["low_stock_items_count"],
        "categories_count": raw_summary["categories_count"]
    }

@app.get("/api/warehouse")
def api_get_warehouse():
    """Retrieve warehouse location cards using MCP Resource inventory://warehouse-locations."""
    res_str = server_module.get_warehouse_locations_resource()
    return json.loads(res_str)

@app.get("/api/inventory")
def api_list_inventory(
    category: Optional[str] = None,
    low_stock_only: bool = False,
    query: Optional[str] = None
):
    """Retrieve inventory items via MCP Tool get_inventory_details / search_inventory."""
    if query and query.strip():
        raw_res = server_module.search_inventory(query.strip())
        data = json.loads(raw_res)
        items = data.get("results", [])
        if category:
            items = [i for i in items if i["category"].lower() == category.lower()]
        if low_stock_only:
            items = [i for i in items if i["quantity"] <= i["min_stock_threshold"]]
        return {"items": items, "count": len(items), "mcp_tool_used": "search_inventory"}
    else:
        raw_res = server_module.get_inventory_details(category=category, low_stock_only=low_stock_only)
        data = json.loads(raw_res)
        items = data.get("items", [])
        return {"items": items, "count": len(items), "mcp_tool_used": "get_inventory_details"}

@app.get("/api/inventory/{item_id}")
def api_get_item(item_id: int):
    """Get single item by ID via MCP Tool get_inventory_details."""
    raw_res = server_module.get_inventory_details(item_id=item_id)
    data = json.loads(raw_res)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data.get("item", {})

@app.post("/api/inventory")
async def api_create_item(request: Request):
    """Create a new item in inventory via MCP Tool add_inventory_item."""
    data = await request.json()
    sku = data.get("sku", "").strip()
    name = data.get("name", "").strip()
    category = data.get("category", "").strip()
    unit_price = float(data.get("unit_price", 0))
    quantity = int(data.get("quantity", 0))
    location = data.get("location", "Main Warehouse").strip()
    min_stock_threshold = int(data.get("min_stock_threshold", 10))
    description = data.get("description", "").strip()

    raw_res = server_module.add_inventory_item(
        sku=sku,
        name=name,
        category=category,
        unit_price=unit_price,
        quantity=quantity,
        location=location,
        min_stock_threshold=min_stock_threshold,
        description=description
    )
    res_json = json.loads(raw_res)
    if "error" in res_json:
        raise HTTPException(status_code=400, detail=res_json["error"])
    return {"success": True, "item": res_json.get("item"), "mcp_tool_used": "add_inventory_item"}

@app.put("/api/inventory/{item_id}")
async def api_update_item(item_id: int, request: Request):
    """Update item fields by ID via MCP Tool update_inventory_item."""
    data = await request.json()
    
    raw_res = server_module.update_inventory_item(
        item_id=item_id,
        new_quantity=data.get("quantity"),
        unit_price=data.get("unit_price"),
        location=data.get("location"),
        min_stock_threshold=data.get("min_stock_threshold"),
        description=data.get("description")
    )
    res_json = json.loads(raw_res)
    if "error" in res_json:
        raise HTTPException(status_code=400, detail=res_json["error"])
    
    # Also update name & category if changed
    updates = {}
    if "name" in data: updates["name"] = data["name"]
    if "category" in data: updates["category"] = data["category"]
    if updates:
        update_item(item_id, updates)
        
    return {"success": True, "item": res_json.get("item"), "mcp_tool_used": "update_inventory_item"}

@app.delete("/api/inventory/{item_id}")
def api_delete_item(item_id: int):
    """Delete item by ID via MCP Tool delete_inventory_item."""
    raw_res = server_module.delete_inventory_item(item_id=item_id, confirm=True)
    res_json = json.loads(raw_res)
    if "error" in res_json:
        raise HTTPException(status_code=400, detail=res_json["error"])
    return {"success": True, "deleted_id": item_id, "mcp_tool_used": "delete_inventory_item"}

@app.post("/api/ai/chat")
async def api_ai_chat(request: Request):
    """
    Process a natural language query through the AI assistant.

    Priority:
      1. Google Gemini AI  — uses MCP resources / prompts / tools as data layer.
      2. Rule-based fallback — existing keyword-matching assistant in server.py.
         Activated automatically when GEMINI_API_KEY is not set or Gemini errors.
    """
    body = await request.json()
    user_message = body.get("message", "")
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Try Gemini first. Returns None when unavailable → use rule-based fallback.
    gemini_result = _gemini.process_query(user_message, server_module)
    if gemini_result is not None:
        return gemini_result

    # Fallback: rule-based keyword assistant (always works, no API key needed)
    return server_module.process_ai_assistant_query(user_message)

# Programmatic MCP compatibility endpoints
MCP_TOOLS_METADATA = [
    {"name": "get_inventory_details", "category": "Data retrieval tool"},
    {"name": "search_inventory", "category": "Search tool"},
    {"name": "add_inventory_item", "category": "Insert tool"},
    {"name": "update_inventory_item", "category": "Update tool"},
    {"name": "delete_inventory_item", "category": "Delete tool"}
]

@app.get("/api/mcp/tools")
def api_get_mcp_tools():
    return {"tools": MCP_TOOLS_METADATA}

@app.get("/api/mcp/resources")
def api_get_mcp_resources():
    return {"resources": [
        {"uri": "inventory://summary", "name": "Inventory Summary"},
        {"uri": "inventory://warehouse-locations", "name": "Warehouse Locations"}
    ]}

@app.get("/api/mcp/prompts")
def api_get_mcp_prompts():
    """
    PROMPT DISCOVERY endpoint.
    Lists all registered MCP prompts, their descriptions, and accepted arguments.
    This is the programmatic equivalent of mcp.list_prompts() over the MCP protocol.
    An MCP client would call this to discover what prompts are available before invoking one.
    """
    return {"prompts": [
        {
            "name": "inventory_restock_assistant",
            "description": "Guides stock replenishment analysis for low-inventory items",
            "arguments": [
                {"name": "category", "description": "Category to filter (e.g. Electronics, Supplies)", "required": False, "default": "All Categories"},
                {"name": "min_threshold", "description": "Stock quantity threshold for reorder alerts", "required": False, "default": 10}
            ]
        },
        {
            "name": "inventory_audit_prompt",
            "description": "Conducts location-specific stock audit and valuation report",
            "arguments": [
                {"name": "location", "description": "Warehouse or aisle to audit (e.g. Goa Warehouse)", "required": False, "default": "All Locations"},
                {"name": "include_valuation", "description": "Whether to include financial valuation in the report", "required": False, "default": True}
            ]
        }
    ]}


@app.post("/api/mcp/prompts/{prompt_name}")
async def api_invoke_prompt(prompt_name: str, request: Request):
    """
    PROMPT INVOCATION endpoint.
    Invokes a specific registered MCP prompt by name with provided arguments.
    Returns the generated prompt instruction string AND the assistant's response.
    This is the programmatic equivalent of mcp.get_prompt(name, arguments) over the MCP protocol.
    """
    body = await request.json()

    # Look up the prompt in the registry (discovery check)
    if prompt_name not in server_module.PROMPT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found in registry.")

    prompt_meta = server_module.PROMPT_REGISTRY[prompt_name]

    try:
        # INVOCATION: Call the @mcp.prompt registered function with provided arguments
        prompt_fn = prompt_meta["fn"]
        # Filter only valid kwargs for this prompt
        valid_args = {k: v for k, v in body.items() if k in prompt_meta["args"]}
        prompt_text = prompt_fn(**valid_args)

        # Also process through the assistant for a complete response
        # Build a synthetic user message that will match the prompt's intent keywords
        synthetic_msg = f"inventory {prompt_name.replace('_', ' ')} {' '.join(str(v) for v in valid_args.values())}"
        assistant_response = server_module.process_ai_assistant_query(synthetic_msg)

        return {
            "prompt_name": prompt_name,
            "arguments_used": valid_args,
            "generated_prompt": prompt_text,
            "assistant_reply": assistant_response.get("reply", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def start():
    uvicorn.run(
        "python_src.web_app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=["*.log", "*.db", "logs/*", "mcp_server.log"]
    )

if __name__ == "__main__":
    start()

