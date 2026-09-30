"""
Alert creation + delivery. Kept independent of *how* a stock change
happened (manual sale, chatbot action, PO receipt) — anything that calls
apps.inventory.services.record_stock_transaction gets alerting for free.
"""
import logging

from django.core.mail import send_mail

from .models import Alert

logger = logging.getLogger("apps.alerts")


def _upsert_alert(product, alert_type, message) -> Alert:
    alert, _created = Alert.objects.update_or_create(
        product=product, alert_type=alert_type,
        defaults={"shop": product.shop, "message": message, "status": Alert.Status.PENDING},
    )
    return alert


def _clear_alert(product, alert_type) -> None:
    Alert.objects.filter(product=product, alert_type=alert_type).delete()


def evaluate_stock_alerts_for_product(product) -> None:
    """Called right after any stock transaction — reacts immediately
    rather than waiting for the next scheduled Celery Beat run."""
    if product.is_out_of_stock:
        alert = _upsert_alert(
            product, Alert.AlertType.OUT_OF_STOCK,
            f"'{product.name}' is out of stock.",
        )
        send_alert_notification(alert)
    elif product.is_low_stock:
        alert = _upsert_alert(
            product, Alert.AlertType.LOW_STOCK,
            f"'{product.name}' is low on stock ({product.quantity} left, "
            f"threshold {product.effective_reorder_threshold}).",
        )
        send_alert_notification(alert)
    else:
        _clear_alert(product, Alert.AlertType.LOW_STOCK)
        _clear_alert(product, Alert.AlertType.OUT_OF_STOCK)


def evaluate_expiry_alert_for_product(product) -> None:
    if product.is_expiring_soon:
        alert = _upsert_alert(
            product, Alert.AlertType.EXPIRING_SOON,
            f"'{product.name}' expires on {product.expiry_date}.",
        )
        send_alert_notification(alert)
    else:
        _clear_alert(product, Alert.AlertType.EXPIRING_SOON)


def send_alert_notification(alert: Alert) -> None:
    """Email is the default channel; swap/extend with Twilio for
    SMS/WhatsApp without touching any of the alert-generation logic."""
    from django.utils import timezone

    shop_owners = alert.shop.memberships.filter(role="owner").select_related("user")
    recipients = [
        m.user.email for m in shop_owners
        if m.user.email and m.user.receive_email_alerts
    ]
    if not recipients:
        logger.info("No email recipients for alert %s — skipping send.", alert.id)
        return

    try:
        send_mail(
            subject=f"[Sentrix] {alert.get_alert_type_display()}: {alert.product.name}",
            message=alert.message,
            from_email=None,
            recipient_list=recipients,
            fail_silently=True,
        )
        alert.status = Alert.Status.SENT
        alert.sent_at = timezone.now()
        alert.save(update_fields=["status", "sent_at"])
    except Exception:
        logger.exception("Failed to send alert notification for alert %s", alert.id)
