from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Membership, Shop, User

admin.site.site_header = "Sentrix Admin"
admin.site.site_title = "Sentrix"
admin.site.index_title = "Shop & Inventory Management"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Contact & Preferences", {
            "fields": ("phone_number", "receive_email_alerts", "receive_sms_alerts"),
        }),
    )


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "currency", "is_active", "created_at")
    search_fields = ("name",)
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "role", "created_at")
    list_filter = ("role",)
