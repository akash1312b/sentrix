from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import ShopScopedViewSetMixin

from .models import PurchaseOrder
from .serializers import PurchaseOrderSerializer
from .services import mark_purchase_order_received


class PurchaseOrderViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items")
    serializer_class = PurchaseOrderSerializer
    filterset_fields = ["status", "supplier"]

    def perform_create(self, serializer):
        serializer.save(shop=self.request.shop)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        po = self.get_object()
        po.status = PurchaseOrder.Status.ORDERED
        po.approved_by = request.user
        po.save(update_fields=["status", "approved_by", "updated_at"])
        return Response(self.get_serializer(po).data)

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        po = mark_purchase_order_received(self.get_object(), request.user)
        return Response(self.get_serializer(po).data)
