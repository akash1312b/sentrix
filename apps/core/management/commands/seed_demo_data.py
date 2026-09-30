import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Membership, Shop, User
from apps.inventory.models import Category, Product, StockTransaction, Supplier
from apps.inventory.services import record_stock_transaction


class Command(BaseCommand):
    help = "Seed a demo shop with categories, suppliers, products, and sales history."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="owner@demo.local")
        parser.add_argument("--password", default="demopass123")

    def handle(self, *args, **options):
        shop, _ = Shop.objects.get_or_create(
            name="Sharma General Store", defaults={"low_stock_threshold_default": 8},
        )
        user, created = User.objects.get_or_create(
            username="demo_owner",
            defaults={"email": options["email"], "first_name": "Demo", "last_name": "Owner"},
        )
        if created:
            user.set_password(options["password"])
            user.save()
        Membership.objects.get_or_create(user=user, shop=shop, role=Membership.Role.OWNER)

        supplier, _ = Supplier.objects.get_or_create(
            shop=shop, name="ABC Distributors",
            defaults={"contact_name": "Ramesh", "phone_number": "9999999999", "lead_time_days": 3},
        )
        category, _ = Category.objects.get_or_create(shop=shop, name="Groceries")

        catalogue = [
            ("Maggi Noodles 70g", "MAG-070", 8901058851826, 10, 14, 45, 10),
            ("Amul Butter 500g", "AMB-500", 8901063210017, 210, 250, 12, 5),
            ("Tata Salt 1kg", "TSA-1KG", 8901030826805, 18, 25, 60, 15),
            ("Parle-G Biscuit", "PLG-100", 8901719110016, 8, 10, 5, 20),
            ("Colgate Toothpaste 100g", "COL-100", 8901314102015, 45, 60, 30, 10),
        ]

        self.stdout.write("Seeding products...")
        for name, sku, barcode, cost, price, qty, threshold in catalogue:
            product, _ = Product.objects.get_or_create(
                shop=shop, sku=sku,
                defaults=dict(
                    name=name, barcode=str(barcode), category=category, supplier=supplier,
                    cost_price=cost, sale_price=price, quantity=qty,
                    reorder_threshold=threshold, reorder_quantity=threshold * 4,
                ),
            )

        self.stdout.write("Simulating 30 days of sales history...")
        for product in Product.objects.filter(shop=shop):
            for days_ago in range(30, 0, -1):
                product.refresh_from_db()
                if product.quantity <= 0:
                    break  # nothing left to sell for this product
                if random.random() < 0.6:  # not every product sells every day
                    qty_sold = min(random.randint(1, 5), product.quantity)
                    if qty_sold <= 0:
                        continue
                    txn = record_stock_transaction(
                        product=product,
                        transaction_type=StockTransaction.TransactionType.SALE_OUT,
                        quantity=-qty_sold,
                        note="Simulated historical sale",
                        user=user,
                    )
                    txn.created_at = timezone.now() - timedelta(days=days_ago)
                    txn.save(update_fields=["created_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Done. Shop='{shop.name}' Login user='demo_owner' password='{options['password']}' "
            f"(or use --email/--password to customize). Shop ID: {shop.id}"
        ))
