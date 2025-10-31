"""Management command to test email sending with detailed diagnostics."""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class Command(BaseCommand):
    help = "Test email configuration and sending (all methods)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            type=str,
            default="abdoeladawy4@gmail.com",
            help="Email address to send test emails to",
        )
        parser.add_argument(
            "--skip-smtp",
            action="store_true",
            help="Skip direct SMTP test",
        )

    def handle(self, *args, **options):
        recipient = options["to"]
        skip_smtp = options.get("skip_smtp", False)
        
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("📧 EMAIL CONFIGURATION & SENDING TEST\n"))
        
        # PART 1: Configuration Review
        self.review_configuration()
        
        # PART 2: Direct SMTP Test
        if not skip_smtp:
            self.test_direct_smtp(recipient)
        
        # PART 3: Django send_mail() Test
        self.test_django_send_mail(recipient)
        
        # PART 4: EmailMultiAlternatives Test (LogiMS method)
        self.test_email_multi_alternatives(recipient)
        
        # Summary
        self.print_summary(recipient)

    def review_configuration(self):
        """Review current email configuration."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("PART 1: Configuration Review")
        self.stdout.write("=" * 80 + "\n")
        
        config = {
            'EMAIL_BACKEND': settings.EMAIL_BACKEND,
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_PORT': settings.EMAIL_PORT,
            'EMAIL_USE_TLS': settings.EMAIL_USE_TLS,
            'EMAIL_USE_SSL': settings.EMAIL_USE_SSL,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': '***' + settings.EMAIL_HOST_PASSWORD[-4:] if settings.EMAIL_HOST_PASSWORD else 'NOT SET',
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
        }
        
        for key, value in config.items():
            self.stdout.write(f"  {key:25s} = {value}")
        
        self.stdout.write("")
        
        # Validation
        if settings.EMAIL_PORT == 465 and settings.EMAIL_USE_SSL:
            self.stdout.write(self.style.SUCCESS("  ✓ Port 465 with SSL - Correct"))
        elif settings.EMAIL_PORT == 587 and settings.EMAIL_USE_TLS:
            self.stdout.write(self.style.SUCCESS("  ✓ Port 587 with TLS - Correct"))
        else:
            self.stdout.write(self.style.WARNING(
                f"  ⚠️  Port {settings.EMAIL_PORT} with SSL={settings.EMAIL_USE_SSL}, TLS={settings.EMAIL_USE_TLS}"
            ))

    def test_direct_smtp(self, recipient):
        """Test direct SMTP connection."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("PART 2: Direct SMTP Connection Test")
        self.stdout.write("=" * 80 + "\n")
        
        try:
            host = settings.EMAIL_HOST
            port = settings.EMAIL_PORT
            user = settings.EMAIL_HOST_USER
            password = settings.EMAIL_HOST_PASSWORD
            
            self.stdout.write(f"Connecting to {host}:{port}...")
            
            if settings.EMAIL_USE_SSL:
                smtp = smtplib.SMTP_SSL(host, port, timeout=10)
                self.stdout.write(self.style.SUCCESS("  ✓ SSL connection established"))
            else:
                smtp = smtplib.SMTP(host, port, timeout=10)
                self.stdout.write(self.style.SUCCESS("  ✓ Connection established"))
                if settings.EMAIL_USE_TLS:
                    smtp.starttls()
                    self.stdout.write(self.style.SUCCESS("  ✓ TLS established"))
            
            self.stdout.write(f"Authenticating as {user}...")
            smtp.login(user, password)
            self.stdout.write(self.style.SUCCESS("  ✓ Authentication successful"))
            
            self.stdout.write("Sending test email...")
            msg = MIMEText("Test email via direct SMTP")
            msg['Subject'] = "Test - Direct SMTP"
            msg['From'] = user
            msg['To'] = recipient
            
            smtp.send_message(msg)
            smtp.quit()
            
            self.stdout.write(self.style.SUCCESS("  ✓ Email sent via direct SMTP\n"))
            self.stdout.write(self.style.SUCCESS("✅ PART 2 PASSED\n"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ❌ ERROR: {e}\n"))

    def test_django_send_mail(self, recipient):
        """Test Django's send_mail() function."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("PART 3: Django send_mail() Test")
        self.stdout.write("=" * 80 + "\n")
        
        try:
            result = send_mail(
                subject="Test - Django send_mail()",
                message="This is a test using Django's send_mail() function.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            
            if result == 1:
                self.stdout.write(self.style.SUCCESS("  ✓ Email sent successfully\n"))
                self.stdout.write(self.style.SUCCESS("✅ PART 3 PASSED\n"))
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Returned: {result}\n"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ❌ ERROR: {e}\n"))

    def test_email_multi_alternatives(self, recipient):
        """Test EmailMultiAlternatives - the method used in LogiMS."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("PART 4: EmailMultiAlternatives Test (LogiMS Method)")
        self.stdout.write("=" * 80 + "\n")
        
        try:
            text_content = "This is the plain text version.\n\nLogiMS uses EmailMultiAlternatives."
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; padding: 20px; }}
                    .container {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                    .success {{ color: green; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>✅ Test Email - LogiMS Method</h2>
                    <p class="success">This is the HTML version!</p>
                    <p>From: {settings.DEFAULT_FROM_EMAIL}</p>
                    <p>Server: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}</p>
                    <p>Method: <strong>EmailMultiAlternatives</strong></p>
                </div>
            </body>
            </html>
            """
            
            msg = EmailMultiAlternatives(
                subject="Test - LogiMS EmailMultiAlternatives",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            )
            msg.attach_alternative(html_content, "text/html")
            
            self.stdout.write("Sending EmailMultiAlternatives (HTML + plain text)...")
            result = msg.send(fail_silently=False)
            
            if result == 1:
                self.stdout.write(self.style.SUCCESS("  ✓ Email sent successfully\n"))
                self.stdout.write(self.style.SUCCESS("✅ PART 4 PASSED - This is how LogiMS sends emails!\n"))
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Returned: {result}\n"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ❌ ERROR: {e}\n"))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

    def print_summary(self, recipient):
        """Print test summary."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("📊 SUMMARY\n"))
        self.stdout.write("=" * 80 + "\n")
        
        self.stdout.write("Tested Methods:")
        self.stdout.write("  1. Direct SMTP (raw Python)")
        self.stdout.write("  2. Django send_mail() (simple)")
        self.stdout.write("  3. EmailMultiAlternatives (LogiMS uses this)")
        self.stdout.write("")
        self.stdout.write(f"Check {recipient} inbox (and spam folder)")
        self.stdout.write("You should receive 3 test emails")
        self.stdout.write("")
        self.stdout.write("=" * 80)

