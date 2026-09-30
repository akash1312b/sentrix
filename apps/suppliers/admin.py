from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderItem


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "shop", "supplier", "status", "auto_generated", "created_at")
    list_filter = ("shop", "status", "auto_generated")
    inlines = [PurchaseOrderItemInline]
