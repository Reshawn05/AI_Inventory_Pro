import os
import sys
import json
import re
import time
import logging
from functools import wraps
from typing import Optional, Dict, Any, List

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mcp.server.fastmcp import FastMCP

try:
    from python_src.Database.database import (
        init_db,
        list_items,
        get_item_by_id,
        get_item_by_sku,
        search_items,
        add_item,
        update_item,
        delete_item,
        get_inventory_summary,
        get_warehouse_locations_summary,
        get_inventory_summary_clean,
        get_warehouse_locations_minimal_summary,
        get_inventory_logs,
        bulk_update_items
    )
except ImportError:
    from Database.database import (
        init_db,
        list_items,
        get_item_by_id,
        get_item_by_sku,
        search_items,
        add_item,
        update_item,
        delete_item,
        get_inventory_summary,
        get_warehouse_locations_summary,
        get_inventory_summary_clean,
        get_warehouse_locations_minimal_summary,
        get_inventory_logs,
        bulk_update_items
    )

# Initialize FastMCP Server
mcp = FastMCP(
    name="Inventory Management System",
    instructions="MCP Server providing core inventory management capabilities: Data Retrieval, Search, Insert, Update, Delete, and Bulk Updates."
)

# Setup logger for MCP Tool execution and server observability (Console + File)
log_dir = os.path.join(project_root, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "mcp_server.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, encoding="utf-8")
    ],
    force=True
)

# Silence third-party file watcher logs from polluting mcp_server.log
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

logger = logging.getLogger("MCP.ToolServer")

