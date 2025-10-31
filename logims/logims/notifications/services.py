"""Service layer for notification logic."""

from datetime import timedelta
from typing import List, Tuple, Optional
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.conf import settings
from logims.drivers.models import (
    Driver,
    DriverNationalID,
    DriverLicense,
    DriverVehicleLicense,
    DriverContract,
)
from .models import NotificationConfig, NotificationLog


class DocumentExpirationChecker:
    """
    Service for checking document expiration status.
    """

    DOCUMENT_MODELS = {
        "national_id": {
            "model": DriverNationalID,
            "related_name": "national_id_doc",
            "display_name": "National ID",
        },
        "license": {
            "model": DriverLicense,
            "related_name": "license",
            "display_name": "Driver License",
        },
        "vehicle_license": {
            "model": DriverVehicleLicense,
            "related_name": "vehicle_license",
            "display_name": "Vehicle License",
        },
        "contract": {
            "model": DriverContract,
            "related_name": "contracts",
            "display_name": "Contract",
        },
    }

    def __init__(self, config: NotificationConfig = None):
        self.config = config or NotificationConfig.get_config()

    def get_expiring_documents(self) -> List[Tuple[str, object, Driver]]:
        """
        Get all documents that are about to expire.
        Returns list of tuples: (document_type, document, driver)
        """
        if not self.config.notify_on_warning:
            return []

        warning_date = timezone.now().date() + timedelta(
            days=self.config.warning_days_before_expiry
        )
        today = timezone.now().date()

        expiring_docs = []

        for doc_type, doc_info in self.DOCUMENT_MODELS.items():
            # Check if notifications are enabled for this document type
            if not self._is_document_type_enabled(doc_type):
                continue

            model = doc_info["model"]
            related_name = doc_info["related_name"]

            if doc_type == "contract":
                # Contracts can have multiple per driver
                documents = model.objects.filter(
                    expiry_date__lte=warning_date,
                    expiry_date__gt=today,
                    is_active=True,
                ).select_related("driver")

                for doc in documents:
                    expiring_docs.append((doc_type, doc, doc.driver))
            else:
                # OneToOne relationships
                drivers = Driver.objects.filter(
                    is_active=True,
                    **{
                        f"{related_name}__expiry_date__lte": warning_date,
                        f"{related_name}__expiry_date__gt": today,
                        f"{related_name}__is_active": True,
                    }
                ).select_related(related_name)

                for driver in drivers:
                    doc = getattr(driver, related_name, None)
                    if doc:
                        expiring_docs.append((doc_type, doc, driver))

        return expiring_docs

    def get_expired_documents(self) -> List[Tuple[str, object, Driver]]:
        """
        Get all documents that have expired.
        Returns list of tuples: (document_type, document, driver)
        """
        if not self.config.notify_on_expired:
            return []

        today = timezone.now().date()
        expired_docs = []

        for doc_type, doc_info in self.DOCUMENT_MODELS.items():
            # Check if notifications are enabled for this document type
            if not self._is_document_type_enabled(doc_type):
                continue

            model = doc_info["model"]
            related_name = doc_info["related_name"]

            if doc_type == "contract":
                # Contracts can have multiple per driver
                documents = model.objects.filter(
                    expiry_date__lt=today,
                    is_active=True,
                ).select_related("driver")

                for doc in documents:
                    expired_docs.append((doc_type, doc, doc.driver))
            else:
                # OneToOne relationships
                drivers = Driver.objects.filter(
                    is_active=True,
                    **{
                        f"{related_name}__expiry_date__lt": today,
                        f"{related_name}__is_active": True,
                    }
                ).select_related(related_name)

                for driver in drivers:
                    doc = getattr(driver, related_name, None)
                    if doc:
                        expired_docs.append((doc_type, doc, driver))

        return expired_docs

    def _is_document_type_enabled(self, doc_type: str) -> bool:
        """Check if notifications are enabled for a specific document type."""
        type_flags = {
            "national_id": self.config.notify_national_id,
            "license": self.config.notify_license,
            "vehicle_license": self.config.notify_vehicle_license,
            "contract": self.config.notify_contract,
        }
        return type_flags.get(doc_type, False)

    @staticmethod
    def get_document_display_name(doc_type: str) -> str:
        """Get human-readable display name for document type."""
        return DocumentExpirationChecker.DOCUMENT_MODELS.get(doc_type, {}).get(
            "display_name", doc_type.replace("_", " ").title()
        )


