from rest_framework.routers import DefaultRouter

from . import views

app_name = "inventory"

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("products", views.ProductViewSet, basename="product")
router.register("transactions", views.StockTransactionViewSet, basename="transaction")

urlpatterns = router.urls