def log_tool_execution(func):
    """
    Observability decorator & exception guard for MCP tools.
    Logs tool calls, tool responses, execution time, and errors.
    Prevents tool execution exceptions from crashing the MCP server.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        logger.info(f"[TOOL CALL] Invoking '{tool_name}' with args={kwargs or args}")
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Check if JSON payload contains an error field
            if isinstance(result, str) and '"error":' in result:
                logger.warning(
                    f"[TOOL RESPONSE - ERROR] '{tool_name}' completed in {duration_ms:.2f}ms with error response. "
                    f"Output snippet: {result[:200]}"
                )
            else:
                res_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                logger.info(
                    f"[TOOL RESPONSE] '{tool_name}' completed successfully in {duration_ms:.2f}ms. "
                    f"Output: {res_preview}"
                )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[TOOL ERROR] '{tool_name}' failed after {duration_ms:.2f}ms with exception: {exc}",
                exc_info=True
            )
            return json.dumps({
                "success": False,
                "error": f"Internal tool execution error in '{tool_name}': {str(exc)}"
            }, indent=2)
    return wrapper

# MCP TOOLS 

@mcp.tool()
@log_tool_execution
def get_inventory_details(
    item_id: Optional[int] = None,
    sku: Optional[str] = None,
    category: Optional[str] = None,
    low_stock_only: bool = False,
    limit: int = 50,
    offset: int = 0
) -> str:
    """1. Data Retrieval Tool: Fetch inventory records or specific product details in INR (₹) with pagination.

    Args:
        item_id: Database integer ID to get a specific item.
        sku: Unique SKU code string to get a specific item.
        category: Filter items by category name (e.g. 'Electronics').
        low_stock_only: If True, only returns items where quantity <= min_stock_threshold.
        limit: Max number of items to return (default 50).
        offset: Pagination offset starting index (default 0).

    Returns:
        JSON string containing single item details or a list of inventory items with overall valuation in INR (₹).
    """
    if item_id is not None or sku is not None:
        item = get_item_by_id(item_id) if item_id is not None else get_item_by_sku(sku)
        if not item:
            return json.dumps({"error": f"Item not found for item_id={item_id}, sku='{sku}'."}, indent=2)
        return json.dumps({"success": True, "currency": "INR (₹)", "item": item}, indent=2)

    items = list_items(category=category, low_stock_only=low_stock_only, limit=limit, offset=offset)
    summary = get_inventory_summary()
    return json.dumps({
        "success": True,
        "currency": "INR (₹)",
        "count": len(items),
        "total_inventory_value_inr": summary["total_inventory_value"],
        "limit": limit,
        "offset": offset,
        "items": items
    }, indent=2)

@mcp.tool()
@log_tool_execution
def search_inventory(query: str) -> str:
    """2. Search Tool: Search inventory across SKU, product name, category, storage location, and description.

    Args:
        query: Search term or keyword (e.g. 'Keyboard', 'Aisle A1', 'Monitor').

    Returns:
        JSON string listing matching items and match count.
    """
    if not query or not query.strip():
        return json.dumps({"error": "Search query cannot be empty."}, indent=2)

    results = search_items(query.strip())
    return json.dumps({
        "success": True,
        "query": query,
        "currency": "INR (₹)",
        "match_count": len(results),
        "results": results
    }, indent=2)

@mcp.tool()
@log_tool_execution
def add_inventory_item(
    sku: str,
    name: str,
    category: str,
    unit_price: float,
    quantity: int = 0,
    location: str = "Main Warehouse",
    min_stock_threshold: int = 10,
    description: str = ""
) -> str:
    """3. Insert Tool: Register a new product item into the inventory database with price in INR (₹).

    Args:
        sku: Unique Stock Keeping Unit identifier (e.g., 'LAPTOP-PRO-16').
        name: Product name/title.
        category: Category (e.g., 'Electronics', 'Office Furniture').
        unit_price: Price per unit in Indian Rupees INR ₹ (> 0).
        quantity: Initial stock quantity (default 0).
        location: Storage location string.
        min_stock_threshold: Minimum threshold before reorder warning (default 10).
        description: Optional item description.

    Returns:
        JSON string of the newly created inventory item record.
    """
    existing = get_item_by_sku(sku)
    if existing:
        return json.dumps({"error": f"Item with SKU '{sku}' already exists with ID {existing['id']}."}, indent=2)

    if unit_price <= 0:
        return json.dumps({"error": "unit_price must be greater than 0 INR (₹)."}, indent=2)

    item_dict = {
        "sku": sku,
        "name": name,
        "category": category,
        "quantity": max(0, quantity),
        "unit_price": unit_price,
        "location": location,
        "min_stock_threshold": max(0, min_stock_threshold),
        "description": description
    }

    created = add_item(item_dict)
    return json.dumps({
        "success": True,
        "message": "Item successfully created in inventory.",
        "currency": "INR (₹)",
        "item": created
    }, indent=2)

@mcp.tool()
@log_tool_execution
def update_inventory_item(
    item_id: int,
    quantity_change: Optional[int] = None,
    new_quantity: Optional[int] = None,
    unit_price: Optional[float] = None,
    location: Optional[str] = None,
    min_stock_threshold: Optional[int] = None,
    description: Optional[str] = None
) -> str:
    """4. Update Tool: Modify attributes or adjust stock quantity/price in INR (₹) for an existing product.

    Args:
        item_id: Database ID of the item to update.
        quantity_change: Relative change in quantity (e.g. +10 for stock in, -5 for stock out).
        new_quantity: Absolute set quantity (overrides quantity_change if provided).
        unit_price: Updated unit price in INR ₹ (> 0).
        location: Updated storage location.
        min_stock_threshold: Updated reorder alert threshold.
        description: Updated product description.

    Returns:
        JSON string of the updated inventory record.
    """
    existing = get_item_by_id(item_id)
    if not existing:
        return json.dumps({"error": f"Item with ID {item_id} not found."}, indent=2)

    updates = {}
    if new_quantity is not None:
        updates["quantity"] = max(0, new_quantity)
    elif quantity_change is not None:
        current_qty = existing["quantity"]
        updates["quantity"] = max(0, current_qty + quantity_change)

    if unit_price is not None:
        if unit_price <= 0:
            return json.dumps({"error": "unit_price must be greater than 0 INR (₹)."}, indent=2)
        updates["unit_price"] = unit_price

    if location is not None:
        updates["location"] = location

    if min_stock_threshold is not None:
        updates["min_stock_threshold"] = max(0, min_stock_threshold)

    if description is not None:
        updates["description"] = description

    if not updates:
        return json.dumps({"message": "No changes requested.", "item": existing}, indent=2)

    updated_item = update_item(item_id, updates)
    return json.dumps({
        "success": True,
        "message": f"Item {item_id} successfully updated.",
        "currency": "INR (₹)",
        "item": updated_item
    }, indent=2)

@mcp.tool()
@log_tool_execution
def delete_inventory_item(item_id: int, confirm: bool = False) -> str:
    """5. Delete Tool: Remove an item from the inventory database.

    Args:
        item_id: Database ID of the item to remove.
        confirm: Confirmation safety flag (must be set to True to complete deletion).

    Returns:
        JSON status message confirming deletion.
    """
    if not confirm:
        return json.dumps({
            "error": "Safety check failed. Pass confirm=True to confirm item deletion.",
            "item_id": item_id
        }, indent=2)

    existing = get_item_by_id(item_id)
    if not existing:
        return json.dumps({"error": f"Item with ID {item_id} not found."}, indent=2)

    success = delete_item(item_id)
    if success:
        return json.dumps({
            "success": True,
            "message": f"Item {item_id} ('{existing['name']}', SKU: {existing['sku']}) deleted.",
            "deleted_item": existing
        }, indent=2)
    else:
        return json.dumps({"error": f"Failed to delete item {item_id}."}, indent=2)

@mcp.tool()
@log_tool_execution
def bulk_update_inventory(updates_json: str) -> str:
    """6. Bulk Update Tool: Batch update stock quantity, price, or details for multiple items atomically.

    Args:
        updates_json: JSON string representing a list of update objects.
                      Example: '[{"item_id": 1, "new_quantity": 50}, {"item_id": 2, "unit_price": 12500.0}]'

    Returns:
        JSON string containing batch update execution summary.
    """
    try:
        updates_list = json.loads(updates_json)
        if not isinstance(updates_list, list):
            return json.dumps({"error": "updates_json must be a valid JSON array of update objects."}, indent=2)
        
        result = bulk_update_items(updates_list)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError as err:
        return json.dumps({"error": f"Invalid JSON string format: {err}"}, indent=2)

# MCP RESOURCES 

@mcp.resource("inventory://summary", mime_type="application/json")
def get_inventory_summary_resource() -> str:
    """MCP Resource 1: Structured aggregate summary metrics of total stock and valuation in INR (₹)."""
    return json.dumps(get_inventory_summary_clean(), indent=2)

@mcp.resource("inventory://warehouse-locations", mime_type="application/json")
def get_warehouse_locations_resource() -> str:
    """MCP Resource 2: Minimal summary of warehouse locations containing location name, products count, and units count."""
    return json.dumps(get_warehouse_locations_minimal_summary(), indent=2)


# MCP PROMPTS 


@mcp.prompt("inventory_restock_assistant")
def inventory_restock_assistant(category: str = "All Categories", min_threshold: int = 10) -> str:
    """MCP Prompt 1: Assistant template to guide stock replenishment analysis for low-inventory items."""
    return (
        f"Please analyze all items in category '{category}' with stock quantity <= {min_threshold}. "
        f"Recommend reorder quantities and priority based on unit price and location."
    )

@mcp.prompt("inventory_audit_prompt")
def inventory_audit_prompt(location: str = "All Locations", include_valuation: bool = True) -> str:
    """MCP Prompt 2: Assistant template for conducting location-specific stock audit and valuation report."""
    return (
        f"Conduct a complete inventory audit for storage location '{location}' "
        f"(Include valuation: {include_valuation}). "
        f"Summarize total stock units, high-value items, and suggest optimal space allocation."
    )

# PROMPT REGISTRY

PROMPT_REGISTRY: Dict[str, Dict] = {
    "inventory_restock_assistant": {
        # The actual @mcp.prompt registered function
        "fn": inventory_restock_assistant,
        "description": "Guides stock replenishment analysis for low-inventory items",
        # Intent keywords: any of these in the user message triggers this prompt
        "intent_keywords": [
            "restock", "reorder", "replenish", "low stock", "out of stock",
            "what should i order", "what to order", "need ordering", "order more",
            "which products need", "shortage", "running low", "below threshold",
            "suggest reorder", "procurement"
        ],
        "args": {
            "category": {"type": str, "default": None},
            "min_threshold": {"type": int, "default": 10}
        }
    },
    "inventory_audit_prompt": {
        "fn": inventory_audit_prompt,
        "description": "Conducts location-specific stock audit and valuation report",
        "intent_keywords": [
            "audit", "inventory health", "stock health", "inventory status",
            "stock status", "which warehouse", "warehouse needs attention",
            "overall status", "full report", "complete report", "inventory report",
            "generate report", "show inventory", "health check"
        ],
        "args": {
            "location": {"type": str, "default": None},
            "include_valuation": {"type": bool, "default": True}
        }
    }
}
 
# PROMPT DISCOVERY: detect_prompt_intent()

def detect_prompt_intent(user_message: str) -> Optional[str]:
    """Determine which registered MCP prompt best matches the user's intent."""
    msg = user_message.lower().strip()
    for prompt_name, meta in PROMPT_REGISTRY.items():
        for keyword in meta["intent_keywords"]:
            if keyword in msg:
                return prompt_name
    return None

