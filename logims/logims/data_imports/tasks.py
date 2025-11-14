from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging
import time

from .models import FileUpload
from .processors.factory import ProcessorFactory
from logims.contrib.logging_utils import ContextLogger, log_error

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
    start_time = time.time()

    logger.info(
        f"File processing task started | file_upload_id={file_upload_id} | "
        f"task_id={self.request.id}"
    )

    try:
        # Get the file upload instance
        file_upload = FileUpload.objects.get(id=file_upload_id)

        logger.info(
            f"File upload retrieved | file_upload_id={file_upload_id} | "
            f"company={file_upload.company.name} | "
            f"file_type={file_upload.file_type} | "
            f"from_date={file_upload.from_date} | "
            f"to_date={file_upload.to_date}"
        )

        # Get the appropriate processor for the company
        processor = ProcessorFactory.get_processor(file_upload)

        logger.info(
            f"Processor obtained | file_upload_id={file_upload_id} | "
            f"processor_type={type(processor).__name__}"
        )

        # Process the file using context manager for structured logging
        with ContextLogger(
            logger,
            "File processing",
            file_upload_id=file_upload_id,
            company=file_upload.company.name,
            file_type=file_upload.file_type
        ):
            records_count, status_message = processor.process_file()

        processing_time = time.time() - start_time

        logger.info(
            f"File processing completed successfully | "
            f"file_upload_id={file_upload.id} | "
            f"company={file_upload.company.name} | "
            f"records_processed={records_count} | "
            f"processing_time={processing_time:.2f}s | "
            f"status={status_message}"
        )

        # Send notification email if configured
        if hasattr(settings, 'SEND_PROCESSING_NOTIFICATIONS') and settings.SEND_PROCESSING_NOTIFICATIONS:
            send_processing_notification.delay(file_upload_id, 'success')
            logger.debug(f"Processing notification queued | file_upload_id={file_upload_id}")

        return {
            'file_upload_id': file_upload_id,
            'status': 'success',
            'records_count': records_count,
            'message': status_message,
            'processing_time': processing_time
        }

    except FileUpload.DoesNotExist:
        error_msg = f"FileUpload with id {file_upload_id} does not exist"
        logger.error(f"File upload not found | file_upload_id={file_upload_id}")
        return {
            'file_upload_id': file_upload_id,
            'status': 'error',
            'message': error_msg
        }

    except Exception as exc:
        processing_time = time.time() - start_time
        error_msg = f"Error processing file {file_upload_id}: {str(exc)}"

        log_error(
            exc,
            context="File processing failed",
            file_upload_id=file_upload_id,
            processing_time=f"{processing_time:.2f}s",
            retry_attempt=self.request.retries
        )

        # Mark file as failed
        try:
            file_upload = FileUpload.objects.get(id=file_upload_id)
            file_upload.mark_processing_failed(error_msg)
            logger.info(
                f"File upload marked as failed | file_upload_id={file_upload_id} | "
                f"company={file_upload.company.name}"
            )
        except FileUpload.DoesNotExist:
            logger.error(f"Could not mark file as failed - not found | file_upload_id={file_upload_id}")

        # Send notification email if configured
        if hasattr(settings, 'SEND_PROCESSING_NOTIFICATIONS') and settings.SEND_PROCESSING_NOTIFICATIONS:
            send_processing_notification.delay(file_upload_id, 'error', error_msg)

        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            retry_countdown = 60 * (2 ** self.request.retries)
            logger.info(
                f"Scheduling retry | file_upload_id={file_upload_id} | "
                f"attempt={self.request.retries + 1}/{self.max_retries} | "
                f"countdown={retry_countdown}s"
            )
            raise self.retry(countdown=retry_countdown)  # Exponential backoff
        else:
            logger.error(
                f"Max retries exceeded | file_upload_id={file_upload_id} | "
                f"attempts={self.max_retries}"
            )

        return {
            'file_upload_id': file_upload_id,
            'status': 'error',
            'message': error_msg,
            'processing_time': processing_time
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
    logger.info(
        f"Sending processing notification | file_upload_id={file_upload_id} | "
        f"notification_status={status}"
    )

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
            logger.info(
                f"Notification email sent | file_upload_id={file_upload_id} | "
                f"recipient={file_upload.created_by.email} | status={status}"
            )
        else:
            logger.warning(
                f"No email recipient found | file_upload_id={file_upload_id} | "
                f"created_by={file_upload.created_by}"
            )

    except FileUpload.DoesNotExist:
        logger.error(f"FileUpload not found for notification | file_upload_id={file_upload_id}")
    except Exception as e:
        log_error(
            e,
            context="Failed to send processing notification",
            file_upload_id=file_upload_id,
            notification_status=status
        )

#
# @shared_task
# def cleanup_old_files(days_old=30):
#     """
#     Clean up old processed files to save storage space
#
#     Args:
#         days_old: Number of days after which to delete files
#     """
#     from datetime import timedelta
#     from django.utils import timezone
#     import os
#
#     logger.info(f"Starting file cleanup task | days_old={days_old}")
#
#     cutoff_date = timezone.now() - timedelta(days=days_old)
#     old_files = FileUpload.objects.filter(
#         status='completed',
#         processing_completed_at__lt=cutoff_date
#     )
#
#     total_files = old_files.count()
#     logger.info(f"Found {total_files} files to cleanup | cutoff_date={cutoff_date}")
#
#     deleted_count = 0
#     error_count = 0
#
#     for file_upload in old_files:
#         try:
#             file_id = file_upload.id
#             company = file_upload.company.name
#
#             # Delete the file via the configured storage backend
#             if file_upload.file:
#                 storage_name = file_upload.file.name
#                 file_upload.file.delete(save=False)
#                 logger.debug(f"Stored file deleted | name={storage_name}")
#
#             # Delete related records
#             payment_count = file_upload.payment_records.count()
#             trip_count = file_upload.trip_records.count()
#
#             file_upload.payment_records.all().delete()
#             file_upload.trip_records.all().delete()
#
#             # Delete the file upload record
#             file_upload.delete()
#             deleted_count += 1
#
#             logger.info(
#                 f"File cleaned up | file_id={file_id} | company={company} | "
#                 f"payment_records={payment_count} | trip_records={trip_count}"
#             )
#
#         except Exception as e:
#             error_count += 1
#             log_error(
#                 e,
#                 context="File cleanup failed",
#                 file_upload_id=file_upload.id,
#                 company=file_upload.company.name
#             )
#
#     logger.info(
#         f"File cleanup completed | total={total_files} | deleted={deleted_count} | "
#         f"errors={error_count} | days_old={days_old}"
#     )
#
#     return {
#         'total_files': total_files,
#         'deleted_count': deleted_count,
#         'error_count': error_count
#     }
