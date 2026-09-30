from celery import shared_task
from django.core.mail import send_mail

from apps.accounts.models import Shop
from apps.inventory.models import Product
from apps.inventory.services import get_expiring_products, get_low_stock_products

from .services import evaluate_expiry_alert_for_product, evaluate_stock_alerts_for_product


@shared_task
def check_low_stock_levels():
    """Safety net on top of the real-time check in inventory.services —
    catches anything whose threshold changed without a new transaction."""
    checked = 0
    for shop in Shop.objects.filter(is_active=True):
        for product in get_low_stock_products(shop) or Product.objects.filter(shop=shop):
            evaluate_stock_alerts_for_product(product)
            checked += 1
    return {"products_checked": checked}


@shared_task
def check_expiring_products():
    flagged = 0
    for shop in Shop.objects.filter(is_active=True):
        for product in get_expiring_products(shop):
            evaluate_expiry_alert_for_product(product)
            flagged += 1
    return {"products_flagged": flagged}


@shared_task
def send_weekly_sales_summary():
    """Emails each shop owner a plain-language summary. Swap the body for
    an LLM-generated write-up of apps.chatbot.services.get_shop_snapshot()
    if you want the AI-flavoured version of this report."""
    from apps.inventory.services import get_low_stock_products

    sent = 0
    for shop in Shop.objects.filter(is_active=True):
        owners = shop.memberships.filter(role="owner").select_related("user")
        recipients = [m.user.email for m in owners if m.user.email]
        if not recipients:
            continue

        low_stock = get_low_stock_products(shop)
        body = (
            f"Weekly summary for {shop.name}\n\n"
            f"Products low on stock: {len(low_stock)}\n"
            + "\n".join(f"- {p.name}: {p.quantity} left" for p in low_stock[:10])
        )
        send_mail(
            subject=f"[Sentrix] Weekly summary for {shop.name}",
            message=body, from_email=None, recipient_list=recipients, fail_silently=True,
        )
        sent += 1
    return {"summaries_sent": sent}