# ARGUMENT EXTRACTION HELPERS

def _extract_restock_args(user_message: str) -> Dict[str, Any]:
    """Extract category and min_threshold arguments from a restock-related user message."""
    msg = user_message.lower()

    # Category detection — match known inventory categories
    category_map = {
        "electronics": "Electronics",
        "office furniture": "Office Furniture",
        "furniture": "Office Furniture",
        "supplies": "Supplies",
        "accessories": "Accessories"
    }
    detected_category = None
    for key, val in category_map.items():
        if key in msg:
            detected_category = val
            break

    # Threshold detection — look for numbers preceded by qualifier words
    min_threshold = 10  # default
    threshold_match = re.search(
        r'(?:below|under|less than|threshold|fewer than|<)\s*(\d+)', msg
    )
    if threshold_match:
        min_threshold = int(threshold_match.group(1))

    return {"category": detected_category, "min_threshold": min_threshold}


def _extract_audit_args(user_message: str) -> Dict[str, Any]:
    """Extract location and include_valuation arguments from an audit-related user message."""
    msg = user_message.lower()

    # Location detection — match known warehouse names and aisles
    location_map = {
        "goa": "Goa Warehouse",
        "pune": "Pune Warehouse",
        "mumbai": "Mumbai Warehouse",
        "delhi": "Delhi Warehouse",
        "aisle a": "Aisle A1",
        "aisle b": "Aisle B1",
        "aisle c": "Aisle C1",
    }
    detected_location = None
    for key, val in location_map.items():
        if key in msg:
            detected_location = val
            break

    # Valuation flag — include by default unless explicitly excluded
    include_valuation = True
    if any(phrase in msg for phrase in ["no valuation", "without valuation", "exclude valuation", "skip valuation"]):
        include_valuation = False

    return {"location": detected_location, "include_valuation": include_valuation}

