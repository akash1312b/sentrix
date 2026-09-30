from celery import shared_task

from apps.accounts.models import Shop

from .services import auto_draft_purchase_orders_for_shop


@shared_task
def auto_generate_purchase_orders():
    """Celery Beat runs this daily: for every active shop, draft POs for
    whatever is currently low on stock so the owner just has to approve."""
    total_created = 0
    for shop in Shop.objects.filter(is_active=True):
        created = auto_draft_purchase_orders_for_shop(shop)
        total_created += len(created)
    return {"purchase_orders_created": total_created}
