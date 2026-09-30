from django.db import transaction

from apps.inventory.models import Product
from apps.inventory.services import get_low_stock_products, record_stock_transaction
from apps.inventory.models import StockTransaction

from .models import PurchaseOrder, PurchaseOrderItem


@transaction.atomic
def auto_draft_purchase_orders_for_shop(shop) -> list[PurchaseOrder]:
    """
    Group every low-stock product by its supplier and create one DRAFT
    purchase order per supplier, pre-filled with the product's configured
    `reorder_quantity` at its last known `cost_price`.

    Drafts require explicit owner approval before being marked ORDERED —
    automation should accelerate the owner's decision, not remove it.
    """
    low_stock_products = [p for p in get_low_stock_products(shop) if p.supplier_id]

    by_supplier: dict[int, list[Product]] = {}
    for product in low_stock_products:
        by_supplier.setdefault(product.supplier_id, []).append(product)

    created_orders = []
    for supplier_id, products in by_supplier.items():
        existing_draft = PurchaseOrder.objects.filter(
            shop=shop, supplier_id=supplier_id, status=PurchaseOrder.Status.DRAFT,
            auto_generated=True,
        ).first()
        if existing_draft:
            continue  # don't spam duplicate drafts every day

        po = PurchaseOrder.objects.create(
            shop=shop, supplier_id=supplier_id,
            status=PurchaseOrder.Status.DRAFT, auto_generated=True,
            notes="Auto-generated from low-stock levels.",
        )
        for product in products:
            PurchaseOrderItem.objects.create(
                purchase_order=po, product=product,
                quantity=product.reorder_quantity, unit_cost=product.cost_price,
            )
        created_orders.append(po)

    return created_orders


@transaction.atomic
def mark_purchase_order_received(purchase_order: PurchaseOrder, user) -> PurchaseOrder:
    """Receiving a PO both updates its status AND books stock-in
    transactions for every line item, keeping quantity always accurate."""
    for item in purchase_order.items.select_related("product"):
        record_stock_transaction(
            product=item.product,
            transaction_type=StockTransaction.TransactionType.PURCHASE_IN,
            quantity=item.quantity,
            unit_price=item.unit_cost,
            note=f"Received via PO-{str(purchase_order.id)[:8]}",
            user=user,
        )
    purchase_order.status = PurchaseOrder.Status.RECEIVED
    purchase_order.save(update_fields=["status", "updated_at"])
    return purchase_order
