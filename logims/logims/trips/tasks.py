"""
Celery tasks for trip file processing.
"""
from celery import shared_task
from django.conf import settings
from django.utils import timezone
import logging
import time

from logims.uploads.models import FileUpload, FileUploadAudit, ProcessingStatus, FileType
from .services.trip_processor import TripProcessingService
from logims.contrib.logging_utils import ContextLogger, log_error

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_trip_file_task(self, file_upload_id):
    """Celery task to process trip file asynchronously"""
    start_time = time.time()

    logger.info(
        f"Trip file processing task started | file_upload_id={file_upload_id} | "
        f"task_id={self.request.id}"
    )

    try:
        # Get the file upload instance with lock (wrap in transaction for select_for_update)
        from django.db import transaction
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

        # Continue processing outside the lock
        metadata = file_upload.metadata
        if not metadata:
            raise ValueError(f"DocumentUploadMetadata not found for file_upload_id={file_upload_id}")

        company_name = metadata.company.name if metadata.company else "No Company"
        logger.info(
            f"Trip file upload retrieved | file_upload_id={file_upload_id} | "
            f"company={company_name}"
        )

        # Log audit trail
        from logims.uploads.services.file_upload_service import FileUploadService
        FileUploadService.log_audit(file_upload, 'processing_started')

        with ContextLogger(
            logger,
            "Trip file processing",
            file_upload_id=file_upload_id,
            company=company_name,
            file_type=FileType.TRIPS
        ):
            service = TripProcessingService(file_upload)
            records_count, status_message = service.process()

        processing_time = time.time() - start_time

        logger.info(
            f"Trip file processing completed successfully | "
            f"file_upload_id={file_upload.id} | "
            f"records_processed={records_count} | "
            f"processing_time={processing_time:.2f}s"
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
        error_msg = f"Error processing trip file {file_upload_id}: {str(exc)}"

        log_error(
            exc,
            context="Trip file processing failed",
            file_upload_id=file_upload_id,
            processing_time=f"{processing_time:.2f}s",
            retry_attempt=self.request.retries
        )

        try:
            file_upload = FileUpload.objects.get(id=file_upload_id)
            file_upload.mark_processing_failed(error_msg)
            from logims.uploads.services.file_upload_service import FileUploadService
            FileUploadService.log_audit(file_upload, 'processing_failed')
        except FileUpload.DoesNotExist:
            pass


        if self.request.retries < self.max_retries:
            retry_countdown = 60 * (2 ** self.request.retries)
            raise self.retry(countdown=retry_countdown)

        return {
            'file_upload_id': file_upload_id,
            'status': 'error',
            'message': error_msg,
            'processing_time': processing_time
        }

