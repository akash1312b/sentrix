import json
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.accounts.models import Membership, Shop, User
from apps.alerts.models import Alert
from apps.chatbot.models import ChatMessage, ChatSession
from apps.chatbot.services import run_chat_turn
from apps.inventory.models import Category, Product, StockTransaction, Supplier
from apps.inventory.services import (
    InsufficientStockError,
    estimate_days_until_stockout,
    record_stock_transaction,
)
from apps.suppliers.models import PurchaseOrder, PurchaseOrderItem
from apps.suppliers.services import (
    auto_draft_purchase_orders_for_shop,
    mark_purchase_order_received,
)


def _get_shop_and_user(request, shop_id=None):
    if not shop_id and hasattr(request, "headers"):
        shop_id = request.headers.get("X-Shop-Id") or request.headers.get("x-shop-id")
    if not shop_id and hasattr(request, "META"):
        shop_id = request.META.get("HTTP_X_SHOP_ID")

    shop = None
    if shop_id:
        shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    if not shop:
        shop = Shop.objects.filter(is_active=True).first()

    req_user = getattr(request, "user", None)
    user = req_user if req_user and req_user.is_authenticated else None

    if not user and hasattr(request, "headers"):
        auth_header = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(auth_header.split(" ")[1])
                user = jwt_auth.get_user(validated_token)
            except Exception:
                pass

    if not user and shop:
        user, _ = User.objects.get_or_create(
            username="demo_owner",
            defaults={"email": "owner@demo.local", "first_name": "Demo", "last_name": "Owner"},
        )
        Membership.objects.get_or_create(user=user, shop=shop, defaults={"role": Membership.Role.OWNER})

    return shop, user


class LoginPageView(TemplateView):
    template_name = "core/login.html"


class SignupPageView(TemplateView):
    template_name = "core/signup.html"


class BaseShopView(TemplateView):
    """Base view providing shop context and active tab info."""
    active_page = "dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        shop, _ = _get_shop_and_user(self.request, self.request.GET.get("shop_id"))
        ctx["shops"] = Shop.objects.filter(is_active=True)
        ctx["current_shop"] = shop
        ctx["active_page"] = self.active_page
        return ctx


class DashboardView(BaseShopView):
    template_name = "core/dashboard.html"
    active_page = "dashboard"


class ProductsView(BaseShopView):
    template_name = "core/products.html"
    active_page = "products"


class PosView(BaseShopView):
    template_name = "core/pos.html"
    active_page = "pos"


class OrdersView(BaseShopView):
    template_name = "core/orders.html"
    active_page = "orders"


class AlertsView(BaseShopView):
    template_name = "core/alerts.html"
    active_page = "alerts"


class AssistantView(BaseShopView):
    template_name = "core/chat.html"
    active_page = "chat"


