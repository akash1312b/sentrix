import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Use UUIDs as public-facing identifiers instead of sequential ints."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at to any model that inherits it."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ShopScopedModel(TimeStampedModel, UUIDPrimaryKeyModel):
    """
    Base class for every model that belongs to a single shop.
    Centralizing the `shop` FK means every queryset can be filtered
    consistently and managers can enforce tenant isolation.
    """

    shop = models.ForeignKey(
        "accounts.Shop",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )

    class Meta:
        abstract = True
