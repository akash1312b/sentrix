from django.db import models

from apps.core.models import ShopScopedModel


class Alert(ShopScopedModel):
    class AlertType(models.TextChoices):
        LOW_STOCK = "low_stock", "Low stock"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        EXPIRING_SOON = "expiring_soon", "Expiring soon"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"

    product = models.ForeignKey(
        "inventory.Product", on_delete=models.CASCADE, related_name="alerts"
    )
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    message = models.CharField(max_length=500)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # One active alert per product/type — re-running the check task
        # updates the existing row (see alerts.services) instead of
        # spamming a fresh alert every time the task runs.
        unique_together = ("product", "alert_type")

    def __str__(self):
        return f"[{self.alert_type}] {self.product} - {self.status}"