@method_decorator(csrf_exempt, name="dispatch")
class WebDashboardDataView(View):
    """Returns complete real-time JSON payload with metrics, catalog, and chart datasets."""

    def get(self, request, *args, **kwargs):
        shop_id = request.GET.get("shop_id")
        shop, _ = _get_shop_and_user(request, shop_id)
        if not shop:
            return JsonResponse({"error": "No active shop found. Please seed demo data."}, status=404)

        products_qs = Product.objects.filter(shop=shop, is_active=True).select_related("category", "supplier")
        products_data = []
        total_valuation = 0
        total_cost_valuation = 0
        low_stock_count = 0
        out_of_stock_count = 0
        healthy_count = 0
        category_valuation_map = {}

        for p in products_qs:
            sale_val = float(p.sale_price) * p.quantity
            cost_val = float(p.cost_price) * p.quantity
            total_valuation += sale_val
            total_cost_valuation += cost_val

            cat_name = p.category.name if p.category else "Uncategorized"
            category_valuation_map[cat_name] = category_valuation_map.get(cat_name, 0.0) + sale_val

            if p.is_out_of_stock:
                out_of_stock_count += 1
            elif p.is_low_stock:
                low_stock_count += 1
            else:
                healthy_count += 1

            products_data.append({
                "id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "barcode": p.barcode or "",
                "quantity": p.quantity,
                "unit": getattr(p, "unit", "units") or "units",
                "reorder_threshold": p.effective_reorder_threshold,
                "reorder_quantity": p.reorder_quantity,
                "cost_price": float(p.cost_price),
                "sale_price": float(p.sale_price),
                "category_id": str(p.category_id) if p.category_id else "",
                "category_name": cat_name,
                "supplier_id": str(p.supplier_id) if p.supplier_id else "",
                "supplier_name": p.supplier.name if p.supplier else "No Supplier",
                "expiry_date": p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else "",
                "is_low_stock": p.is_low_stock,
                "is_out_of_stock": p.is_out_of_stock,
                "is_expiring_soon": p.is_expiring_soon,
                "days_until_stockout": estimate_days_until_stockout(p),
            })

        # Categories & Suppliers
        categories = list(Category.objects.filter(shop=shop).values("id", "name"))
        suppliers = list(Supplier.objects.filter(shop=shop).values("id", "name", "lead_time_days", "phone_number", "contact_name"))

        # Purchase orders
        orders_qs = PurchaseOrder.objects.filter(shop=shop).select_related("supplier").prefetch_related("items__product").order_by("-created_at")[:25]
        orders_data = []
        for o in orders_qs:
            orders_data.append({
                "id": str(o.id),
                "supplier_name": o.supplier.name if o.supplier else "Direct Supplier",
                "status": o.status,
                "auto_generated": o.auto_generated,
                "total_cost": float(o.total_cost),
                "created_at": o.created_at.strftime("%b %d, %Y"),
                "items_count": o.items.count(),
                "items": [
                    {
                        "product_name": item.product.name,
                        "quantity": item.quantity,
                        "unit_cost": float(item.unit_cost),
                        "line_total": float(item.line_total),
                    }
                    for item in o.items.all()
                ],
            })

        # Alerts
        alerts_qs = Alert.objects.filter(shop=shop).select_related("product").order_by("-created_at")[:25]
        alerts_data = [
            {
                "id": str(a.id),
                "product_name": a.product.name if a.product else "System",
                "alert_type": a.alert_type,
                "status": a.status,
                "message": a.message,
                "created_at": a.created_at.strftime("%b %d, %H:%M"),
            }
            for a in alerts_qs
        ]

        # Recent transactions
        transactions_qs = StockTransaction.objects.filter(shop=shop).select_related("product").order_by("-created_at")[:20]
        txns_data = [
            {
                "id": str(t.id),
                "product_name": t.product.name if t.product else "Unknown Item",
                "transaction_type": t.get_transaction_type_display(),
                "raw_type": t.transaction_type,
                "quantity": t.quantity,
                "note": t.note or "",
                "created_at": t.created_at.strftime("%b %d, %H:%M"),
            }
            for t in transactions_qs
        ]

        # 7-day movement trends for Chart
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        recent_all_txns = StockTransaction.objects.filter(
            shop=shop, created_at__gte=seven_days_ago
        ).values("transaction_type", "quantity", "created_at")

        trend_labels = []
        sales_trend = []
        restock_trend = []
        for i in range(6, -1, -1):
            day_date = (timezone.now() - timezone.timedelta(days=i)).date()
            trend_labels.append(day_date.strftime("%a %d"))
            day_sales = sum(
                abs(t["quantity"]) for t in recent_all_txns
                if t["created_at"].date() == day_date and t["transaction_type"] == StockTransaction.TransactionType.SALE_OUT
            )
            day_restock = sum(
                t["quantity"] for t in recent_all_txns
                if t["created_at"].date() == day_date and t["transaction_type"] == StockTransaction.TransactionType.PURCHASE_IN
            )
            sales_trend.append(day_sales)
            restock_trend.append(day_restock)

        # Category chart data
        category_chart_labels = list(category_valuation_map.keys())
        category_chart_values = [round(val, 2) for val in category_valuation_map.values()]

        # All available shops for switcher
        all_shops = list(Shop.objects.filter(is_active=True).values("id", "name", "currency"))

        return JsonResponse({
            "shop": {
                "id": str(shop.id),
                "name": shop.name,
                "currency": shop.currency,
            },
            "all_shops": [{"id": str(s["id"]), "name": s["name"], "currency": s["currency"]} for s in all_shops],
            "metrics": {
                "total_products": len(products_data),
                "total_valuation": round(total_valuation, 2),
                "total_cost_valuation": round(total_cost_valuation, 2),
                "profit_margin": round(((total_valuation - total_cost_valuation) / total_valuation * 100) if total_valuation > 0 else 0, 1),
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
                "healthy_count": healthy_count,
                "pending_orders": len([o for o in orders_data if o["status"] in ["draft", "pending", "ordered"]]),
                "active_alerts": len([a for a in alerts_data if a["status"] != "acknowledged"]),
            },
            "products": products_data,
            "categories": [{"id": str(c["id"]), "name": c["name"]} for c in categories],
            "suppliers": [
                {
                    "id": str(s["id"]),
                    "name": s["name"],
                    "lead_time_days": s["lead_time_days"],
                    "phone_number": s["phone_number"] or "",
                    "contact_name": s["contact_name"] or "",
                }
                for s in suppliers
            ],
            "purchase_orders": orders_data,
            "alerts": alerts_data,
            "recent_transactions": txns_data,
            "charts": {
                "categories": {
                    "labels": category_chart_labels,
                    "values": category_chart_values,
                },
                "health": {
                    "labels": ["Healthy", "Low Stock", "Out of Stock"],
                    "values": [healthy_count, low_stock_count, out_of_stock_count],
                },
                "trends": {
                    "labels": trend_labels,
                    "sales": sales_trend,
                    "restock": restock_trend,
                }
            }
        })


