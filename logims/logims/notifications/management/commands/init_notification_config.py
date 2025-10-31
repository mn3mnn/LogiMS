"""Management command to initialize notification configuration."""

from django.core.management.base import BaseCommand
from logims.notifications.models import NotificationConfig


class Command(BaseCommand):
    help = "Initialize notification configuration with default values"

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-email",
            nargs="+",
            type=str,
            help="Admin email addresses to add to configuration",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Initializing notification configuration..."))

        # Get or create config
        config = NotificationConfig.get_config()

        # Update admin emails if provided
        if options.get("admin_email"):
            config.admin_emails = options["admin_email"]
            config.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Added admin emails: {', '.join(options['admin_email'])}"
                )
            )

        # Display current configuration
        self.stdout.write("\nCurrent Configuration:")
        self.stdout.write(f"  Active: {config.is_active}")
        self.stdout.write(f"  Warning days: {config.warning_days_before_expiry}")
        self.stdout.write(f"  Admin emails: {', '.join(config.admin_emails) if config.admin_emails else 'None'}")
        self.stdout.write(f"  Email subject prefix: {config.email_subject_prefix}")
        self.stdout.write(f"  From email: {config.from_email or 'Default'}")
        self.stdout.write(f"  Check schedule: {config.check_schedule_cron}")

        self.stdout.write("\nNotification Types:")
        self.stdout.write(f"  Warning: {config.notify_on_warning}")
        self.stdout.write(f"  Expired: {config.notify_on_expired}")

        self.stdout.write("\nRecipients:")
        self.stdout.write(f"  Notify drivers: {config.notify_driver}")
        self.stdout.write(f"  Notify admins: {config.notify_admins}")

        self.stdout.write("\nDocument Types:")
        self.stdout.write(f"  National ID: {config.notify_national_id}")
        self.stdout.write(f"  License: {config.notify_license}")
        self.stdout.write(f"  Vehicle License: {config.notify_vehicle_license}")
        self.stdout.write(f"  Contract: {config.notify_contract}")

        self.stdout.write(
            self.style.SUCCESS("\n✅ Configuration initialized successfully")
        )
        self.stdout.write(
            "\n💡 You can modify these settings in the Django admin interface"
        )

