from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ShopScopedModel


class Category(ShopScopedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("shop", "name")
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Supplier(ShopScopedModel):
    """Kept in inventory as a lightweight FK target; the full supplier
    workflow (purchase orders) lives in apps.suppliers."""
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    lead_time_days = models.PositiveIntegerField(
        default=3, help_text="Typical days between placing a PO and receiving stock."
    )

    def __str__(self):
        return self.name


class Product(ShopScopedModel):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.IntegerField(default=0)
    reorder_threshold = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Below this quantity, an alert fires. Falls back to the shop default if unset.",
    )
    reorder_quantity = models.PositiveIntegerField(
        default=20, help_text="Suggested quantity to reorder when stock runs low.",
    )
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("shop", "sku")
        indexes = [models.Index(fields=["shop", "barcode"])]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def effective_reorder_threshold(self) -> int:
        return self.reorder_threshold or self.shop.low_stock_threshold_default

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.effective_reorder_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.quantity <= 0

    @property
    def is_expiring_soon(self) -> bool:
        if not self.expiry_date:
            return False
        days_ahead = settings.EXPIRY_ALERT_DAYS_AHEAD
        return self.expiry_date <= timezone.now().date() + timezone.timedelta(days=days_ahead)


class StockTransaction(ShopScopedModel):
    """Every change to a product's quantity is recorded here — this is
    the audit trail that powers sales analytics and reorder predictions."""

    class TransactionType(models.TextChoices):
        PURCHASE_IN = "purchase_in", "Purchase (stock in)"
        SALE_OUT = "sale_out", "Sale (stock out)"
        RETURN_IN = "return_in", "Customer return (stock in)"
        DAMAGE_OUT = "damage_out", "Damaged/expired (stock out)"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    quantity = models.IntegerField(help_text="Positive for stock in, negative for stock out.")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="stock_transactions"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product} {self.quantity:+d} ({self.transaction_type})"
