"""
Gemini AI Service for Inventory Management System
===================================================

This module is the ONLY place where Google Gemini code lives.
Everything else in the project remains unchanged.

HOW TO CONFIGURE:
    Set the GEMINI_API_KEY environment variable before starting the server.

    Windows PowerShell:
        $env:GEMINI_API_KEY = "your-api-key-here"

    Windows CMD:
        set GEMINI_API_KEY=your-api-key-here

    Linux / macOS:
        export GEMINI_API_KEY="your-api-key-here"

    Get a free API key at: https://aistudio.google.com/apikey

HOW IT WORKS (two-step Gemini pipeline):
    Step 1 — DECISION:  Gemini reads the user message and decides which MCP
                        capability (resource / prompt / tool) to invoke.
    Step 2 — EXECUTE:   Python executes that MCP capability using the existing
                        server.py functions (no logic is duplicated here).
    Step 3 — RESPOND:   Gemini receives the raw MCP data and generates a clean,
                        natural-language business response.
    FALLBACK:           If Gemini is unavailable, returns None so the caller
                        falls back to the existing rule-based assistant.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_service_instance: Optional["GeminiService"] = None


def get_gemini_service() -> "GeminiService":
    """Return the application-wide singleton GeminiService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GeminiService()
    return _service_instance


# ---------------------------------------------------------------------------
# GeminiService
# ---------------------------------------------------------------------------

