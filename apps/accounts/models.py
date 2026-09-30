import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import TimeStampedModel


class User(AbstractUser):
    """Custom user model so we can extend it later (phone, notification
    preferences, etc.) without a painful mid-project migration."""

    phone_number = models.CharField(max_length=20, blank=True)
    receive_email_alerts = models.BooleanField(default=True)
    receive_sms_alerts = models.BooleanField(default=False)

    def __str__(self):
        return self.get_full_name() or self.username


class Shop(TimeStampedModel):
    """A single physical/online store. Kept separate from User so one
    owner can eventually run multiple shops without a data model change."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    low_stock_threshold_default = models.PositiveIntegerField(
        default=10,
        help_text="Fallback reorder threshold for products that don't set their own.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
    """Links a User to a Shop with a role. This is the join table that
    makes multi-shop / multi-staff support possible from day one."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)

    class Meta:
        unique_together = ("user", "shop")

    def __str__(self):
        return f"{self.user} @ {self.shop} ({self.role})"
