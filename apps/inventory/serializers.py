from rest_framework import serializers

from .models import Category, Product, StockTransaction, Supplier
from .services import estimate_days_until_stockout


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "created_at"]
        read_only_fields = ["id", "created_at"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id", "name", "contact_name", "phone_number", "email",
            "lead_time_days", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    is_expiring_soon = serializers.BooleanField(read_only=True)
    days_until_stockout = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "category", "category_name",
            "supplier", "supplier_name", "cost_price", "sale_price",
            "quantity", "reorder_threshold", "reorder_quantity",
            "expiry_date", "is_active", "is_low_stock", "is_out_of_stock",
            "is_expiring_soon", "days_until_stockout", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_days_until_stockout(self, obj):
        return estimate_days_until_stockout(obj)

    def create(self, validated_data):
        validated_data["shop"] = self.context["request"].shop
        return super().create(validated_data)


class StockTransactionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockTransaction
        fields = [
            "id", "product", "product_name", "transaction_type", "quantity",
            "unit_price", "note", "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class BarcodeLookupSerializer(serializers.Serializer):
    barcode = serializers.CharField()
