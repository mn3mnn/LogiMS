"""Celery tasks for document expiration notifications."""

from celery import shared_task
from celery.utils.log import get_task_logger
from .services import NotificationService
from .models import NotificationConfig

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, rate_limit='10/h')
def check_document_expiration(self):
    """
    Celery task to check document expiration and send notifications.
    This task should be scheduled to run daily (or as configured).
    Rate limited to 10 executions per hour to prevent abuse.
    """
    try:
        # Get configuration
        config = NotificationConfig.get_config()

        if not config.is_active:
            logger.info("Notifications are disabled in configuration")
            return {
                "status": "skipped",
                "reason": "Notifications disabled",
            }

        # Initialize service and process documents
        service = NotificationService(config)
        stats = service.process_all_documents()

        # Log results
        logger.info(
            f"Document expiration check completed: "
            f"Expiring checked: {stats['expiring_checked']}, "
            f"digest sent to admins: {stats['expiring_digest_sent_to_admins']}, "
            f"sent to drivers: {stats['expiring_sent_to_drivers']}; "
            f"Expired checked: {stats['expired_checked']}, "
            f"digest sent to admins: {stats['expired_digest_sent_to_admins']}, "
            f"sent to drivers: {stats['expired_sent_to_drivers']}"
        )

        if stats["errors"]:
            logger.warning(f"Errors occurred: {'; '.join(stats['errors'])}")

        return {
            "status": "success",
            "stats": stats,
        }

    except Exception as exc:
        logger.error(f"Error in document expiration check: {str(exc)}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_test_notification(driver_id: int, doc_type: str = "license"):
    """
    Send a test notification for a specific driver and document type.
    Useful for testing the notification system.
    """
    from logims.drivers.models import Driver

    try:
        driver = Driver.objects.get(id=driver_id)
        config = NotificationConfig.get_config()
        service = NotificationService(config)

        # Get the document
        doc_type_map = {
            "national_id": "national_id_doc",
            "license": "license",
            "vehicle_license": "vehicle_license",
        }

        related_name = doc_type_map.get(doc_type)
        if not related_name:
            return {"status": "error", "message": f"Invalid document type: {doc_type}"}

        document = getattr(driver, related_name, None)
        if not document:
            return {
                "status": "error",
                "message": f"Driver has no {doc_type} document",
            }

        # Send warning notification
        success = service.send_expiration_notification(
            driver=driver,
            document=document,
            doc_type=doc_type,
            notification_type="warning",
        )

        return {
            "status": "success" if success else "failed",
            "driver_id": driver_id,
            "doc_type": doc_type,
        }

    except Driver.DoesNotExist:
        return {"status": "error", "message": f"Driver with ID {driver_id} not found"}
    except Exception as e:
        logger.error(f"Error sending test notification: {str(e)}")
        return {"status": "error", "message": str(e)}


@shared_task
def cleanup_old_logs(days: int = 90):
    """
    Cleanup notification logs older than specified days.
    This task can be scheduled to run monthly to keep the database clean.

    Args:
        days: Delete logs older than this many days (default: 90)
    """
    from .utils import cleanup_old_logs as do_cleanup

    try:
        deleted_count = do_cleanup(days=days)
        logger.info(f"Cleaned up {deleted_count} notification logs older than {days} days")
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "days": days,
        }
    except Exception as e:
        logger.error(f"Error cleaning up old logs: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
        }

