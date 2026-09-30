from rest_framework.routers import DefaultRouter

from . import views

app_name = "alerts"

router = DefaultRouter()
router.register("", views.AlertViewSet, basename="alert")

urlpatterns = router.urls