@method_decorator(csrf_exempt, name="dispatch")
class WebProductManageView(View):
    """Create, Update, or Delete products from the web UI."""

    def post(self, request, *args, **kwargs):
        """Add new or update existing product."""
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        shop, _ = _get_shop_and_user(request, data.get("shop_id"))
        if not shop:
            return JsonResponse({"error": "Shop not found"}, status=404)

        product_id = data.get("id")
        name = data.get("name", "").strip()
        sku = data.get("sku", "").strip()
        barcode = data.get("barcode", "").strip() or None
        sale_price = data.get("sale_price")
        cost_price = data.get("cost_price", 0.0)
        reorder_threshold = data.get("reorder_threshold", 5)
        reorder_quantity = data.get("reorder_quantity", 10)
        category_id = data.get("category_id")
        supplier_id = data.get("supplier_id")
        unit = data.get("unit", "units").strip()
        expiry_date = data.get("expiry_date") or None

        if not name or not sku or sale_price is None:
            return JsonResponse({"error": "Name, SKU, and Sale Price are required fields."}, status=400)

        try:
            sale_price = Decimal(str(sale_price))
            cost_price = Decimal(str(cost_price))
            reorder_threshold = int(reorder_threshold)
            reorder_quantity = int(reorder_quantity)
        except Exception:
            return JsonResponse({"error": "Invalid numeric values for prices or thresholds."}, status=400)

        category = Category.objects.filter(pk=category_id, shop=shop).first() if category_id else None
        supplier = Supplier.objects.filter(pk=supplier_id, shop=shop).first() if supplier_id else None

        if product_id:
            # Update existing
            prod = Product.objects.filter(pk=product_id, shop=shop).first()
            if not prod:
                return JsonResponse({"error": "Product not found to update."}, status=404)
            prod.name = name
            prod.sku = sku
            prod.barcode = barcode
            prod.sale_price = sale_price
            prod.cost_price = cost_price
            prod.reorder_threshold = reorder_threshold
            prod.reorder_quantity = reorder_quantity
            prod.category = category
            prod.supplier = supplier
            if expiry_date:
                prod.expiry_date = expiry_date
            prod.save()
            return JsonResponse({"success": True, "message": f"Updated '{prod.name}' successfully."})
        else:
            # Create new
            initial_stock = int(data.get("initial_stock", 0))
            if Product.objects.filter(shop=shop, sku__iexact=sku).exists():
                return JsonResponse({"error": f"SKU '{sku}' already exists in this shop."}, status=400)

            prod = Product.objects.create(
                shop=shop,
                name=name,
                sku=sku,
                barcode=barcode,
                quantity=initial_stock,
                cost_price=cost_price,
                sale_price=sale_price,
                reorder_threshold=reorder_threshold,
                reorder_quantity=reorder_quantity,
                category=category,
                supplier=supplier,
                expiry_date=expiry_date,
            )

            # Record initial stock in ledger if > 0
            if initial_stock > 0:
                _, user = _get_shop_and_user(request, data.get("shop_id"))
                record_stock_transaction(
                    product=prod,
                    transaction_type=StockTransaction.TransactionType.PURCHASE_IN,
                    quantity=initial_stock,
                    note="Initial catalog intake",
                    user=user,
                )

            return JsonResponse({"success": True, "product_id": str(prod.id), "message": f"Created product '{prod.name}' successfully."})

    def delete(self, request, *args, **kwargs):
        """Soft delete / deactivate or remove product."""
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            data = {}

        product_id = data.get("id") or request.GET.get("id")
        shop, _ = _get_shop_and_user(request)
        prod = Product.objects.filter(pk=product_id, shop=shop).first()
        if not prod:
            return JsonResponse({"error": "Product not found"}, status=404)

        prod.is_active = False
        prod.save(update_fields=["is_active"])
        return JsonResponse({"success": True, "message": f"Archived product '{prod.name}'."})