# PROMPT INVOCATION: 

def _execute_restock_prompt(
    prompt_instructions: str,
    category: Optional[str],
    min_threshold: int
) -> Dict[str, Any]:
    """
    PROMPT INVOCATION — inventory_restock_assistant.
    Uses MCP Tool: get_inventory_details(low_stock_only=True) to fetch data
    guided by the prompt's instructions.
    """
    # Call MCP Tool as instructed by the prompt
    raw = json.loads(get_inventory_details(category=category, low_stock_only=True))
    items: List[Dict] = raw.get("items", [])

    # Apply threshold filter from prompt arguments
    items_below_threshold = [i for i in items if i["quantity"] <= min_threshold]

    return {
        "items": items_below_threshold,
        "category": category or "All Categories",
        "threshold": min_threshold,
        "prompt_instructions": prompt_instructions  # retained for traceability
    }


def _execute_audit_prompt(
    prompt_instructions: str,
    location: Optional[str],
    include_valuation: bool
) -> Dict[str, Any]:
    """
    PROMPT INVOCATION — inventory_audit_prompt.
    Uses MCP Resource: inventory://summary for overall metrics,
    MCP Tool: search_inventory() or get_inventory_details() for location data,
    MCP Resource: inventory://warehouse-locations for capacity data.
    """
    # Call MCP Resource for aggregate summary (as instructed by prompt)
    summary = json.loads(get_inventory_summary_resource())

    # Call MCP Tool or Resource for location-specific items
    if location:
        search_raw = json.loads(search_inventory(location))
        location_items: List[Dict] = search_raw.get("results", [])
    else:
        all_raw = json.loads(get_inventory_details())
        location_items = all_raw.get("items", [])

    # Call MCP Resource for warehouse capacity overview
    warehouse_data = json.loads(get_warehouse_locations_resource())

    return {
        "summary": summary,
        "location": location or "All Locations",
        "items": location_items,
        "warehouse": warehouse_data,
        "include_valuation": include_valuation,
        "prompt_instructions": prompt_instructions  # retained for traceability
    }

# RESPONSE FORMATTERS

