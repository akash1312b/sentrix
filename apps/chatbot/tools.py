"""
Tool ("function calling") definitions for the AI assistant.

Design principle: the AI never invents numbers. Every question about
stock levels, sales, or suppliers is answered by calling a real function
against the database — the same service functions the REST API uses
(see apps.inventory.services / apps.suppliers.services). The LLM's job
is to understand intent, pick the right tool, and phrase the answer —
never to calculate or recall inventory facts on its own.
"""
from apps.inventory.models import Product, StockTransaction
from apps.inventory.serializers import ProductSerializer
from apps.inventory.services import (
    InsufficientStockError, estimate_days_until_stockout,
    get_low_stock_products, record_stock_transaction,
)
from apps.suppliers.models import PurchaseOrder, PurchaseOrderItem

# ---------------------------------------------------------------------------
# JSON schemas Claude uses to decide when/how to call each tool.
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "name": "get_stock_level",
        "description": "Look up the current stock quantity for a product by name or SKU.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Product name or SKU, may be partial."},
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "list_low_stock_products",
        "description": "List every product currently at or below its reorder threshold.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "adjust_stock",
        "description": (
            "Record a stock change for a product — a sale, a purchase received, "
            "a return, damage/wastage, or a manual correction. Always confirm "
            "the product and quantity with the user before calling this for "
            "anything destructive (e.g. large stock removals)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "transaction_type": {
                    "type": "string",
                    "enum": [c[0] for c in StockTransaction.TransactionType.choices],
                },
                "quantity": {
                    "type": "integer",
                    "description": "Always a positive number; direction comes from transaction_type.",
                },
                "note": {"type": "string"},
            },
            "required": ["product_name", "transaction_type", "quantity"],
        },
    },
    {
        "name": "estimate_stockout",
        "description": "Estimate how many days until a product runs out, based on recent sales velocity.",
        "input_schema": {
            "type": "object",
            "properties": {"product_name": {"type": "string"}},
            "required": ["product_name"],
        },
    },
    {
        "name": "create_purchase_order",
        "description": "Draft a new purchase order for a supplier with one product line item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "quantity": {"type": "integer"},
            },
            "required": ["product_name", "quantity"],
        },
    },
]


def _find_product(shop, product_name: str) -> Product | None:
    return (
        Product.objects.filter(shop=shop, name__icontains=product_name).first()
        or Product.objects.filter(shop=shop, sku__icontains=product_name).first()
    )


def execute_tool(*, shop, user, tool_name: str, tool_input: dict) -> dict:
    """Dispatch a tool call to the matching handler. Every branch returns
    a small JSON-serializable dict that gets fed back to Claude as the
    tool_result — never a raw model instance."""

    if tool_name == "get_stock_level":
        product = _find_product(shop, tool_input["product_name"])
        if not product:
            return {"found": False}
        return {
            "found": True,
            "product_name": product.name,
            "sku": product.sku,
            "quantity": product.quantity,
            "reorder_threshold": product.effective_reorder_threshold,
            "is_low_stock": product.is_low_stock,
        }

    if tool_name == "list_low_stock_products":
        products = get_low_stock_products(shop)
        return {
            "count": len(products),
            "products": [
                {"name": p.name, "sku": p.sku, "quantity": p.quantity,
                 "reorder_threshold": p.effective_reorder_threshold}
                for p in products
            ],
        }

    if tool_name == "adjust_stock":
        product = _find_product(shop, tool_input["product_name"])
        if not product:
            return {"success": False, "error": f"No product matching '{tool_input['product_name']}'."}
        signed_quantity = tool_input["quantity"]
        if tool_input["transaction_type"] in (
            StockTransaction.TransactionType.SALE_OUT,
            StockTransaction.TransactionType.DAMAGE_OUT,
        ):
            signed_quantity = -abs(signed_quantity)
        else:
            signed_quantity = abs(signed_quantity)
        try:
            txn = record_stock_transaction(
                product=product, transaction_type=tool_input["transaction_type"],
                quantity=signed_quantity, note=tool_input.get("note", "via AI assistant"),
                user=user,
            )
        except InsufficientStockError as exc:
            return {"success": False, "error": str(exc)}
        # record_stock_transaction locks/updates its own row copy internally,
        # so this in-memory `product` is stale — refresh before reporting.
        product.refresh_from_db()
        return {
            "success": True, "product_name": product.name,
            "new_quantity": product.quantity, "transaction_id": str(txn.id),
        }

    if tool_name == "estimate_stockout":
        product = _find_product(shop, tool_input["product_name"])
        if not product:
            return {"found": False}
        days = estimate_days_until_stockout(product)
        return {"found": True, "product_name": product.name, "days_until_stockout": days}

    if tool_name == "create_purchase_order":
        product = _find_product(shop, tool_input["product_name"])
        if not product or not product.supplier_id:
            return {"success": False, "error": "Product not found or has no supplier configured."}
        po = PurchaseOrder.objects.create(
            shop=shop, supplier=product.supplier, status=PurchaseOrder.Status.DRAFT,
            notes="Created via AI assistant.",
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po, product=product,
            quantity=tool_input["quantity"], unit_cost=product.cost_price,
        )
        return {"success": True, "purchase_order_id": str(po.id), "status": po.status}

    return {"error": f"Unknown tool '{tool_name}'."}