@method_decorator(csrf_exempt, name="dispatch")
class WebStockAdjustView(View):
    """Endpoint for instant stock adjustments from the UI modals."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        product_id = data.get("product_id")
        txn_type = data.get("transaction_type", "sale_out")
        quantity = data.get("quantity")
        note = data.get("note", "Recorded via Web UI")

        if not product_id or not quantity:
            return JsonResponse({"error": "product_id and quantity are required"}, status=400)

        try:
            quantity = int(quantity)
        except ValueError:
            return JsonResponse({"error": "quantity must be an integer"}, status=400)

        shop, user = _get_shop_and_user(request, data.get("shop_id"))
        product = Product.objects.filter(pk=product_id, shop=shop).first()
        if not product:
            return JsonResponse({"error": "Product not found"}, status=404)

        # Ensure correct sign based on transaction type
        signed_quantity = abs(quantity)
        if txn_type in [StockTransaction.TransactionType.SALE_OUT, StockTransaction.TransactionType.DAMAGE_OUT]:
            signed_quantity = -abs(quantity)

        try:
            txn = record_stock_transaction(
                product=product,
                transaction_type=txn_type,
                quantity=signed_quantity,
                note=note,
                user=user,
            )
            product.refresh_from_db()
            return JsonResponse({
                "success": True,
                "product_name": product.name,
                "new_quantity": product.quantity,
                "transaction_id": str(txn.id),
                "message": f"Successfully recorded {txn.get_transaction_type_display()} for {product.name}.",
            })
        except InsufficientStockError as exc:
            return JsonResponse({"error": str(exc)}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class WebPosCheckoutView(View):
    """Atomic multi-item point-of-sale checkout endpoint."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        items = data.get("items", [])
        if not items:
            return JsonResponse({"error": "Cart is empty"}, status=400)

        shop, user = _get_shop_and_user(request, data.get("shop_id"))
        customer_name = data.get("customer_name", "Counter Sale").strip()
        payment_method = data.get("payment_method", "Cash").strip()
        discount = Decimal(str(data.get("discount", 0)))

        receipt_items = []
        total_amount = Decimal("0.00")

        try:
            with transaction.atomic():
                for item in items:
                    prod_id = item.get("product_id")
                    qty = int(item.get("quantity", 1))
                    if qty <= 0:
                        continue

                    prod = Product.objects.select_for_update().filter(pk=prod_id, shop=shop).first()
                    if not prod:
                        raise ValueError(f"Product ID '{prod_id}' not found.")

                    if prod.quantity < qty:
                        raise InsufficientStockError(
                            f"Not enough stock for '{prod.name}'. In stock: {prod.quantity}, requested: {qty}."
                        )

                    line_total = Decimal(str(prod.sale_price)) * qty
                    total_amount += line_total

                    # Record transaction
                    record_stock_transaction(
                        product=prod,
                        transaction_type=StockTransaction.TransactionType.SALE_OUT,
                        quantity=-qty,
                        note=f"POS Sale — {customer_name} ({payment_method})",
                        user=user,
                    )

                    receipt_items.append({
                        "name": prod.name,
                        "quantity": qty,
                        "unit_price": float(prod.sale_price),
                        "line_total": float(line_total),
                    })

            net_total = max(Decimal("0.00"), total_amount - discount)
            receipt_id = f"RCP-{timezone.now().strftime('%y%m%d')}-{str(timezone.now().timestamp())[-4:]}"

            return JsonResponse({
                "success": True,
                "receipt": {
                    "receipt_id": receipt_id,
                    "shop_name": shop.name,
                    "currency": shop.currency,
                    "customer_name": customer_name,
                    "payment_method": payment_method,
                    "items": receipt_items,
                    "subtotal": float(total_amount),
                    "discount": float(discount),
                    "total": float(net_total),
                    "timestamp": timezone.now().strftime("%b %d, %Y %I:%M %p"),
                },
                "message": f"Sale completed! Total: {shop.currency} {net_total:,.2f}",
            })
        except InsufficientStockError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class WebCreatePurchaseOrderView(View):
    """Create a manual purchase order with custom supplier and item line items."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        shop, user = _get_shop_and_user(request, data.get("shop_id"))
        supplier_id = data.get("supplier_id")
        items_data = data.get("items", [])
        notes = data.get("notes", "")

        if not supplier_id or not items_data:
            return JsonResponse({"error": "Supplier and at least one item are required."}, status=400)

        supplier = Supplier.objects.filter(pk=supplier_id, shop=shop).first()
        if not supplier:
            return JsonResponse({"error": "Supplier not found"}, status=404)

        try:
            with transaction.atomic():
                po = PurchaseOrder.objects.create(
                    shop=shop,
                    supplier=supplier,
                    status=PurchaseOrder.Status.DRAFT,
                    auto_generated=False,
                    notes=notes,
                )

                for item in items_data:
                    prod = Product.objects.filter(pk=item.get("product_id"), shop=shop).first()
                    if not prod:
                        continue
                    qty = int(item.get("quantity", 1))
                    unit_cost = Decimal(str(item.get("unit_cost", prod.cost_price)))

                    PurchaseOrderItem.objects.create(
                        purchase_order=po,
                        product=prod,
                        quantity=qty,
                        unit_cost=unit_cost,
                    )

            return JsonResponse({
                "success": True,
                "order_id": str(po.id),
                "message": f"Drafted Purchase Order PO-{str(po.id)[:8]} with {len(items_data)} line item(s).",
            })
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class WebBarcodeLookupView(View):
    """Instant barcode and SKU search for the scanner modal."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        code = data.get("code", "").strip()
        shop, _ = _get_shop_and_user(request, data.get("shop_id"))

        product = (
            Product.objects.filter(shop=shop, barcode=code).first()
            or Product.objects.filter(shop=shop, sku__iexact=code).first()
            or Product.objects.filter(shop=shop, name__icontains=code).first()
        )

        if not product:
            return JsonResponse({"found": False, "message": f"No product found matching '{code}'."}, status=404)

        return JsonResponse({
            "found": True,
            "product": {
                "id": str(product.id),
                "name": product.name,
                "sku": product.sku,
                "barcode": product.barcode or "",
                "quantity": product.quantity,
                "sale_price": float(product.sale_price),
                "cost_price": float(product.cost_price),
                "is_low_stock": product.is_low_stock,
                "is_out_of_stock": product.is_out_of_stock,
                "category_name": product.category.name if product.category else "Uncategorized",
                "days_until_stockout": estimate_days_until_stockout(product),
            }
        })


