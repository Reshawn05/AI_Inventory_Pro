from typing import Optional
from pydantic import BaseModel, Field

class InventoryItem(BaseModel):
    """Represents a single product item in the inventory system."""
    id: int = Field(..., description="Unique product ID integer")
    sku: str = Field(..., description="Stock Keeping Unit identifier code (e.g. ELEC-1001)")
    name: str = Field(..., description="Product title or name")
    category: str = Field(..., description="Product category (e.g., Electronics, Stationery, Hardware)")
    quantity: int = Field(..., description="Current available stock quantity")
    unit_price: float = Field(..., description="Unit price per item in INR (₹)")
    location: str = Field(..., description="Warehouse or storage location (e.g. Aisle A1, Shelf 2)")
    min_stock_threshold: int = Field(..., description="Minimum stock level before triggering reorder alert")
    description: Optional[str] = Field(default="", description="Detailed product description")
    created_at: str = Field(..., description="ISO timestamp of record creation")
    updated_at: str = Field(..., description="ISO timestamp of last update")

class ItemCreate(BaseModel):
    """Input payload for adding a new item to inventory."""
    sku: str = Field(..., description="Unique Stock Keeping Unit (e.g. LAPTOP-PRO-15)")
    name: str = Field(..., description="Product name")
    category: str = Field(..., description="Product category")
    quantity: int = Field(default=0, ge=0, description="Initial stock quantity (>= 0)")
    unit_price: float = Field(..., gt=0, description="Price per unit in INR ₹ (> 0)")
    location: str = Field(default="Main Warehouse", description="Storage location")
    min_stock_threshold: int = Field(default=10, ge=0, description="Reorder alert threshold")
    description: Optional[str] = Field(default="", description="Product description")

class ItemUpdate(BaseModel):
    """Input payload for updating inventory item fields."""
    name: Optional[str] = Field(default=None, description="New product name")
    category: Optional[str] = Field(default=None, description="New category")
    quantity: Optional[int] = Field(default=None, ge=0, description="New absolute stock quantity")
    unit_price: Optional[float] = Field(default=None, gt=0, description="New unit price in INR ₹")
    location: Optional[str] = Field(default=None, description="New storage location")
    min_stock_threshold: Optional[int] = Field(default=None, ge=0, description="New threshold level")
    description: Optional[str] = Field(default=None, description="New product description")

class InventorySummary(BaseModel):
    """Summary metrics of the inventory database."""
    total_items: int
    total_quantity: int
    total_inventory_value: float
    low_stock_items_count: int
    categories_count: int