class NotificationService:
    """
    Service for sending document expiration notifications.
    Sends digest emails to admins and individual emails to drivers.
    """

    def __init__(self, config: NotificationConfig = None):
        self.config = config or NotificationConfig.get_config()
        self.checker = DocumentExpirationChecker(self.config)

    def send_expiration_notification(
        self,
        driver: Driver,
        document: object,
        doc_type: str,
        notification_type: str,
        connection: Optional[object] = None,
    ) -> bool:
        """
        Send a notification for a document expiration.
        Returns True if notification was sent successfully.
        """
        if not self.config.is_active:
            return False

        # Check if we should send this notification
        if not NotificationLog.should_send_notification(
            driver=driver,
            document_type=doc_type,
            notification_type=notification_type,
            expiry_date=document.expiry_date,
        ):
            return False

        # Build recipient list
        recipients = self._build_recipient_list(driver)
        if not recipients:
            return False

        # Create notification log
        log = NotificationLog.objects.create(
            notification_type=notification_type,
            document_type=doc_type,
            driver=driver,
            document_id=document.id,
            expiry_date=document.expiry_date,
            recipients=recipients,
            status="pending",
        )

        try:
            # Send email
            self._send_email(
                driver=driver,
                document=document,
                doc_type=doc_type,
                notification_type=notification_type,
                recipients=recipients,
                connection=connection,
            )

            # Mark as sent
            log.mark_sent()
            return True

        except Exception as e:
            # Mark as failed
            log.mark_failed(str(e))
            return False

    def _build_recipient_list(self, driver: Driver) -> List[str]:
        """
        Build list of email recipients for individual driver notification.
        Only includes the driver's email (admins get digest emails separately).
        """
        recipients = []

        # Only add driver email for individual notifications
        # Admins receive digest emails separately
        if self.config.notify_driver and driver.email:
            recipients.append(driver.email)

        return recipients

    def _send_email(
        self,
        driver: Driver,
        document: object,
        doc_type: str,
        notification_type: str,
        recipients: List[str],
        connection: Optional[object] = None,
    ):
        """Send email notification."""
        # Calculate days until/since expiration
        today = timezone.now().date()
        days_diff = (document.expiry_date - today).days

        # Build context for templates
        context = {
            "driver": driver,
            "document": document,
            "doc_type_display": self.checker.get_document_display_name(doc_type),
            "expiry_date": document.expiry_date,
            "days_until_expiry": days_diff if days_diff > 0 else 0,
            "days_since_expired": abs(days_diff) if days_diff < 0 else 0,
            "notification_type": notification_type,
            "company": driver.company,
        }

        # Determine subject based on notification type
        if notification_type == "warning":
            subject = (
                f"{self.config.email_subject_prefix} Document Expiring Soon - "
                f"{driver.first_name} {driver.last_name} - "
                f"{context['doc_type_display']}"
            )
            template_name = "notifications/document_expiring_warning"
        else:  # expired
            subject = (
                f"{self.config.email_subject_prefix} Document Expired - "
                f"{driver.first_name} {driver.last_name} - "
                f"{context['doc_type_display']}"
            )
            template_name = "notifications/document_expired"

        # Render email templates
        text_content = render_to_string(f"{template_name}.txt", context)
        html_content = render_to_string(f"{template_name}.html", context)

        # Get from email
        from_email = self.config.from_email or settings.DEFAULT_FROM_EMAIL

        # Create and send email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients,
            connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

    def send_admin_digest(
        self,
        documents: List[Tuple[str, object, Driver]],
        notification_type: str,
        connection: Optional[object] = None,
    ) -> bool:
        """
        Send a single digest email to admins with all documents.

        Args:
            documents: List of (doc_type, document, driver) tuples
            notification_type: "warning" or "expired"

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.config.notify_admins or not self.config.admin_emails:
            return False

        if not documents:
            return False

        # Check if we should send based on cooldown period (from config)
        if not NotificationLog.should_send_admin_digest(notification_type):
            return False

        try:
            # Prepare document data for template
            today = timezone.now().date()
            documents_data = []

            for doc_type, document, driver in documents:
                days_diff = (document.expiry_date - today).days
                documents_data.append({
                    'driver': driver,
                    'document': document,
                    'doc_type_display': self.checker.get_document_display_name(doc_type),
                    'days_until_expiry': days_diff if days_diff > 0 else 0,
                    'days_since_expired': abs(days_diff) if days_diff < 0 else 0,
                })

            # Build context for templates
            context = {
                'documents': documents_data,
                'warning_days': self.config.warning_days_before_expiry,
                'notification_type': notification_type,
            }

            # Determine subject and template
            if notification_type == "warning":
                subject = (
                    f"{self.config.email_subject_prefix} "
                    f"{len(documents)} Document(s) Expiring Soon - Action Required"
                )
                template_name = "notifications/admin_digest_warning"
            else:  # expired
                subject = (
                    f"{self.config.email_subject_prefix} URGENT: "
                    f"{len(documents)} Document(s) Expired - Immediate Action Required"
                )
                template_name = "notifications/admin_digest_expired"

            # Render email templates
            text_content = render_to_string(f"{template_name}.txt", context)
            html_content = render_to_string(f"{template_name}.html", context)

            # Get from email
            from_email = self.config.from_email or settings.DEFAULT_FROM_EMAIL

            # Create and send email
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=self.config.admin_emails,
                connection=connection,
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()

            # Log the digest notification - create one entry per document for better tracking
            for doc_type, document, driver in documents:
                NotificationLog.objects.create(
                    notification_type=notification_type,
                    document_type="admin_digest",  # Special type for digest
                    driver=driver,
                    document_id=document.id,
                    expiry_date=document.expiry_date,
                    recipients=self.config.admin_emails,
                    status="sent",
                    sent_at=timezone.now(),
                )

            return True

        except Exception as e:
            # Log error for each document that was supposed to be in the digest
            for doc_type, document, driver in documents:
                NotificationLog.objects.create(
                    notification_type=notification_type,
                    document_type="admin_digest",
                    driver=driver,
                    document_id=document.id,
                    expiry_date=document.expiry_date,
                    recipients=self.config.admin_emails,
                    status="failed",
                    error_message=str(e),
                )
            return False

    def process_all_documents(self) -> dict:
        """
        Process all documents and send notifications as needed.
        Sends digest emails to admins and individual emails to drivers.
        Uses connection pooling for better performance.
        Returns statistics about notifications sent.
        """
        stats = {
            "expiring_checked": 0,
            "expiring_sent_to_drivers": 0,
            "expiring_digest_sent_to_admins": False,
            "expired_checked": 0,
            "expired_sent_to_drivers": 0,
            "expired_digest_sent_to_admins": False,
            "errors": [],
        }

        # Open a single email connection for all sends (connection pooling)
        connection = get_connection()

        try:
            connection.open()

            # Process expiring documents
            if self.config.notify_on_warning:
                expiring_docs = self.checker.get_expiring_documents()
                stats["expiring_checked"] = len(expiring_docs)

                # Send digest email to admins with ALL expiring documents
                if expiring_docs and self.config.notify_admins:
                    try:
                        if self.send_admin_digest(expiring_docs, "warning", connection=connection):
                            stats["expiring_digest_sent_to_admins"] = True
                    except Exception as e:
                        stats["errors"].append(
                            f"Error sending expiring documents digest to admins: {str(e)}"
                        )

                # Send individual emails to drivers
                if self.config.notify_driver:
                    for doc_type, document, driver in expiring_docs:
                        try:
                            if self.send_expiration_notification(
                                driver=driver,
                                document=document,
                                doc_type=doc_type,
                                notification_type="warning",
                                connection=connection,
                            ):
                                stats["expiring_sent_to_drivers"] += 1
                        except Exception as e:
                            stats["errors"].append(
                                f"Error sending warning to driver {driver.id}: {str(e)}"
                            )

            # Process expired documents
            if self.config.notify_on_expired:
                expired_docs = self.checker.get_expired_documents()
                stats["expired_checked"] = len(expired_docs)

                # Send digest email to admins with ALL expired documents
                if expired_docs and self.config.notify_admins:
                    try:
                        if self.send_admin_digest(expired_docs, "expired", connection=connection):
                            stats["expired_digest_sent_to_admins"] = True
                    except Exception as e:
                        stats["errors"].append(
                            f"Error sending expired documents digest to admins: {str(e)}"
                        )

                # Send individual emails to drivers
                if self.config.notify_driver:
                    for doc_type, document, driver in expired_docs:
                        try:
                            if self.send_expiration_notification(
                                driver=driver,
                                document=document,
                                doc_type=doc_type,
                                notification_type="expired",
                                connection=connection,
                            ):
                                stats["expired_sent_to_drivers"] += 1
                        except Exception as e:
                            stats["errors"].append(
                                f"Error sending expired notification to driver {driver.id}: {str(e)}"
                            )

        finally:
            # Always close the connection
            try:
                connection.close()
            except Exception:
                pass  # Ignore errors when closing connection

        return stats

