from rest_framework import serializers

from apps.inventory.serializers import ProductSerializer

from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_detail = ProductSerializer(source="product", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "product_detail", "quantity", "unit_cost", "line_total"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "supplier", "supplier_name", "status", "auto_generated",
            "expected_delivery_date", "approved_by", "notes", "items",
            "total_cost", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "auto_generated", "approved_by", "created_at", "updated_at"]
