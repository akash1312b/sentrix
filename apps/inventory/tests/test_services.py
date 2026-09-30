import pytest

from apps.inventory.models import StockTransaction
from apps.inventory.services import (
    InsufficientStockError, get_low_stock_products, record_stock_transaction,
)


@pytest.mark.django_db
def test_record_stock_transaction_updates_quantity(product, owner_user):
    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-6, user=owner_user,
    )
    product.refresh_from_db()
    assert product.quantity == 14


@pytest.mark.django_db
def test_record_stock_transaction_prevents_overselling(product, owner_user):
    with pytest.raises(InsufficientStockError):
        record_stock_transaction(
            product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
            quantity=-999, user=owner_user,
        )
    product.refresh_from_db()
    assert product.quantity == 20  # unchanged


@pytest.mark.django_db
def test_low_stock_detection(product, owner_user, shop):
    assert not product.is_low_stock
    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-16, user=owner_user,
    )
    product.refresh_from_db()
    assert product.is_low_stock
    assert product in get_low_stock_products(shop)


@pytest.mark.django_db
def test_stock_transaction_creates_alert_automatically(product, owner_user):
    from apps.alerts.models import Alert

    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-16, user=owner_user,
    )
    assert Alert.objects.filter(product=product, alert_type=Alert.AlertType.LOW_STOCK).exists()


@pytest.mark.django_db
def test_alert_clears_once_restocked(product, owner_user):
    from apps.alerts.models import Alert

    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.SALE_OUT,
        quantity=-16, user=owner_user,
    )
    assert Alert.objects.filter(product=product, alert_type=Alert.AlertType.LOW_STOCK).exists()

    record_stock_transaction(
        product=product, transaction_type=StockTransaction.TransactionType.PURCHASE_IN,
        quantity=30, user=owner_user,
    )
    assert not Alert.objects.filter(product=product, alert_type=Alert.AlertType.LOW_STOCK).exists()
