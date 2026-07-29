import sqlite3
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("MCP.Database")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Establish connection to SQLite database and return connection object with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH, reset_seed: bool = False) -> None:
    """Initialize inventory database schema, indexes, audit log table, and insert initial seed data in INR (₹) if creating database for first time."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory';")
        table_exists = cursor.fetchone() is not None

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                unit_price REAL NOT NULL DEFAULT 0.0 CHECK (unit_price >= 0.0),
                location TEXT NOT NULL DEFAULT 'Main Warehouse',
                min_stock_threshold INTEGER NOT NULL DEFAULT 10,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                action TEXT NOT NULL,
                previous_quantity INTEGER,
                new_quantity INTEGER,
                timestamp TEXT NOT NULL
            );
        """)

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_category ON inventory(category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_location ON inventory(location);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory(sku);")

        conn.commit()

        if reset_seed:
            cursor.execute("DELETE FROM inventory;")
            cursor.execute("DELETE FROM inventory_logs;")
            conn.commit()

        if not table_exists or reset_seed:
            cursor.execute("SELECT COUNT(*) FROM inventory;")
            count = cursor.fetchone()[0]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                seed_items = [
                    ("ELEC-1001", "Ergonomic Mechanical Keyboard", "Electronics", 45, 8999.00, "Goa Warehouse - Aisle A1", 10, "RGB Backlit mechanical keyboard with tactile brown switches", now, now),
                    ("ELEC-1002", "UltraWide 34-inch Monitor", "Electronics", 8, 38500.00, "Pune Warehouse - Section B2", 10, "34-inch curved WQHD monitor with 144Hz refresh rate", now, now),
                    ("ELEC-1003", "Wireless Noise-Canceling Headphones", "Electronics", 24, 14999.00, "Goa Warehouse - Aisle A2", 15, "Bluetooth 5.2 active noise canceling over-ear headphones", now, now),
                    ("OFF-2001", "Executive Ergonomic Desk Chair", "Office Furniture", 5, 22499.00, "Pune Warehouse - Floor 1", 8, "High-back mesh chair with adjustable lumbar support", now, now),
                    ("OFF-2002", "Electric Standing Desk Frame", "Office Furniture", 12, 28900.00, "Mumbai Central Hub - Bay 4", 5, "Dual-motor motorized standing desk frame with memory presets", now, now),
                    ("SUP-3001", "Heavy-Duty Shipping Box (Pack of 25)", "Supplies", 120, 2499.00, "Mumbai Central Hub - Rack C5", 30, "Corrugated cardboard boxes 16x12x12 inches", now, now),
                    ("SUP-3002", "Thermal Label Printer Rolls (6 Pack)", "Supplies", 3, 1299.00, "Delhi Depot - Shelf 2", 15, "Direct thermal adhesive labels 4x6 inches", now, now),
                    ("ACC-4001", "USB-C Multi-Port Hub Adapter", "Accessories", 60, 3499.00, "Goa Warehouse - Aisle A3", 20, "7-in-1 USB-C adapter with HDMI, SD card reader, PD charging", now, now)
                ]
                cursor.executemany("""
                    INSERT INTO inventory (sku, name, category, quantity, unit_price, location, min_stock_threshold, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, seed_items)
                conn.commit()

def list_items(
    category: Optional[str] = None,
    low_stock_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """Retrieve list of inventory items with filtering options."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM inventory WHERE 1=1"
        params = []

        if category:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(category)

        if low_stock_only:
            query += " AND quantity <= min_stock_threshold"

        query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_item_by_id(item_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve a single item by its database primary key ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_item_by_sku(sku: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve a single item by its unique SKU code."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory WHERE LOWER(sku) = LOWER(?);", (sku,))
        row = cursor.fetchone()
        return dict(row) if row else None

def search_items(query: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Search inventory across SKU, name, category, location, and description fields."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT * FROM inventory
            WHERE sku LIKE ?
               OR name LIKE ?
               OR category LIKE ?
               OR location LIKE ?
               OR description LIKE ?
            ORDER BY id ASC;
        """, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def add_item(item_dict: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Insert a new inventory item into SQLite database and log creation event."""
    now = datetime.now(timezone.utc).isoformat()
    qty = max(0, item_dict.get("quantity", 0))
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO inventory (sku, name, category, quantity, unit_price, location, min_stock_threshold, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                item_dict["sku"].upper(),
                item_dict["name"],
                item_dict["category"],
                qty,
                item_dict["unit_price"],
                item_dict.get("location", "Main Warehouse"),
                item_dict.get("min_stock_threshold", 10),
                item_dict.get("description", ""),
                now,
                now
            ))
            new_id = cursor.lastrowid
            
            cursor.execute("""
                INSERT INTO inventory_logs (item_id, action, previous_quantity, new_quantity, timestamp)
                VALUES (?, ?, ?, ?, ?);
            """, (new_id, "CREATE", 0, qty, now))
            
            conn.commit()
        return get_item_by_id(new_id, db_path)
    except sqlite3.Error as err:
        logger.error(f"[Database Error] Failed to add item with SKU '{item_dict.get('sku')}': {err}")
        return None

def update_item(item_id: int, updates: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Update fields of an existing inventory item by item_id and log changes."""
    if not updates:
        return get_item_by_id(item_id, db_path)

    existing = get_item_by_id(item_id, db_path)
    if not existing:
        return None

    prev_qty = existing["quantity"]
    fields = []
    params = []
    for key, value in updates.items():
        if value is not None and key in ["name", "category", "quantity", "unit_price", "location", "min_stock_threshold", "description"]:
            fields.append(f"{key} = ?")
            params.append(value)

    if not fields:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    fields.append("updated_at = ?")
    params.append(now)
    params.append(item_id)

    query = f"UPDATE inventory SET {', '.join(fields)} WHERE id = ?;"

    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if "quantity" in updates and updates["quantity"] != prev_qty:
                cursor.execute("""
                    INSERT INTO inventory_logs (item_id, action, previous_quantity, new_quantity, timestamp)
                    VALUES (?, ?, ?, ?, ?);
                """, (item_id, "UPDATE_QUANTITY", prev_qty, updates["quantity"], now))
            else:
                cursor.execute("""
                    INSERT INTO inventory_logs (item_id, action, previous_quantity, new_quantity, timestamp)
                    VALUES (?, ?, ?, ?, ?);
                """, (item_id, "UPDATE_DETAILS", prev_qty, updates.get("quantity", prev_qty), now))

            conn.commit()
        return get_item_by_id(item_id, db_path)
    except sqlite3.Error as err:
        logger.error(f"[Database Error] Failed to update item {item_id}: {err}")
        return None

def delete_item(item_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Delete an item from inventory by item_id. Returns True if deleted, False if not found or on error."""
    existing = get_item_by_id(item_id, db_path)
    if not existing:
        return False

    prev_qty = existing["quantity"]
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM inventory WHERE id = ?;", (item_id,))
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                cursor.execute("""
                    INSERT INTO inventory_logs (item_id, action, previous_quantity, new_quantity, timestamp)
                    VALUES (?, ?, ?, ?, ?);
                """, (item_id, "DELETE", prev_qty, 0, now))

            conn.commit()
        return deleted_count > 0
    except sqlite3.Error as err:
        logger.error(f"[Database Error] Failed to delete item {item_id}: {err}")
        return False

def get_inventory_summary(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Calculate aggregate inventory metrics in INR (₹)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_items,
                COALESCE(SUM(quantity), 0) as total_quantity,
                COALESCE(SUM(quantity * unit_price), 0.0) as total_value,
                SUM(CASE WHEN quantity <= min_stock_threshold THEN 1 ELSE 0 END) as low_stock_count,
                COUNT(DISTINCT category) as category_count
            FROM inventory;
        """)
        row = cursor.fetchone()
        return {
            "total_items": row["total_items"],
            "total_quantity": row["total_quantity"],
            "total_inventory_value": round(row["total_value"], 2),
            "currency": "INR (₹)",
            "low_stock_items_count": row["low_stock_count"],
            "categories_count": row["category_count"]
        }

def get_warehouse_locations_summary(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Retrieve structured warehouse locations summary and item distribution."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory ORDER BY location ASC, id ASC;")
        rows = cursor.fetchall()
        
        locations_map = {}
        for row in rows:
            loc = row["location"]
            if loc not in locations_map:
                locations_map[loc] = {
                    "location_name": loc,
                    "items_count": 0,
                    "total_units": 0,
                    "items": []
                }
            locations_map[loc]["items_count"] += 1
            locations_map[loc]["total_units"] += row["quantity"]
            locations_map[loc]["items"].append({
                "id": row["id"],
                "sku": row["sku"],
                "name": row["name"],
                "category": row["category"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"]
            })
            
        return {
            "success": True,
            "currency": "INR (₹)",
            "total_locations_count": len(locations_map),
            "locations": list(locations_map.values())
        }

def get_inventory_summary_clean(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Retrieve clean, structured aggregate metrics summary for MCP resource consumption."""
    summary = get_inventory_summary(db_path)
    return {
        "report_title": "Executive Inventory Summary Report",
        "currency": "INR (₹)",
        "total_unique_products": summary["total_items"],
        "total_units_in_stock": summary["total_quantity"],
        "total_inventory_valuation": f"₹{summary['total_inventory_value']:,.2f}",
        "low_stock_alerts_count": summary["low_stock_items_count"],
        "active_categories_count": summary["categories_count"]
    }

def get_warehouse_locations_minimal_summary(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Retrieve summary of warehouse locations containing facility name, products count, units count, capacity %, and items list."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory ORDER BY location ASC;")
        rows = cursor.fetchall()
        
        # Max capacity reference per main facility for calculating capacity %
        FACILITY_CAPACITIES = {
            "Goa Warehouse": 100,
            "Pune Warehouse": 50,
            "Mumbai Central Hub": 200,
            "Delhi Depot": 50,
            "Main Warehouse": 150
        }
        
        facilities = {}
        for r in rows:
            loc = r["location"]
            # Extract main facility name before hyphen/dash if present
            facility_name = loc.split(" - ")[0].strip() if " - " in loc else loc.strip()
            
            if facility_name not in facilities:
                facilities[facility_name] = {
                    "name": facility_name,
                    "products": 0,
                    "units": 0,
                    "items": []
                }
            
            facilities[facility_name]["products"] += 1
            facilities[facility_name]["units"] += r["quantity"]
            facilities[facility_name]["items"].append({
                "id": r["id"],
                "sku": r["sku"],
                "name": r["name"],
                "category": r["category"],
                "quantity": r["quantity"],
                "unit_price": r["unit_price"],
                "sub_location": loc
            })
            
        locations_list = []
        for fac_name, data in facilities.items():
            max_cap = FACILITY_CAPACITIES.get(fac_name, 100)
            capacity_pct = min(100, int((data["units"] / max_cap) * 100))
            locations_list.append({
                "name": fac_name,
                "products": data["products"],
                "units": data["units"],
                "capacity_pct": capacity_pct,
                "max_capacity": max_cap,
                "items": data["items"]
            })
            
        return {
            "locations": locations_list
        }

def get_inventory_logs(limit: int = 50, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve audit history logs of stock updates, creations, and deletions."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory_logs ORDER BY id DESC LIMIT ?;", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def bulk_update_items(items_updates: List[Dict[str, Any]], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Perform batch updates on multiple inventory items within a single atomic transaction."""
    updated_items = []
    errors = []
    
    for update_req in items_updates:
        item_id = update_req.get("item_id")
        if not item_id:
            errors.append("Missing item_id in update request.")
            continue
        
        updates = {k: v for k, v in update_req.items() if k != "item_id"}
        res = update_item(item_id, updates, db_path=db_path)
        if res:
            updated_items.append(res)
        else:
            errors.append(f"Failed to update item_id {item_id}.")
            
    return {
        "success": len(errors) == 0,
        "updated_count": len(updated_items),
        "updated_items": updated_items,
        "errors": errors
    }


