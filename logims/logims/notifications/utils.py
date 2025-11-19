"""Utility functions for the notifications app."""

from datetime import timedelta
from django.utils import timezone
from typing import Dict, List
from .models import NotificationLog


def get_notification_statistics(days: int = 30) -> Dict:
    """
    Get notification statistics for the last N days.

    Args:
        days: Number of days to look back (default: 30)

    Returns:
        Dictionary containing notification statistics
    """
    start_date = timezone.now() - timedelta(days=days)

    logs = NotificationLog.objects.filter(created_at__gte=start_date)

    stats = {
        "total_notifications": logs.count(),
        "sent": logs.filter(status="sent").count(),
        "failed": logs.filter(status="failed").count(),
        "pending": logs.filter(status="pending").count(),
        "by_type": {
            "warning": logs.filter(notification_type="warning").count(),
            "expired": logs.filter(notification_type="expired").count(),
        },
        "by_document_type": {
            "national_id": logs.filter(document_type="national_id").count(),
            "license": logs.filter(document_type="license").count(),
            "vehicle_license": logs.filter(document_type="vehicle_license").count(),
            "contract": logs.filter(document_type="contract").count(),
        },
        "period_days": days,
    }

    return stats


def get_recent_failures(limit: int = 10) -> List[NotificationLog]:
    """
    Get most recent failed notifications.

    Args:
        limit: Maximum number of failures to return

    Returns:
        List of NotificationLog objects with failed status
    """
    return list(
        NotificationLog.objects.filter(status="failed")
        .order_by("-created_at")[:limit]
        .select_related("driver")
    )


def cleanup_old_logs(days: int = 90) -> int:
    """
    Delete notification logs older than specified days.

    Args:
        days: Delete logs older than this many days

    Returns:
        Number of logs deleted
    """
    cutoff_date = timezone.now() - timedelta(days=days)
    deleted_count, _ = NotificationLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    return deleted_count


def get_driver_notification_history(driver_id: int, limit: int = 20) -> List[NotificationLog]:
    """
    Get notification history for a specific driver.

    Args:
        driver_id: ID of the driver
        limit: Maximum number of records to return

    Returns:
        List of NotificationLog objects for the driver
    """
    return list(
        NotificationLog.objects.filter(driver_id=driver_id)
        .order_by("-created_at")[:limit]
    )


def retry_failed_notification(log_id: int) -> bool:
    """
    Retry sending a failed notification.

    Args:
        log_id: ID of the NotificationLog to retry

    Returns:
        True if retry was successful, False otherwise
    """
    from .services import NotificationService
    from .models import NotificationConfig

    try:
        log = NotificationLog.objects.get(id=log_id, status="failed")

        # Get the document
        driver = log.driver
        doc_type = log.document_type

        # Map document type to related name
        doc_type_map = {
            "national_id": "national_id_doc",
            "license": "license",
            "vehicle_license": "vehicle_license",
            "contract": None,  # Contracts need special handling
        }

        if doc_type == "contract":
            # For contracts, we need to get the specific contract by ID
            from logims.drivers.models import DriverContract
            document = DriverContract.objects.get(id=log.document_id)
        else:
            related_name = doc_type_map.get(doc_type)
            if not related_name:
                return False
            document = getattr(driver, related_name, None)

        if not document:
            return False

        # Delete the old failed log
        log.delete()

        # Try sending again
        config = NotificationConfig.get_config()
        service = NotificationService(config)

        return service.send_expiration_notification(
            driver=driver,
            document=document,
            doc_type=doc_type,
            notification_type=log.notification_type,
        )

    except Exception:
        return False


def validate_email_configuration() -> Dict[str, bool]:
    """
    Validate that email configuration is properly set up.

    Returns:
        Dictionary with validation results
    """
    from django.core.mail import get_connection
    from django.conf import settings
    from .models import NotificationConfig

    results = {
        "email_backend_configured": bool(settings.EMAIL_BACKEND),
        "smtp_settings_valid": False,
        "admin_emails_configured": False,
        "from_email_configured": False,
        "can_connect": False,
    }

    # Check if SMTP settings are configured
    try:
        if hasattr(settings, "EMAIL_HOST") and settings.EMAIL_HOST:
            results["smtp_settings_valid"] = True
    except Exception:
        pass

    # Check notification config
    try:
        config = NotificationConfig.get_config()
        results["admin_emails_configured"] = bool(config.admin_emails)
        results["from_email_configured"] = bool(
            config.from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        )
    except Exception:
        pass

    # Try to establish connection
    try:
        connection = get_connection()
        connection.open()
        results["can_connect"] = True
        connection.close()
    except Exception:
        pass

    return results

