from django.contrib import admin

from .models import Category, Product, StockTransaction, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "created_at")
    list_filter = ("shop",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "shop", "lead_time_days")
    list_filter = ("shop",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "shop", "quantity", "reorder_threshold", "is_active")
    list_filter = ("shop", "category", "is_active")
    search_fields = ("name", "sku", "barcode")


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "transaction_type", "quantity", "shop", "created_at")
    list_filter = ("shop", "transaction_type")
    readonly_fields = [f.name for f in StockTransaction._meta.fields]
