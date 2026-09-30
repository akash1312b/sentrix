"""
Business logic kept out of views/serializers so both the REST API and the
AI chatbot's tool-calling layer can share exactly the same code path.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Product, StockTransaction


class InsufficientStockError(Exception):
    pass


@transaction.atomic
def record_stock_transaction(
    *, product: Product, transaction_type: str, quantity: int,
    unit_price: Decimal | None = None, note: str = "", user=None,
) -> StockTransaction:
    """
    Single choke point for every stock change. Locks the product row so
    concurrent sales (e.g. two staff members ringing up a sale at once)
    can't both read a stale quantity and oversell.
    """
    product = Product.objects.select_for_update().get(pk=product.pk)

    new_quantity = product.quantity + quantity
    if new_quantity < 0:
        raise InsufficientStockError(
            f"Cannot remove {abs(quantity)} units of '{product.name}': "
            f"only {product.quantity} in stock."
        )

    product.quantity = new_quantity
    product.save(update_fields=["quantity", "updated_at"])

    txn = StockTransaction.objects.create(
        shop=product.shop,
        product=product,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=unit_price,
        note=note,
        created_by=user,
    )

    # Import locally to avoid a circular import (alerts -> inventory).
    from apps.alerts.services import evaluate_stock_alerts_for_product
    evaluate_stock_alerts_for_product(product)

    return txn


def get_low_stock_products(shop):
    return [p for p in Product.objects.filter(shop=shop, is_active=True) if p.is_low_stock]


def get_expiring_products(shop):
    return [p for p in Product.objects.filter(shop=shop, is_active=True) if p.is_expiring_soon]


def estimate_days_until_stockout(product: Product, lookback_days: int = 30) -> float | None:
    """
    Simple, explainable forecasting: average daily sales over the lookback
    window, projected forward against current stock. Deliberately not a
    full ML model — this is accurate, fast, and easy to defend in review.
    """
    since = timezone.now() - timezone.timedelta(days=lookback_days)
    sold_qs = product.transactions.filter(
        transaction_type=StockTransaction.TransactionType.SALE_OUT,
        created_at__gte=since,
    )
    total_sold = abs(sum(t.quantity for t in sold_qs))
    if total_sold == 0:
        return None

    avg_daily_sales = total_sold / lookback_days
    if avg_daily_sales == 0:
        return None
    return round(product.quantity / avg_daily_sales, 1)
