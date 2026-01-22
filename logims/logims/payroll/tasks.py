"""
Celery tasks for payment file processing.
"""
from celery import shared_task
from django.conf import settings
from django.utils import timezone
import logging
import time

from logims.uploads.models import FileUpload, FileUploadAudit, ProcessingStatus, FileType
from .services.payment_processor import PaymentProcessingService
from logims.contrib.logging_utils import ContextLogger, log_error

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_payment_file_task(self, file_upload_id):
    """
    Celery task to process payment file asynchronously.

    Args:
        file_upload_id: ID of the FileUpload instance to process

    Returns:
        dict: Processing results
    """
    start_time = time.time()

    logger.info(
        f"Payment file processing task started | file_upload_id={file_upload_id} | "
        f"task_id={self.request.id}"
    )

    try:
        # Get the file upload instance with lock (wrap in transaction for select_for_update)
        from django.db import transaction

        # Get file upload with lock (small transaction just for the lock)
        with transaction.atomic():
            file_upload = FileUpload.objects.select_for_update().get(id=file_upload_id)
            # Check if already processed while holding the lock
            if file_upload.status == ProcessingStatus.COMPLETED:
                logger.info(f"File already processed | file_upload_id={file_upload_id}")
                return {
                    'file_upload_id': file_upload_id,
                    'status': 'already_processed',
                    'message': 'File was already processed'
                }

        # Continue processing outside the lock (processing has its own transaction)
        metadata = file_upload.metadata
        if not metadata:
            raise ValueError(f"DocumentUploadMetadata not found for file_upload_id={file_upload_id}")

        company_name = metadata.company.name if metadata.company else "No Company"
        logger.info(
            f"Payment file upload retrieved | file_upload_id={file_upload_id} | "
            f"company={company_name} | "
            f"from_date={metadata.from_date} | "
            f"to_date={metadata.to_date}"
        )

        # Log audit trail
        from logims.uploads.services.file_upload_service import FileUploadService
        FileUploadService.log_audit(file_upload, 'processing_started')

        # Process the file using context manager for structured logging
        with ContextLogger(
            logger,
            "Payment file processing",
            file_upload_id=file_upload_id,
            company=company_name,
            file_type=FileType.PAYMENTS
        ):
            service = PaymentProcessingService(file_upload)
            records_count, status_message = service.process()

        processing_time = time.time() - start_time

        logger.info(
            f"Payment file processing completed successfully | "
            f"file_upload_id={file_upload.id} | "
            f"company={company_name} | "
            f"records_processed={records_count} | "
            f"processing_time={processing_time:.2f}s | "
            f"status={status_message}"
        )

        # Log audit trail
        from logims.uploads.services.file_upload_service import FileUploadService
        FileUploadService.log_audit(file_upload, 'processing_completed')


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
        error_msg = f"Error processing payment file {file_upload_id}: {str(exc)}"

        log_error(
            exc,
            context="Payment file processing failed",
            file_upload_id=file_upload_id,
            processing_time=f"{processing_time:.2f}s",
            retry_attempt=self.request.retries
        )

        # Mark file as failed and log audit
        try:
            file_upload = FileUpload.objects.get(id=file_upload_id)
            file_upload.mark_processing_failed(error_msg)
            from logims.uploads.services.file_upload_service import FileUploadService
            FileUploadService.log_audit(file_upload, 'processing_failed')
            company_name = file_upload.metadata.company.name if file_upload.metadata and file_upload.metadata.company else "No Company"
            logger.info(
                f"Payment file upload marked as failed | file_upload_id={file_upload_id} | "
                f"company={company_name}"
            )
        except FileUpload.DoesNotExist:
            logger.error(f"Could not mark file as failed - not found | file_upload_id={file_upload_id}")

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
