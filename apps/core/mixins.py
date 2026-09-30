from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.accounts.models import Shop

SHOP_ID_HEADER_PARAMETER = OpenApiParameter(
    name="X-Shop-Id",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="UUID of the shop this request acts on. The authenticated "
                 "user must have a Membership for this shop.",
)


class ShopHeaderAutoSchema(AutoSchema):
    """Ensures every endpoint using ShopScopedViewSetMixin documents the
    required X-Shop-Id header in the OpenAPI schema (and therefore in the
    Swagger 'Try it out' UI), without having to annotate every view/action
    individually with @extend_schema."""

    def get_override_parameters(self):
        return super().get_override_parameters() + [SHOP_ID_HEADER_PARAMETER]


class ShopScopedViewSetMixin:
    """
    Every domain model (Product, Supplier, PurchaseOrder, ...) belongs to a
    Shop. Rather than repeat the same "which shop, does the user belong to
    it" logic in every view, this mixin resolves `request.shop` once from
    the `X-Shop-Id` header and scopes get_queryset() automatically.

    A user can belong to multiple shops (see Membership), so the shop must
    be explicit per-request rather than inferred solely from the user.
    """

    schema = ShopHeaderAutoSchema()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        shop_id = request.headers.get("X-Shop-Id")
        if not shop_id:
            raise NotFound("Missing required 'X-Shop-Id' header.")

        membership = request.user.memberships.filter(shop_id=shop_id).select_related("shop").first()
        if not membership:
            raise PermissionDenied("You do not have access to this shop.")

        request.shop = membership.shop
        request.membership = membership

    def get_queryset(self):
        return super().get_queryset().filter(shop=self.request.shop)