@method_decorator(csrf_exempt, name="dispatch")
class WebPurchaseOrderActionView(View):
    """Approve, Receive, or Auto-Draft Purchase Orders."""

    def post(self, request, action, *args, **kwargs):
        shop, user = _get_shop_and_user(request)
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            data = {}

        if action == "auto-draft":
            created = auto_draft_purchase_orders_for_shop(shop)
            return JsonResponse({
                "success": True,
                "count": len(created),
                "message": f"Drafted {len(created)} purchase order(s) for low stock products.",
            })

        order_id = data.get("order_id") or kwargs.get("order_id")
        po = PurchaseOrder.objects.filter(pk=order_id, shop=shop).first()
        if not po:
            return JsonResponse({"error": "Purchase order not found"}, status=404)

        if action == "approve":
            po.status = PurchaseOrder.Status.ORDERED
            po.approved_by = user
            po.save(update_fields=["status", "approved_by", "updated_at"])
            return JsonResponse({"success": True, "status": po.status, "message": f"PO-{str(po.id)[:8]} approved and marked as ORDERED."})

        elif action == "receive":
            mark_purchase_order_received(po, user)
            return JsonResponse({"success": True, "status": po.status, "message": f"PO-{str(po.id)[:8]} received and stock booked successfully."})

        return JsonResponse({"error": "Invalid action"}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class WebAlertActionView(View):
    """Acknowledge single or bulk alert notifications."""

    def post(self, request, alert_id=None, *args, **kwargs):
        shop, _ = _get_shop_and_user(request)

        # Bulk acknowledge
        if not alert_id or str(alert_id) == "all":
            updated_count = Alert.objects.filter(shop=shop, status=Alert.Status.TRIGGERED).update(
                status=Alert.Status.ACKNOWLEDGED,
                acknowledged_at=timezone.now()
            )
            return JsonResponse({"success": True, "message": f"Acknowledged {updated_count} active alert(s)."})

        alert = Alert.objects.filter(pk=alert_id, shop=shop).first()
        if not alert:
            return JsonResponse({"error": "Alert not found"}, status=404)

        alert.status = Alert.Status.ACKNOWLEDGED
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=["status", "acknowledged_at"])
        return JsonResponse({"success": True, "message": "Alert acknowledged."})


@method_decorator(csrf_exempt, name="dispatch")
class WebChatView(View):
    """Web-accessible chat endpoint for interactive testing on the dashboard."""

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        message = data.get("message", "").strip()
        if not message:
            return JsonResponse({"error": "Message is required"}, status=400)

        shop, user = _get_shop_and_user(request, data.get("shop_id"))
        if not shop:
            return JsonResponse({"error": "No active shop found. Run seed_demo_data first."}, status=404)

        session = None
        session_id = data.get("session_id")
        if session_id:
            session = ChatSession.objects.filter(pk=session_id, shop=shop).first()

        if not session:
            session = ChatSession.objects.create(
                shop=shop,
                user=user,
                title=message[:50],
            )

        ChatMessage.objects.create(session=session, role="user", content=message)

        history = [
            {"role": m.role, "content": m.content}
            for m in session.messages.filter(role__in=["user", "assistant"]).order_by("created_at")
        ]

        reply_text, _ = run_chat_turn(shop=shop, user=user, conversation=history)

        ChatMessage.objects.create(session=session, role="assistant", content=reply_text)

        return JsonResponse({
            "session_id": str(session.id),
            "reply": reply_text,
        })