class GeminiService:
    """
    Wraps the Google Gemini API and connects it to the project's MCP layer.

    The assistant now operates as a real AI agent:
      User message
        → Gemini decides which MCP capability to invoke  (DISCOVERY + DECISION)
        → Python executes that MCP tool / resource / prompt  (EXECUTION)
        → Gemini reasons over the returned data             (REASONING)
        → Clean natural-language reply sent to the user     (RESPONSE)

    If GEMINI_API_KEY is not set, or if the API call fails, process_query()
    returns None and the caller falls back to the rule-based assistant.
    """

    # Default model — override with GEMINI_MODEL env var if needed
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self):
        self.api_key  = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL).strip()
        self.model    = None
        self.available = False
        self._initialize()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _initialize(self):
        """
        Attempt to connect to the Gemini API.
        Fails silently so the application always starts successfully.
        """
        if not self.api_key:
            logger.warning(
                "[GeminiService] GEMINI_API_KEY is not set. "
                "The AI assistant will use the rule-based fallback. "
                "Set the environment variable to enable Gemini."
            )
            return

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            self.available = True
            logger.info(f"[GeminiService] Ready — model: '{self.model_name}'")
        except ImportError:
            logger.error(
                "[GeminiService] google-genai package is not installed. "
                "Run:  pip install google-genai"
            )
        except Exception as exc:
            logger.error(f"[GeminiService] Initialization failed: {exc}")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def process_query(self, user_message: str, server_module) -> Optional[Dict[str, Any]]:
        """
        Main entry point called by the web app's /api/ai/chat endpoint.

        Returns:
            dict  with a 'reply' key on success.
            None  if Gemini is unavailable → caller uses rule-based fallback.
        """
        if not self.available:
            return None  # Signal: use the rule-based fallback

        try:
            return self._run_pipeline(user_message, server_module)

        except Exception as exc:
            msg = str(exc).lower()
            # Quota / rate-limit → friendly message, do NOT crash or show traceback
            if any(k in msg for k in ["quota", "429", "resource_exhausted", "rate limit", "too many"]):
                logger.warning(f"[GeminiService] Rate limit: {exc}")
                return {
                    "reply": (
                        "I'm temporarily unavailable due to API usage limits. "
                        "Please try again in a moment."
                    )
                }
            # Any other error → fall back to rule-based assistant
            logger.error(f"[GeminiService] Unexpected error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(self, user_message: str, server_module) -> Dict[str, Any]:
        """Three-step Gemini + MCP pipeline."""

        # Step 1 — Ask Gemini which MCP capability to invoke
        capabilities_text = self._build_capabilities_description(server_module)
        decision          = self._get_mcp_decision(user_message, capabilities_text)

        # Step 2 — Execute that MCP capability using existing server functions
        mcp_result = self._execute_mcp_capability(decision, server_module)

        # Step 3 — Ask Gemini to turn the raw MCP data into a natural response
        reply = self._generate_natural_response(user_message, mcp_result)
        return {"reply": reply}

    # ------------------------------------------------------------------
    # Step 1 helpers
    # ------------------------------------------------------------------

    def _build_capabilities_description(self, server_module) -> str:
        """
        PROMPT DISCOVERY:
        Builds a human-readable description of all available MCP capabilities.

        Prompts are discovered dynamically from PROMPT_REGISTRY so that adding
        new prompts to server.py is automatically reflected here — no hardcoding.
        """
        # Discover prompts from PROMPT_REGISTRY (single source of truth)
        prompt_lines = []
        for name, meta in server_module.PROMPT_REGISTRY.items():
            arg_names = list(meta["args"].keys())
            prompt_lines.append(
                f"  - {name}({', '.join(arg_names)}) — {meta['description']}"
            )

        return f"""
=== MCP RESOURCES  (read-only snapshots — prefer for quick stats) ===
  - inventory://summary              — KPIs: product count, total units, total valuation, low-stock count
  - inventory://warehouse-locations  — Warehouse list with product counts and capacity %

=== MCP PROMPTS  (prefer for analysis / restock / audit tasks) ===
{chr(10).join(prompt_lines)}

=== MCP TOOLS  (use for search, CRUD, targeted retrieval) ===
  - search_inventory(query)                              — Full-text product search
  - get_inventory_details(category?, low_stock_only?)    — List products with optional filters
  - add_inventory_item(sku, name, category, unit_price, quantity?, location?, min_stock_threshold?)
  - update_inventory_item(item_id, quantity_change?, new_quantity?, unit_price?, location?)
  - delete_inventory_item(item_id, confirm)              — Permanently delete a product
"""

    def _get_mcp_decision(self, user_message: str, capabilities_text: str) -> Dict[str, Any]:
        """
        STEP 1 — First Gemini call.
        Gemini reads the user message and returns a JSON decision specifying
        which MCP capability (type + name + args) to invoke.
        """
        prompt = f"""You are an MCP orchestrator for an Inventory Management System.
Your only job is to read a user message and return a JSON object choosing which MCP capability to invoke.

Available MCP Capabilities:
{capabilities_text}

User message: "{user_message}"

Selection rules (in priority order):
1. MCP PROMPTS   → use for restock analysis, audits, health checks, reports
2. MCP RESOURCES → use for quick KPIs, summaries, warehouse overview
3. MCP TOOLS     → use for searching products, CRUD operations, targeted lookups

Respond with ONLY a valid JSON object. No markdown. No explanation. Nothing else.

Format:
{{
  "type": "prompt" | "resource" | "tool",
  "name": "<exact capability name from the list above>",
  "args": {{ <key-value pairs or empty object {{}} if no args needed> }}
}}

Examples:
- "Which products need restocking?"              → {{"type":"prompt","name":"inventory_restock_assistant","args":{{"category":"All Categories","min_threshold":10}}}}
- "Inventory summary" or "show KPIs"             → {{"type":"resource","name":"inventory://summary","args":{{}}}}
- "Warehouse capacity" or "warehouse overview"   → {{"type":"resource","name":"inventory://warehouse-locations","args":{{}}}}
- "Inventory audit" or "inventory health"        → {{"type":"prompt","name":"inventory_audit_prompt","args":{{"location":"All Locations","include_valuation":true}}}}
- "Audit Goa warehouse"                          → {{"type":"prompt","name":"inventory_audit_prompt","args":{{"location":"Goa Warehouse","include_valuation":true}}}}
- "Search for keyboard"                          → {{"type":"tool","name":"search_inventory","args":{{"query":"keyboard"}}}}
- "Show low stock electronics"                   → {{"type":"tool","name":"get_inventory_details","args":{{"category":"Electronics","low_stock_only":true}}}}
"""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        raw = response.text.strip()

        # Strip markdown fences if Gemini wrapped the JSON in code blocks
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[GeminiService] Could not parse decision JSON: {raw!r}")
            return {"type": "resource", "name": "inventory://summary", "args": {}}

    # ------------------------------------------------------------------
    # Step 2 helpers
    # ------------------------------------------------------------------

    def _execute_mcp_capability(self, decision: Dict, server_module) -> Dict[str, Any]:
        """
        STEP 2 — Execute the MCP capability Gemini selected.

        Calls existing server.py functions directly — no business logic is
        duplicated here. This is the real MCP invocation layer.
        """
        cap_type = decision.get("type", "resource")
        name     = decision.get("name", "inventory://summary")
        args     = decision.get("args", {})

        try:
            # ── MCP RESOURCE ──────────────────────────────────────────────
            if cap_type == "resource":
                if name == "inventory://summary":
                    data = json.loads(server_module.get_inventory_summary_resource())
                    return {"type": "resource", "name": name, "data": data}

                if name == "inventory://warehouse-locations":
                    data = json.loads(server_module.get_warehouse_locations_resource())
                    return {"type": "resource", "name": name, "data": data}

            # ── MCP PROMPT ────────────────────────────────────────────────
            elif cap_type == "prompt":
                if name in server_module.PROMPT_REGISTRY:
                    meta      = server_module.PROMPT_REGISTRY[name]
                    prompt_fn = meta["fn"]

                    # Only pass args the prompt actually declares
                    valid_args = {k: v for k, v in args.items() if k in meta["args"]}

                    # Invoke the @mcp.prompt registered function
                    prompt_template = prompt_fn(**valid_args)

                    # Execute underlying MCP tools as guided by the prompt template
                    if name == "inventory_restock_assistant":
                        return self._exec_restock_prompt(prompt_template, args, server_module)

                    if name == "inventory_audit_prompt":
                        return self._exec_audit_prompt(prompt_template, args, server_module)

            # ── MCP TOOL ──────────────────────────────────────────────────
            elif cap_type == "tool":
                return self._exec_tool(name, args, server_module)

        except Exception as exc:
            logger.error(
                f"[GeminiService] Error executing MCP capability "
                f"type='{cap_type}' name='{name}': {exc}"
            )

        # Safe fallback — always return something meaningful
        data = json.loads(server_module.get_inventory_summary_resource())
        return {"type": "resource", "name": "inventory://summary", "data": data}

    def _exec_restock_prompt(self, prompt_template: str, args: Dict, server_module) -> Dict:
        """Execute inventory_restock_assistant: calls get_inventory_details MCP tool."""
        category  = args.get("category")
        threshold = int(args.get("min_threshold", 10))
        use_cat   = category if category not in (None, "", "All Categories") else None

        raw   = json.loads(server_module.get_inventory_details(category=use_cat, low_stock_only=True))
        items = [i for i in raw.get("items", []) if i["quantity"] <= threshold]

        return {
            "type": "prompt",
            "name": "inventory_restock_assistant",
            "prompt_template": prompt_template,
            "data": {
                "items": items,
                "threshold": threshold,
                "category": category or "All Categories",
            },
        }

    def _exec_audit_prompt(self, prompt_template: str, args: Dict, server_module) -> Dict:
        """
        Execute inventory_audit_prompt:
        calls get_inventory_summary_resource (MCP Resource),
        search_inventory or get_inventory_details (MCP Tool),
        and get_warehouse_locations_resource (MCP Resource).
        """
        location    = args.get("location")
        include_val = bool(args.get("include_valuation", True))

        # MCP Resource: summary KPIs
        summary = json.loads(server_module.get_inventory_summary_resource())

        # MCP Tool: location-specific items
        if location and location not in ("", "All Locations"):
            raw   = json.loads(server_module.search_inventory(location))
            items = raw.get("results", [])
        else:
            raw   = json.loads(server_module.get_inventory_details())
            items = raw.get("items", [])

        # MCP Resource: warehouse capacity data
        warehouse = json.loads(server_module.get_warehouse_locations_resource())

        return {
            "type": "prompt",
            "name": "inventory_audit_prompt",
            "prompt_template": prompt_template,
            "data": {
                "summary":           summary,
                "items":             items,
                "warehouse":         warehouse,
                "include_valuation": include_val,
                "location":          location or "All Locations",
            },
        }

    def _exec_tool(self, name: str, args: Dict, server_module) -> Dict:
        """Execute an MCP Tool and return the result."""
        if name == "search_inventory":
            data = json.loads(server_module.search_inventory(args.get("query", "")))
            return {"type": "tool", "name": name, "data": data}

        if name == "get_inventory_details":
            data = json.loads(server_module.get_inventory_details(
                item_id      = args.get("item_id"),
                sku          = args.get("sku"),
                category     = args.get("category"),
                low_stock_only = bool(args.get("low_stock_only", False)),
            ))
            return {"type": "tool", "name": name, "data": data}

        if name == "add_inventory_item":
            # Only pass recognised kwargs to avoid TypeError
            allowed = {"sku", "name", "category", "unit_price", "quantity",
                       "location", "min_stock_threshold", "description"}
            safe_args = {k: v for k, v in args.items() if k in allowed}
            data = json.loads(server_module.add_inventory_item(**safe_args))
            return {"type": "tool", "name": name, "data": data}

        if name == "update_inventory_item":
            allowed = {"item_id", "quantity_change", "new_quantity", "unit_price",
                       "location", "min_stock_threshold", "description"}
            safe_args = {k: v for k, v in args.items() if k in allowed}
            data = json.loads(server_module.update_inventory_item(**safe_args))
            return {"type": "tool", "name": name, "data": data}

        if name == "delete_inventory_item":
            data = json.loads(server_module.delete_inventory_item(
                item_id = args.get("item_id"),
                confirm = bool(args.get("confirm", False)),
            ))
            return {"type": "tool", "name": name, "data": data}

        # Unknown tool name — return a graceful acknowledgement
        logger.warning(f"[GeminiService] Unknown tool name: '{name}'")
        return {"type": "tool", "name": name, "data": {"message": f"Tool '{name}' is not yet mapped."}}

    # ------------------------------------------------------------------
    # Step 3 helpers
    # ------------------------------------------------------------------

    def _generate_natural_response(self, user_message: str, mcp_result: Dict) -> str:
        """
        STEP 3 — Second Gemini call.
        Gemini receives the raw MCP data and generates a clean, professional,
        natural-language response. No MCP internals are ever shown to the user.
        """
        prompt = f"""You are a helpful Smart Inventory AI Assistant for a professional Inventory Management System.
The system uses Indian Rupees (₹) as currency.

The user asked: "{user_message}"

The following data was retrieved from the inventory system:
{json.dumps(mcp_result.get("data", {}), indent=2, ensure_ascii=False)}

Write a clear, professional, business-friendly response:
• Use plain English — not JSON or technical jargon
• Format currency as ₹ with Indian comma notation  (e.g. ₹1,23,456.00)
• Use bullet points or numbered lists where helpful
• Highlight critical or urgent items clearly
• Include actionable recommendations where relevant
• Be concise but complete
• Do NOT mention: API names, tool names, prompt names, MCP, JSON, protocol details, or any internal implementation
• Write as a knowledgeable inventory manager speaking to a colleague
"""
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        return response.text.strip()
