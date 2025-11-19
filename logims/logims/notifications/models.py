"""Models for notification configuration and logging."""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, EmailValidator
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone


class NotificationConfig(models.Model):
    """
    Configuration for document expiration notifications.
    This model should ideally have only one instance (singleton pattern).
    """

    # Email Recipients
    admin_emails = ArrayField(
        models.EmailField(validators=[EmailValidator()]),
        default=list,
        blank=True,
        help_text="List of email addresses to receive notifications (can be any valid email)",
    )

    # Notification Timing (in days)
    warning_days_before_expiry = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Number of days before expiration to send warning notification",
    )

    # Email Settings
    from_email = models.EmailField(
        blank=True,
        help_text="From email address (leave blank to use default)",
    )
    email_subject_prefix = models.CharField(
        max_length=50,
        default="[LogiMS]",
        help_text="Prefix for email subject lines",
    )

    # Notification Toggles
    notify_on_warning = models.BooleanField(
        default=True,
        help_text="Send notifications when documents are about to expire",
    )
    notify_on_expired = models.BooleanField(
        default=True,
        help_text="Send notifications when documents have expired",
    )
    notify_driver = models.BooleanField(
        default=True,
        help_text="Send notification to driver (if email available)",
    )
    notify_admins = models.BooleanField(
        default=True,
        help_text="Send notification to admin emails",
    )

    # Document Type Toggles
    notify_national_id = models.BooleanField(
        default=True,
        help_text="Send notifications for National ID documents",
    )
    notify_license = models.BooleanField(
        default=True,
        help_text="Send notifications for License documents",
    )
    notify_vehicle_license = models.BooleanField(
        default=True,
        help_text="Send notifications for Vehicle License documents",
    )
    notify_contract = models.BooleanField(
        default=True,
        help_text="Send notifications for Contract documents",
    )

    # Schedule Settings
    check_schedule_cron = models.CharField(
        max_length=100,
        default="0 9 * * *",
        help_text="Cron expression for check schedule (default: daily at 9 AM). Auto-syncs with Celery Beat periodic task. Format: 'minute hour day month day_of_week'",
    )

    # Cooldown Settings
    notification_cooldown_days = models.PositiveIntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days to wait before sending duplicate individual notifications (NOTE: Each document gets max 2 emails total)",
    )
    admin_digest_cooldown_hours = models.PositiveIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        help_text="Hours to wait before sending duplicate admin digest emails",
    )

    # General Settings
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable all notifications",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Configuration"
        verbose_name_plural = "Notification Configuration"

    def __str__(self):
        return f"Notification Config (Active: {self.is_active})"

    def save(self, *args, **kwargs):
        """
        Ensure only one configuration exists (singleton pattern).
        Also sync the cron schedule with django_celery_beat periodic task.
        """
        if not self.pk and NotificationConfig.objects.exists():
            # Update existing config instead of creating new one
            self.pk = NotificationConfig.objects.first().pk
        
        result = super().save(*args, **kwargs)
        
        # Sync cron schedule with periodic task
        self._sync_periodic_task()
        
        return result
    
    def _sync_periodic_task(self):
        """
        Sync the cron schedule with django_celery_beat periodic task.
        Creates or updates the periodic task to match check_schedule_cron.
        """
        try:
            from django_celery_beat.models import PeriodicTask, CrontabSchedule
            
            # Parse cron expression (format: "minute hour day month day_of_week")
            cron_parts = self.check_schedule_cron.strip().split()
            if len(cron_parts) != 5:
                # Invalid cron expression, skip sync
                return
            
            minute, hour, day_of_month, month_of_year, day_of_week = cron_parts
            
            # Get or create the crontab schedule
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_month=day_of_month,
                month_of_year=month_of_year,
                day_of_week=day_of_week,
                timezone=timezone.get_current_timezone(),
            )
            
            # Get or create the periodic task
            task_name = "Check Document Expiration (Auto-synced)"
            task, created = PeriodicTask.objects.get_or_create(
                name=task_name,
                defaults={
                    'task': 'logims.notifications.tasks.check_document_expiration',
                    'crontab': schedule,
                    'enabled': self.is_active,
                }
            )
            
            # Update if already exists
            if not created:
                task.crontab = schedule
                task.enabled = self.is_active
                task.save()
                
        except ImportError:
            # django_celery_beat not installed, skip sync
            pass
        except Exception as e:
            # Log error but don't prevent saving config
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to sync periodic task: {e}")

    @classmethod
    def get_config(cls):
        """Get or create the notification configuration."""
        config, created = cls.objects.get_or_create(pk=1)
        return config


class NotificationLog(models.Model):
    """
    Log of sent notifications to avoid duplicates and track history.
    """

    NOTIFICATION_TYPE_CHOICES = [
        ("warning", "Warning (About to Expire)"),
        ("expired", "Expired"),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ("national_id", "National ID"),
        ("license", "License"),
        ("vehicle_license", "Vehicle License"),
        ("contract", "Contract"),
        ("admin_digest", "Admin Digest Email"),  # Special type for batch emails to admins
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    # Notification Details
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPE_CHOICES,
        help_text="Type of notification",
    )
    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPE_CHOICES,
        help_text="Type of document",
    )

    # Driver and Document Info
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    document_id = models.PositiveIntegerField(
        help_text="ID of the specific document (varies by type)",
    )
    expiry_date = models.DateField(
        help_text="Expiry date of the document at time of notification",
    )

    # Recipients
    recipients = ArrayField(
        models.EmailField(),
        default=list,
        help_text="List of email addresses that received this notification",
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if notification failed",
    )

    # Timestamps
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["driver", "document_type", "notification_type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            f"{self.get_notification_type_display()} - "
            f"{self.driver} - {self.get_document_type_display()} "
            f"({self.status})"
        )

    def mark_sent(self):
        """Mark notification as successfully sent."""
        self.status = "sent"
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_failed(self, error_message):
        """Mark notification as failed with error message."""
        self.status = "failed"
        self.error_message = error_message
        self.save(update_fields=["status", "error_message"])

    @classmethod
    def should_send_notification(cls, driver, document_type, notification_type, expiry_date):
        """
        Check if a notification should be sent based on logs.
        Each document should receive ONLY 2 emails:
        - 1 warning email (before expiry)
        - 1 expired email (after expiry)

        Returns True if this specific notification has never been sent.
        """
        # Check if we've EVER sent this exact notification
        # (driver + document_type + notification_type + expiry_date)
        already_sent = cls.objects.filter(
            driver=driver,
            document_type=document_type,
            notification_type=notification_type,
            expiry_date=expiry_date,
            status="sent",
        ).exists()

        return not already_sent

    @classmethod
    def should_send_admin_digest(cls, notification_type, hours_cooldown=None):
        """
        Check if an admin digest should be sent based on recent logs.
        Returns True if no admin digest was sent in the cooldown period.

        Args:
            notification_type: "warning" or "expired"
            hours_cooldown: Hours to wait before sending another digest (None = use config)
        """
        from datetime import timedelta

        # Use config value if not specified
        if hours_cooldown is None:
            from .models import NotificationConfig
            config = NotificationConfig.get_config()
            hours_cooldown = config.admin_digest_cooldown_hours

        cooldown_time = timezone.now() - timedelta(hours=hours_cooldown)

        # Check for recent admin digest of same type
        recent_digest = cls.objects.filter(
            document_type="admin_digest",
            notification_type=notification_type,
            status="sent",
            sent_at__gte=cooldown_time,
        ).exists()

        return not recent_digest

