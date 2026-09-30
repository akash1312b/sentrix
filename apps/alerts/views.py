from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import ShopScopedViewSetMixin

from .models import Alert
from .serializers import AlertSerializer


class AlertViewSet(ShopScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.select_related("product")
    serializer_class = AlertSerializer
    filterset_fields = ["alert_type", "status"]

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.status = Alert.Status.ACKNOWLEDGED
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=["status", "acknowledged_at"])
        return Response(self.get_serializer(alert).data)
