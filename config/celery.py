import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("sentrix")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Periodic tasks (Celery Beat)
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    "check-low-stock-every-morning": {
        "task": "apps.alerts.tasks.check_low_stock_levels",
        "schedule": crontab(hour=8, minute=0),
    },
    "check-expiring-products-every-morning": {
        "task": "apps.alerts.tasks.check_expiring_products",
        "schedule": crontab(hour=8, minute=15),
    },
    "auto-generate-purchase-orders": {
        "task": "apps.suppliers.tasks.auto_generate_purchase_orders",
        "schedule": crontab(hour=9, minute=0),
    },
    "weekly-sales-summary-report": {
        "task": "apps.alerts.tasks.send_weekly_sales_summary",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
