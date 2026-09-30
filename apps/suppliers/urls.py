from rest_framework.routers import DefaultRouter

from . import views

app_name = "suppliers"

router = DefaultRouter()
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchase-order")

urlpatterns = router.urls
