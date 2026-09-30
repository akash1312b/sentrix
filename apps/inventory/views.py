from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.mixins import ShopScopedViewSetMixin

from .models import Category, Product, StockTransaction, Supplier
from .serializers import (
    BarcodeLookupSerializer, CategorySerializer, ProductSerializer,
    StockTransactionSerializer, SupplierSerializer,
)
from .services import InsufficientStockError, record_stock_transaction


class CategoryViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def perform_create(self, serializer):
        serializer.save(shop=self.request.shop)


class SupplierViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def perform_create(self, serializer):
        serializer.save(shop=self.request.shop)


class ProductViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category", "supplier")
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "supplier", "is_active"]
    search_fields = ["name", "sku", "barcode"]
    ordering_fields = ["name", "quantity", "created_at"]

    def initial(self, request, *args, **kwargs):
        if getattr(self, "action", None) == "import_template":
            return super(ShopScopedViewSetMixin, self).initial(request, *args, **kwargs)
        return super().initial(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        products = [p for p in self.get_queryset() if p.is_low_stock]
        return Response(self.get_serializer(products, many=True).data)

    @action(detail=False, methods=["get"], url_path="expiring-soon")
    def expiring_soon(self, request):
        products = [p for p in self.get_queryset() if p.is_expiring_soon]
        return Response(self.get_serializer(products, many=True).data)

    @action(detail=False, methods=["post"], url_path="barcode-lookup")
    def barcode_lookup(self, request):
        """Scan/type a barcode -> instantly resolve to a product (or 404
        so the frontend can prompt 'add new product with this barcode')."""
        serializer = BarcodeLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = self.get_queryset().filter(barcode=serializer.validated_data["barcode"]).first()
        if not product:
            return Response({"detail": "No product found for this barcode."}, status=404)
        return Response(self.get_serializer(product).data)

    @action(detail=True, methods=["post"], url_path="adjust-stock")
    def adjust_stock(self, request, pk=None):
        """
        Record a stock in/out movement for this product. This is the same
        entry point the AI chatbot's tools call, so behaviour (including
        alert triggering) is always identical between UI and chat.
        """
        product = self.get_object()
        txn_type = request.data.get("transaction_type")
        quantity = request.data.get("quantity")
        note = request.data.get("note", "")

        if txn_type not in StockTransaction.TransactionType.values:
            return Response({"detail": "Invalid transaction_type."}, status=400)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer."}, status=400)

        try:
            txn = record_stock_transaction(
                product=product, transaction_type=txn_type, quantity=quantity,
                note=note, user=request.user,
            )
        except InsufficientStockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(StockTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get", "post", "delete"], url_path="sample-data")
    def sample_data(self, request):
        """Manage demo sample products for the current shop."""
        sample_skus = [
            "SMP-RICE-5K", "SMP-ATTA-10K", "SMP-OIL-1L", "SMP-TEA-500", "SMP-COF-100",
            "SMP-CKI-200", "SMP-CHP-090", "SMP-MLK-1L", "SMP-EGG-12P", "SMP-SOP-125",
        ]
        existing_sample_qs = self.get_queryset().filter(sku__in=sample_skus)
        count = existing_sample_qs.count()

        if request.method == "GET":
            return Response({"loaded": count > 0, "count": count})

        if request.method == "DELETE":
            deleted_count, _ = existing_sample_qs.delete()
            return Response({"loaded": False, "count": 0, "deleted": deleted_count, "detail": "Sample items removed."})

        if request.method == "POST":
            if count > 0:
                return Response({"detail": "Sample data already exists.", "loaded": True, "count": count}, status=status.HTTP_409_CONFLICT)

            sample_items = [
                {
                    "name": "Basmati Rice (5 kg)", "sku": "SMP-RICE-5K", "barcode": "8901030826801",
                    "category": "Groceries", "sale_price": "450.00", "cost_price": "380.00",
                    "quantity": 25, "reorder_threshold": 10, "reorder_quantity": 20,
                },
                {
                    "name": "Whole Wheat Atta (10 kg)", "sku": "SMP-ATTA-10K", "barcode": "8901030826802",
                    "category": "Groceries", "sale_price": "380.00", "cost_price": "320.00",
                    "quantity": 18, "reorder_threshold": 8, "reorder_quantity": 15,
                },
                {
                    "name": "Refined Sunflower Oil (1 L)", "sku": "SMP-OIL-1L", "barcode": "8901030826803",
                    "category": "Groceries", "sale_price": "165.00", "cost_price": "140.00",
                    "quantity": 30, "reorder_threshold": 12, "reorder_quantity": 24,
                },
                {
                    "name": "Premium CTC Tea (500 g)", "sku": "SMP-TEA-500", "barcode": "8901030826804",
                    "category": "Beverages", "sale_price": "220.00", "cost_price": "180.00",
                    "quantity": 15, "reorder_threshold": 6, "reorder_quantity": 12,
                },
                {
                    "name": "Instant Coffee Jar (100 g)", "sku": "SMP-COF-100", "barcode": "8901030826805",
                    "category": "Beverages", "sale_price": "290.00", "cost_price": "240.00",
                    "quantity": 12, "reorder_threshold": 5, "reorder_quantity": 10,
                },
                {
                    "name": "Crunchy Butter Cookies (200 g)", "sku": "SMP-CKI-200", "barcode": "8901030826806",
                    "category": "Snacks", "sale_price": "60.00", "cost_price": "45.00",
                    "quantity": 40, "reorder_threshold": 15, "reorder_quantity": 30,
                },
                {
                    "name": "Potato Chips Classic (90 g)", "sku": "SMP-CHP-090", "barcode": "8901030826807",
                    "category": "Snacks", "sale_price": "40.00", "cost_price": "28.00",
                    "quantity": 4, "reorder_threshold": 10, "reorder_quantity": 25,
                },
                {
                    "name": "Fresh Pasteurized Milk (1 L)", "sku": "SMP-MLK-1L", "barcode": "8901030826808",
                    "category": "Dairy & Eggs", "sale_price": "65.00", "cost_price": "52.00",
                    "quantity": 0, "reorder_threshold": 8, "reorder_quantity": 20,
                },
                {
                    "name": "Farm Fresh Eggs (Pack of 12)", "sku": "SMP-EGG-12P", "barcode": "8901030826809",
                    "category": "Dairy & Eggs", "sale_price": "95.00", "cost_price": "75.00",
                    "quantity": 20, "reorder_threshold": 6, "reorder_quantity": 15,
                },
                {
                    "name": "Herbal Bath Soap (125 g)", "sku": "SMP-SOP-125", "barcode": "8901030826810",
                    "category": "Personal Care", "sale_price": "55.00", "cost_price": "40.00",
                    "quantity": 50, "reorder_threshold": 15, "reorder_quantity": 30,
                },
            ]

            created_objs = []
            for item in sample_items:
                cat, _ = Category.objects.get_or_create(shop=request.shop, name=item["category"])
                prod = Product.objects.create(
                    shop=request.shop,
                    name=item["name"],
                    sku=item["sku"],
                    barcode=item["barcode"],
                    category=cat,
                    sale_price=item["sale_price"],
                    cost_price=item["cost_price"],
                    quantity=item["quantity"],
                    reorder_threshold=item["reorder_threshold"],
                    reorder_quantity=item["reorder_quantity"],
                    is_active=True,
                )
                created_objs.append(prod)

            return Response({
                "loaded": True,
                "count": len(created_objs),
                "detail": "Sample items added successfully.",
            }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="import-template", permission_classes=[permissions.AllowAny])
    def import_template(self, request):
        """Download sample CSV template for bulk product import."""
        from django.http import HttpResponse

        csv_content = (
            "Product Name,Selling Price,Cost Price,SKU,Barcode,Category,Stock Quantity,Reorder Threshold\n"
            "Basmati Rice 5kg,450.00,380.00,RICE-5K,8901030826801,Groceries,25,10\n"
            "Whole Wheat Atta 10kg,380.00,320.00,ATTA-10K,8901030826802,Groceries,18,8\n"
            "Sunflower Cooking Oil 1L,165.00,140.00,OIL-1L,8901030826803,Groceries,30,12\n"
            "Premium Tea 500g,220.00,180.00,TEA-500,8901030826804,Beverages,15,6\n"
            "Butter Cookies 200g,60.00,45.00,CKI-200,8901030826806,Snacks,40,15\n"
        )
        response = HttpResponse(csv_content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sentrix_product_import_template.csv"'
        return response

    @action(detail=False, methods=["post"], url_path="import")
    def import_products(self, request):
        """Bulk import products from uploaded CSV file."""
        import csv
        import uuid

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "Please select a CSV file to upload."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            content = uploaded_file.read().decode("utf-8-sig", errors="replace")
        except Exception:
            return Response({"detail": "Could not read the uploaded file. Please make sure it is a valid CSV file."}, status=status.HTTP_400_BAD_REQUEST)

        lines = [line for line in content.splitlines() if line.strip()]
        if not lines:
            return Response({"detail": "The uploaded CSV file is empty."}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.reader(lines)
        try:
            header_row = next(reader)
        except StopIteration:
            return Response({"detail": "The uploaded CSV file has no header row."}, status=status.HTTP_400_BAD_REQUEST)

        header_map = {}
        for idx, col in enumerate(header_row):
            clean_col = col.strip().lower().replace(" ", "_").replace("-", "_")
            header_map[clean_col] = idx

        def get_val(row, keys, default=""):
            for k in keys:
                if k in header_map and header_map[k] < len(row):
                    v = row[header_map[k]].strip()
                    if v:
                        return v
            return default

        created_count = 0
        problems = []
        total_rows = 0

        for row_idx, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue
            total_rows += 1

            name = get_val(row, ["product_name", "name", "item_name", "title"])
            if not name:
                problems.append({
                    "row": row_idx,
                    "name": "Unknown",
                    "reason": "Product name is required and was empty."
                })
                continue

            sale_price_str = get_val(row, ["selling_price", "sale_price", "price", "mrp", "retail_price"])
            if not sale_price_str:
                problems.append({
                    "row": row_idx,
                    "name": name,
                    "reason": "Selling price is empty."
                })
                continue

            try:
                sale_price = float(sale_price_str.replace("$", "").replace("₹", "").replace(",", "").strip())
                if sale_price < 0:
                    raise ValueError("Negative price")
            except ValueError:
                problems.append({
                    "row": row_idx,
                    "name": name,
                    "reason": f"Selling price '{sale_price_str}' is not a valid number."
                })
                continue

            cost_price_str = get_val(row, ["cost_price", "cost", "purchase_price", "buy_price"], "0")
            try:
                cost_price = float(cost_price_str.replace("$", "").replace("₹", "").replace(",", "").strip()) if cost_price_str else 0.0
            except ValueError:
                cost_price = 0.0

            qty_str = get_val(row, ["stock_quantity", "quantity", "stock", "qty", "count"], "0")
            try:
                quantity = int(float(qty_str)) if qty_str else 0
            except ValueError:
                quantity = 0

            threshold_str = get_val(row, ["reorder_threshold", "threshold", "min_stock", "low_stock_threshold"], "")
            try:
                reorder_threshold = int(float(threshold_str)) if threshold_str else None
            except ValueError:
                reorder_threshold = None

            sku = get_val(row, ["sku", "code", "item_code", "product_code"])
            barcode = get_val(row, ["barcode", "upc", "ean", "isbn"])
            category_name = get_val(row, ["category", "category_name", "department"])
            supplier_name = get_val(row, ["supplier", "supplier_name", "vendor"])

            category_obj = None
            if category_name:
                category_obj, _ = Category.objects.get_or_create(shop=request.shop, name=category_name)

            supplier_obj = None
            if supplier_name:
                supplier_obj, _ = Supplier.objects.get_or_create(shop=request.shop, name=supplier_name)

            if not sku:
                sku = f"SKU-{uuid.uuid4().hex[:8].upper()}"

            Product.objects.update_or_create(
                shop=request.shop,
                sku=sku,
                defaults={
                    "name": name,
                    "barcode": barcode,
                    "category": category_obj,
                    "supplier": supplier_obj,
                    "sale_price": sale_price,
                    "cost_price": cost_price,
                    "quantity": quantity,
                    "reorder_threshold": reorder_threshold,
                    "is_active": True,
                }
            )
            created_count += 1

        return Response({
            "created": created_count,
            "skipped": len(problems),
            "problems": problems,
            "total_rows": total_rows,
        })


class StockTransactionViewSet(ShopScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only: transactions are created via Product.adjust_stock (or the
    chatbot), never edited directly, to keep the audit trail trustworthy."""

    queryset = StockTransaction.objects.select_related("product")
    serializer_class = StockTransactionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["product", "transaction_type"]
    ordering_fields = ["created_at"]
