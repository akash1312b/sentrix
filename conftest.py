import pytest


@pytest.fixture(autouse=True)
def _use_sqlite_and_eager_celery(settings):
    """Keep the test suite fast and dependency-free: in-memory-ish sqlite,
    no real network calls, tasks run synchronously."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def shop(db):
    from apps.accounts.models import Shop
    return Shop.objects.create(name="Test Store", low_stock_threshold_default=5)


@pytest.fixture
def owner_user(db, shop):
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Membership

    User = get_user_model()
    user = User.objects.create_user(username="owner", email="owner@example.com", password="pass12345")
    Membership.objects.create(user=user, shop=shop, role=Membership.Role.OWNER)
    return user


@pytest.fixture
def supplier(db, shop):
    from apps.inventory.models import Supplier
    return Supplier.objects.create(shop=shop, name="Test Supplier", lead_time_days=2)


@pytest.fixture
def product(db, shop, supplier):
    from apps.inventory.models import Product
    return Product.objects.create(
        shop=shop, name="Test Widget", sku="WID-001", barcode="1234567890123",
        supplier=supplier, cost_price=10, sale_price=15,
        quantity=20, reorder_threshold=5, reorder_quantity=50,
    )


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()
