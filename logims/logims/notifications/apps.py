from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logims.notifications"
    verbose_name = "Notifications"

    def ready(self):
        """Import signal handlers when app is ready."""
        try:
            import logims.notifications.signals  # noqa: F401
        except ImportError:
            pass

