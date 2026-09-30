import pytest

from apps.suppliers.models import PurchaseOrder
from apps.suppliers.services import auto_draft_purchase_orders_for_shop, mark_purchase_order_received


@pytest.mark.django_db
def test_auto_draft_creates_po_for_low_stock_product(shop, product, owner_user):
    from apps.inventory.services import record_stock_transaction
    from apps.inventory.models import StockTransaction

    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-16, user=owner_user,
    )
    orders = auto_draft_purchase_orders_for_shop(shop)
    assert len(orders) == 1
    po = orders[0]
    assert po.status == PurchaseOrder.Status.DRAFT
    assert po.items.count() == 1
    assert po.items.first().quantity == product.reorder_quantity


@pytest.mark.django_db
def test_auto_draft_does_not_duplicate_existing_draft(shop, product, owner_user):
    from apps.inventory.services import record_stock_transaction
    from apps.inventory.models import StockTransaction

    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-16, user=owner_user,
    )
    first_run = auto_draft_purchase_orders_for_shop(shop)
    second_run = auto_draft_purchase_orders_for_shop(shop)
    assert len(first_run) == 1
    assert len(second_run) == 0  # no duplicate draft created
    assert PurchaseOrder.objects.filter(shop=shop).count() == 1


@pytest.mark.django_db
def test_receiving_po_updates_stock(shop, product, supplier, owner_user):
    po = PurchaseOrder.objects.create(shop=shop, supplier=supplier, status=PurchaseOrder.Status.ORDERED)
    from apps.suppliers.models import PurchaseOrderItem
    PurchaseOrderItem.objects.create(purchase_order=po, product=product, quantity=30, unit_cost=10)

    mark_purchase_order_received(po, owner_user)

    product.refresh_from_db()
    po.refresh_from_db()
    assert product.quantity == 50
    assert po.status == PurchaseOrder.Status.RECEIVED
