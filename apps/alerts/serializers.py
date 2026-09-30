from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id", "product", "product_name", "alert_type", "status",
            "message", "sent_at", "acknowledged_at", "created_at",
        ]
        read_only_fields = ["id", "sent_at", "created_at"]