def _format_restock_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Format restock analysis results into clean business language."""
    items: List[Dict] = data["items"]
    category: str = data["category"]
    threshold: int = data["threshold"]

    if not items:
        cat_text = f" in **{category}**" if category != "All Categories" else ""
        return {
            "reply": (
                f"Great news! All products{cat_text} are currently above the minimum "
                f"reorder threshold of {threshold} units. No immediate restocking action is required."
            )
        }

    # Sort by urgency: lowest stock first
    items_sorted = sorted(items, key=lambda x: x["quantity"])

    lines = []
    for item in items_sorted:
        lines.append(
            f"• **{item['name']}** — {item['quantity']} units remaining "
            f"(Reorder at: {item['min_stock_threshold']} units, "
            f"Location: {item['location']})"
        )

    # Tier-based recommendations
    critical = [i for i in items_sorted if i["quantity"] == 0]
    urgent = [i for i in items_sorted if 0 < i["quantity"] <= 3]
    moderate = [i for i in items_sorted if i["quantity"] > 3]

    recommendations = []
    if critical:
        names = ", ".join(f"**{i['name']}**" for i in critical)
        recommendations.append(f"🔴 **Immediate action required:** {names} {'is' if len(critical) == 1 else 'are'} completely out of stock.")
    if urgent:
        names = ", ".join(f"**{i['name']}**" for i in urgent)
        recommendations.append(f"🟠 **Reorder urgently:** {names} {'has' if len(urgent) == 1 else 'have'} critically low stock (≤3 units).")
    if moderate:
        names = ", ".join(f"**{i['name']}**" for i in moderate)
        recommendations.append(f"🟡 **Monitor closely:** {names} {'is' if len(moderate) == 1 else 'are'} approaching the reorder threshold.")

    cat_text = f" in **{category}**" if category != "All Categories" else ""
    reply = (
        f"Based on the current inventory analysis{cat_text}, "
        f"**{len(items)} product(s)** are below the reorder threshold of {threshold} units:\n\n"
        + "\n".join(lines)
        + "\n\n**Recommendations:**\n"
        + "\n".join(recommendations)
    )

    return {"reply": reply}


def _format_audit_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Format inventory audit results into clean business language."""
    summary: Dict = data["summary"]
    location: str = data["location"]
    items: List[Dict] = data["items"]
    include_valuation: bool = data["include_valuation"]
    warehouse: Dict = data["warehouse"]

    loc_text = f"**{location}**" if location != "All Locations" else "**all warehouse locations**"
    reply = f"Inventory audit complete for {loc_text}.\n\n"

    # Overall snapshot
    reply += "**Overall Snapshot:**\n"
    reply += f"• Unique products tracked: {summary.get('total_unique_products', 'N/A')}\n"
    reply += f"• Total units in stock: {summary.get('total_units_in_stock', 'N/A')}\n"
    reply += f"• Products needing attention: {summary.get('low_stock_alerts_count', 0)}\n"
    if include_valuation:
        reply += f"• Total inventory valuation: {summary.get('total_inventory_valuation', 'N/A')}\n"

    # Top assets by value
    if items:
        high_value = sorted(
            items,
            key=lambda x: x.get("unit_price", 0) * x.get("quantity", 0),
            reverse=True
        )[:3]
        reply += "\n**Top Assets by Value:**\n"
        for item in high_value:
            val = item.get("unit_price", 0) * item.get("quantity", 0)
            reply += (
                f"• **{item['name']}** — ₹{val:,.2f} "
                f"({item['quantity']} units @ ₹{item.get('unit_price', 0):,.2f} each)\n"
            )

        # Items needing attention
        low_items = [i for i in items if i["quantity"] <= i.get("min_stock_threshold", 10)]
        if low_items:
            reply += f"\n**Items Needing Attention ({len(low_items)}):**\n"
            for item in low_items[:5]:
                reply += f"• **{item['name']}** — {item['quantity']} units (Threshold: {item['min_stock_threshold']})\n"
            if len(low_items) > 5:
                reply += f"  ...and {len(low_items) - 5} more.\n"

    # Warehouse capacity from resource
    locations = warehouse.get("locations", [])
    if locations:
        reply += "\n**Warehouse Capacity Overview:**\n"
        for loc in locations:
            cap = loc.get("capacity_pct", 0)
            status = "✅ Healthy" if cap <= 60 else ("⚠️ High" if cap <= 80 else "🔴 Critical")
            reply += f"• {loc['name']}: {cap}% capacity — {status}\n"

    # Overall recommendation
    has_critical = summary.get("low_stock_alerts_count", 0) > 0
    reply += "\n**Recommendation:** " + (
        "Consider restocking flagged items to maintain operational readiness across all locations."
        if has_critical else
        "Inventory levels are healthy. No immediate action required."
    )

    return {"reply": reply}


