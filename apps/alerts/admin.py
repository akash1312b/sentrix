from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("product", "alert_type", "status", "shop", "created_at")
    list_filter = ("shop", "alert_type", "status")
