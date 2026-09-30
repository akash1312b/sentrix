from rest_framework.permissions import BasePermission


class IsShopMember(BasePermission):
    """Object-level permission: user must belong to the shop that owns
    the object (via obj.shop or the object itself being a Shop)."""

    def has_object_permission(self, request, view, obj):
        shop = getattr(obj, "shop", obj)
        return request.user.memberships.filter(shop=shop).exists()


class IsShopOwner(BasePermission):
    """Restrict destructive actions (e.g. deleting a product, approving a
    purchase order) to users with the 'owner' role on the shop."""

    def has_object_permission(self, request, view, obj):
        shop = getattr(obj, "shop", obj)
        return request.user.memberships.filter(shop=shop, role="owner").exists()