def process_ai_assistant_query(user_message: str) -> Dict[str, Any]:
    """
    Process a natural language query through the MCP Prompt layer.

    Flow:
      User message → detect prompt intent (DISCOVERY)
                   → extract arguments
                   → invoke @mcp.prompt function (INVOCATION)
                   → execute MCP tools/resources guided by prompt
                   → format and return clean business response
    """
    msg = user_message.strip()

    # ----------------------------------------------------------

    matched_prompt = detect_prompt_intent(msg)

    if matched_prompt == "inventory_restock_assistant":
        args = _extract_restock_args(msg)

        prompt_instructions = PROMPT_REGISTRY["inventory_restock_assistant"]["fn"](
            category=args["category"] or "All Categories",
            min_threshold=args["min_threshold"]
        )

        execution_data = _execute_restock_prompt(
            prompt_instructions=prompt_instructions,
            category=args["category"],
            min_threshold=args["min_threshold"]
        )

        # ------------------------------------------------------
        # STEP 5: FORMAT CLEAN RESPONSE
        # ------------------------------------------------------
        return _format_restock_response(execution_data)

    if matched_prompt == "inventory_audit_prompt":
        args = _extract_audit_args(msg)

        # PROMPT INVOCATION: mcp.get_prompt("inventory_audit_prompt", args)
        prompt_instructions = PROMPT_REGISTRY["inventory_audit_prompt"]["fn"](
            location=args["location"] or "All Locations",
            include_valuation=args["include_valuation"]
        )

        # TOOL + RESOURCE EXECUTION guided by prompt instructions
        execution_data = _execute_audit_prompt(
            prompt_instructions=prompt_instructions,
            location=args["location"],
            include_valuation=args["include_valuation"]
        )

        return _format_audit_response(execution_data)

    msg_lower = msg.lower()

    # Summary / KPI queries → MCP Resource: inventory://summary
    if any(k in msg_lower for k in ["summary", "total value", "valuation", "stats", "kpi"]):
        resource_data = json.loads(get_inventory_summary_resource())
        return {
            "reply": (
                f"Here is the current inventory snapshot:\n"
                f"• Total Products: {resource_data.get('total_unique_products')}\n"
                f"• Total Units in Stock: {resource_data.get('total_units_in_stock')}\n"
                f"• Total Valuation: {resource_data.get('total_inventory_valuation')}\n"
                f"• Low Stock Alerts: {resource_data.get('low_stock_alerts_count')} product(s) need attention"
            )
        }

    # Warehouse / location queries → MCP Resource: inventory://warehouse-locations
    if any(k in msg_lower for k in ["warehouse", "location", "goa", "pune", "mumbai", "delhi", "capacity"]):
        wh_data = json.loads(get_warehouse_locations_resource())
        locs = wh_data.get("locations", [])
        summary_lines = "\n".join([
            f"• {loc['name']}: {loc['products']} products, {loc['units']} units — {loc['capacity_pct']}% capacity"
            for loc in locs
        ])
        return {
            "reply": f"Here is the regional warehouse overview:\n{summary_lines}"
        }

    # Product search → MCP Tool: search_inventory
    search_term = (
        msg_lower
        .replace("search", "").replace("find", "").replace("for", "")
        .replace("product", "").replace("item", "").replace("show", "")
        .strip()
    )
    if search_term and len(search_term) >= 2:
        search_res = json.loads(search_inventory(search_term))
        results = search_res.get("results", [])
        if results:
            item_lines = "\n".join([
                f"• **{i['name']}** (SKU: {i['sku']}) — {i['quantity']} units @ ₹{i['unit_price']:,.2f}"
                for i in results[:5]
            ])
            more = f"\n  ...and {len(results) - 5} more." if len(results) > 5 else ""
            return {
                "reply": f"Found **{len(results)} product(s)** matching your search:\n{item_lines}{more}"
            }
        return {
            "reply": f"No products found matching '{search_term}'. Try a different keyword or check the Products tab."
        }

    # Default fallback
    all_details = json.loads(get_inventory_details())
    items_count = all_details.get("count", 0)
    return {
        "reply": (
            f"I'm currently tracking **{items_count} products** across your warehouses. "
            f"Here are some things you can ask me:\n"
            f"• \"Which products need restocking?\"\n"
            f"• \"Generate an inventory audit\"\n"
            f"• \"Show warehouse capacity\"\n"
            f"• \"Search for [product name]\""
        )
    }


if __name__ == "__main__":
    init_db()
    mcp.run()
