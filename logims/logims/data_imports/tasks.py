from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging

from .models import FileUpload
from .processors.factory import ProcessorFactory

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_excel_file(self, file_upload_id):
    """
    Celery task to process Excel file asynchronously

    Args:
        file_upload_id: ID of the FileUpload instance to process

    Returns:
        dict: Processing results
    """
    try:
        # Get the file upload instance
        file_upload = FileUpload.objects.get(id=file_upload_id)

        # Get the appropriate processor for the company
        processor = ProcessorFactory.get_processor(file_upload)

        # Process the file
        records_count, status_message = processor.process_file()

        logger.info(
            f"Successfully processed file {file_upload.id} for company {file_upload.company.name}. "
            f"Records processed: {records_count}"
        )

        # Send notification email if configured
        if hasattr(settings, 'SEND_PROCESSING_NOTIFICATIONS') and settings.SEND_PROCESSING_NOTIFICATIONS:
            send_processing_notification.delay(file_upload_id, 'success')

        return {
            'file_upload_id': file_upload_id,
            'status': 'success',
            'records_count': records_count,
            'message': status_message
        }

    except FileUpload.DoesNotExist:
        error_msg = f"FileUpload with id {file_upload_id} does not exist"
        logger.error(error_msg)
        return {
            'file_upload_id': file_upload_id,
            'status': 'error',
            'message': error_msg
        }

    except Exception as exc:
        error_msg = f"Error processing file {file_upload_id}: {str(exc)}"
        logger.error(error_msg, exc_info=True)

        # Mark file as failed
        try:
            file_upload = FileUpload.objects.get(id=file_upload_id)
            file_upload.mark_processing_failed(error_msg)
        except FileUpload.DoesNotExist:
            pass

        # Send notification email if configured
        if hasattr(settings, 'SEND_PROCESSING_NOTIFICATIONS') and settings.SEND_PROCESSING_NOTIFICATIONS:
            send_processing_notification.delay(file_upload_id, 'error', error_msg)

        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying task for file {file_upload_id}, attempt {self.request.retries + 1}")
            raise self.retry(countdown=60 * (2 ** self.request.retries))  # Exponential backoff

        return {
            'file_upload_id': file_upload_id,
            'status': 'error',
            'message': error_msg
        }


@shared_task
def send_processing_notification(file_upload_id, status, error_message=None):
    """
    Send email notification about file processing status

    Args:
        file_upload_id: ID of the FileUpload instance
        status: 'success' or 'error'
        error_message: Error message if status is 'error'
    """
    try:
        file_upload = FileUpload.objects.get(id=file_upload_id)

        if status == 'success':
            subject = f"File Processing Completed - {file_upload.company.name}"
            message = f"""
            Your Excel file has been successfully processed.

            Company: {file_upload.company.name}
            File Type: {file_upload.get_file_type_display()}
            Period: {file_upload.from_date} to {file_upload.to_date}
            Records Processed: {file_upload.processed_records_count}
            Completed At: {file_upload.processing_completed_at}
            """
        else:
            subject = f"File Processing Failed - {file_upload.company.name}"
            message = f"""
            There was an error processing your Excel file.

            Company: {file_upload.company.name}
            File Type: {file_upload.get_file_type_display()}
            Period: {file_upload.from_date} to {file_upload.to_date}
            Error: {error_message}
            Failed At: {timezone.now()}
            """

        # Send email to the user who uploaded the file
        if file_upload.created_by and file_upload.created_by.email:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[file_upload.created_by.email],
                fail_silently=True,
            )

    except FileUpload.DoesNotExist:
        logger.error(f"FileUpload {file_upload_id} not found for notification")
    except Exception as e:
        logger.error(f"Failed to send notification for file {file_upload_id}: {str(e)}")


@shared_task
def cleanup_old_files(days_old=30):
    """
    Clean up old processed files to save storage space

    Args:
        days_old: Number of days after which to delete files
    """
    from datetime import timedelta
    from django.utils import timezone
    import os

    cutoff_date = timezone.now() - timedelta(days=days_old)
    old_files = FileUpload.objects.filter(
        status='completed',
        processing_completed_at__lt=cutoff_date
    )

    deleted_count = 0
    for file_upload in old_files:
        try:
            # Delete the physical file
            if file_upload.file and os.path.exists(file_upload.file.path):
                os.remove(file_upload.file.path)

            # Delete related records
            file_upload.payment_records.all().delete()
            file_upload.trip_records.all().delete()

            # Delete the file upload record
            file_upload.delete()
            deleted_count += 1

        except Exception as e:
            logger.error(f"Failed to delete file {file_upload.id}: {str(e)}")

    logger.info(f"Cleaned up {deleted_count} old files")
    return deleted_count
