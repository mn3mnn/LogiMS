"""Django admin configuration for notifications app."""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import NotificationConfig, NotificationLog


@admin.register(NotificationConfig)
class NotificationConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for Notification Configuration.
    Singleton model - only one instance should exist.
    """

    fieldsets = (
        (
            "General Settings",
            {
                "fields": (
                    "is_active",
                ),
                "description": "Enable/disable all notifications",
            },
        ),
        (
            "Schedule Settings",
            {
                "fields": (
                    "check_schedule_cron",
                ),
                "description": (
                    "Configure when to check for expiring documents. "
                    "This automatically syncs with Celery Beat periodic task. "
                    "Format: 'minute hour day month day_of_week'. "
                    "Examples: '0 9 * * *' (daily 9 AM), '0 */6 * * *' (every 6 hours), '0 0 * * 1' (every Monday midnight)"
                ),
            },
        ),
        (
            "Email Recipients",
            {
                "fields": (
                    "admin_emails",
                    "notify_driver",
                    "notify_admins",
                ),
                "description": "Configure who receives notifications. Admin emails can be any valid email addresses (Gmail, Outlook, company emails, etc.)",
            },
        ),
        (
            "Email Settings",
            {
                "fields": (
                    "from_email",
                    "email_subject_prefix",
                ),
                "description": "Configure email sender and subject",
            },
        ),
        (
            "Notification Timing",
            {
                "fields": (
                    "warning_days_before_expiry",
                    "notification_cooldown_days",
                    "admin_digest_cooldown_hours",
                ),
                "description": "Configure when to send expiration warnings and cooldown periods. NOTE: Each document receives exactly 2 emails (1 warning + 1 expired).",
            },
        ),
        (
            "Notification Types",
            {
                "fields": (
                    "notify_on_warning",
                    "notify_on_expired",
                ),
                "description": "Enable/disable specific notification types",
            },
        ),
        (
            "Document Types",
            {
                "fields": (
                    "notify_national_id",
                    "notify_license",
                    "notify_vehicle_license",
                    "notify_contract",
                ),
                "description": "Enable/disable notifications for specific document types",
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    list_display = (
        "id",
        "is_active_badge",
        "warning_days_display",
        "notification_types_display",
        "recipient_types_display",
        "updated_at",
    )

    def is_active_badge(self, obj):
        """Display active status as colored badge."""
        if obj.is_active:
            return format_html(
                '<span style="color: white; background-color: green; '
                'padding: 3px 10px; border-radius: 3px;">✓ Active</span>'
            )
        return format_html(
            '<span style="color: white; background-color: red; '
            'padding: 3px 10px; border-radius: 3px;">✗ Inactive</span>'
        )

    is_active_badge.short_description = "Status"

    def warning_days_display(self, obj):
        """Display warning days configuration."""
        return f"{obj.warning_days_before_expiry} days"

    warning_days_display.short_description = "Warning Period"

    def notification_types_display(self, obj):
        """Display enabled notification types."""
        types = []
        if obj.notify_on_warning:
            types.append("Warning")
        if obj.notify_on_expired:
            types.append("Expired")
        return ", ".join(types) if types else "None"

    notification_types_display.short_description = "Notification Types"

    def recipient_types_display(self, obj):
        """Display enabled recipient types."""
        recipients = []
        if obj.notify_driver:
            recipients.append("Drivers")
        if obj.notify_admins:
            recipients.append(f"Admins ({len(obj.admin_emails)})")
        return ", ".join(recipients) if recipients else "None"

    recipient_types_display.short_description = "Recipients"

    def has_add_permission(self, request):
        """Only allow adding if no config exists."""
        return not NotificationConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of the configuration."""
        return False

    class Meta:
        verbose_name = "Notification Configuration"
        verbose_name_plural = "Notification Configuration"


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """
    Admin interface for Notification Logs.
    Read-only interface for viewing notification history.
    """

    list_display = (
        "id",
        "driver_link",
        "document_type_display",
        "notification_type_display",
        "status_badge",
        "expiry_date",
        "recipients_count",
        "sent_at",
        "created_at",
    )

    list_filter = (
        "status",
        "notification_type",
        "document_type",
        "created_at",
        "sent_at",
    )

    search_fields = (
        "driver__first_name",
        "driver__last_name",
        "driver__nid",
        "driver__email",
        "recipients",
    )

    readonly_fields = (
        "notification_type",
        "document_type",
        "driver",
        "document_id",
        "expiry_date",
        "recipients",
        "status",
        "error_message",
        "sent_at",
        "created_at",
    )

    fieldsets = (
        (
            "Notification Details",
            {
                "fields": (
                    "notification_type",
                    "document_type",
                    "status",
                ),
            },
        ),
        (
            "Driver & Document",
            {
                "fields": (
                    "driver",
                    "document_id",
                    "expiry_date",
                ),
            },
        ),
        (
            "Recipients & Status",
            {
                "fields": (
                    "recipients",
                    "error_message",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "sent_at",
                    "created_at",
                ),
            },
        ),
    )

    ordering = ("-created_at",)

    def driver_link(self, obj):
        """Display driver name as link to driver admin page."""
        url = reverse("admin:drivers_driver_change", args=[obj.driver.id])
        return format_html('<a href="{}">{}</a>', url, obj.driver)

    driver_link.short_description = "Driver"

    def document_type_display(self, obj):
        """Display document type with icon."""
        icons = {
            "national_id": "🆔",
            "license": "🚗",
            "vehicle_license": "🚙",
            "contract": "📄",
        }
        icon = icons.get(obj.document_type, "📋")
        return f"{icon} {obj.get_document_type_display()}"

    document_type_display.short_description = "Document Type"

    def notification_type_display(self, obj):
        """Display notification type with icon."""
        if obj.notification_type == "warning":
            return format_html(
                '<span style="color: orange;">⚠️ {}</span>',
                obj.get_notification_type_display(),
            )
        return format_html(
            '<span style="color: red;">🚨 {}</span>',
            obj.get_notification_type_display(),
        )

    notification_type_display.short_description = "Type"

    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            "pending": "gray",
            "sent": "green",
            "failed": "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: white; background-color: {}; '
            'padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def recipients_count(self, obj):
        """Display count of recipients."""
        count = len(obj.recipients)
        return format_html(
            '<span title="{}">{} recipient{}</span>',
            ", ".join(obj.recipients),
            count,
            "s" if count != 1 else "",
        )

    recipients_count.short_description = "Recipients"

    def has_add_permission(self, request):
        """Disable manual creation of logs."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup."""
        return True

    def has_change_permission(self, request, obj=None):
        """Make logs read-only."""
        return False

    class Meta:
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"

