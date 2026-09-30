from django.conf import settings
from django.db import models

from apps.core.models import ShopScopedModel


class PurchaseOrder(ShopScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending approval"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    supplier = models.ForeignKey(
        "inventory.Supplier", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    auto_generated = models.BooleanField(
        default=False, help_text="True if created automatically by the low-stock automation task.",
    )
    expected_delivery_date = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_purchase_orders",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO-{str(self.id)[:8]} · {self.supplier.name} · {self.status}"

    @property
    def total_cost(self):
        return sum(item.line_total for item in self.items.all())


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="po_items")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
