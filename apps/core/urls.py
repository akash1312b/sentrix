from django.urls import path

from .views import (
    AlertsView,
    AssistantView,
    DashboardView,
    LoginPageView,
    OrdersView,
    PosView,
    ProductsView,
    SignupPageView,
    WebAlertActionView,
    WebBarcodeLookupView,
    WebChatView,
    WebCreatePurchaseOrderView,
    WebDashboardDataView,
    WebPosCheckoutView,
    WebProductManageView,
    WebPurchaseOrderActionView,
    WebStockAdjustView,
)

app_name = "core"

urlpatterns = [
    # Multi-Page App Routes
    path("", DashboardView.as_view(), name="dashboard"),
    path("login/", LoginPageView.as_view(), name="login-page"),
    path("signup/", SignupPageView.as_view(), name="signup-page"),
    path("products/", ProductsView.as_view(), name="products"),
    path("pos/", PosView.as_view(), name="pos"),
    path("orders/", OrdersView.as_view(), name="orders"),
    path("alerts/", AlertsView.as_view(), name="alerts"),
    path("assistant/", AssistantView.as_view(), name="chat"),
    path("chat/", AssistantView.as_view(), name="chat-alias"),

    # REST APIs & Web Actions
    path("api/dashboard-data/", WebDashboardDataView.as_view(), name="dashboard-data"),
    path("api/products/manage/", WebProductManageView.as_view(), name="product-manage"),
    path("api/inventory/adjust/", WebStockAdjustView.as_view(), name="inventory-adjust"),
    path("api/inventory/barcode/", WebBarcodeLookupView.as_view(), name="inventory-barcode"),
    path("api/pos/checkout/", WebPosCheckoutView.as_view(), name="pos-checkout"),
    path("api/orders/create-custom/", WebCreatePurchaseOrderView.as_view(), name="orders-create-custom"),
    path("api/orders/<str:action>/", WebPurchaseOrderActionView.as_view(), name="order-action-global"),
    path("api/orders/<uuid:order_id>/<str:action>/", WebPurchaseOrderActionView.as_view(), name="order-action"),
    path("api/alerts/acknowledge-all/", WebAlertActionView.as_view(), {"alert_id": "all"}, name="alert-ack-all"),
    path("api/alerts/<uuid:alert_id>/acknowledge/", WebAlertActionView.as_view(), name="alert-ack"),
    path("api/chat/", WebChatView.as_view(), name="web-chat"),
]
