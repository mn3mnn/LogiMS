"""
File upload service layer.
Handles business logic for file upload operations.
"""
import logging
from typing import Dict, List, Tuple, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from logims.users.models import User
else:
    from django.contrib.auth import get_user_model
    User = get_user_model()

from django.db import transaction

from ..models import FileUpload, FileUploadAudit, FileType, ProcessingStatus
from logims.contrib.logging_utils import log_model_change, log_error

logger = logging.getLogger(__name__)

# Constants
PROCESSABLE_FILE_TYPES = [
    FileType.PAYMENTS,
    FileType.TRIPS,
    FileType.EXPENSES,
]


class FileUploadService:
    """Service for file upload business logic"""

    @staticmethod
    def get_company_name(file_upload: FileUpload) -> Optional[str]:
        """
        Get company name from metadata.

        Args:
            file_upload: FileUpload instance

        Returns:
            Company name or None if not available
        """
        if hasattr(file_upload, 'metadata') and file_upload.metadata and file_upload.metadata.company:
            return file_upload.metadata.company.name
        return None

    @staticmethod
    def get_original_metadata(file_upload: FileUpload) -> Dict[str, Any]:
        """
        Extract original metadata values for change detection.

        Args:
            file_upload: FileUpload instance

        Returns:
            Dictionary of original metadata values
        """
        original_data = {
            'title': file_upload.title,
            'file_type': file_upload.file_type,
        }

        if hasattr(file_upload, 'metadata') and file_upload.metadata:
            metadata = file_upload.metadata
            if file_upload.file_type in [FileType.PAYMENTS, FileType.TRIPS]:
                original_data['company_id'] = metadata.company_id if metadata.company else None
                original_data['from_date'] = metadata.from_date
                original_data['to_date'] = metadata.to_date
            elif file_upload.file_type in [FileType.EXPENSES, FileType.CONTRACTS, FileType.OTHER]:
                original_data['amount'] = metadata.amount

        return original_data

    @staticmethod
    def check_metadata_changes(
        file_upload: FileUpload,
        request_data: Dict[str, Any],
        original_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Check if metadata fields that require reprocessing have changed.

        Args:
            file_upload: FileUpload instance
            request_data: Request data dictionary
            original_data: Original metadata dictionary

        Returns:
            Tuple of (should_reprocess, changed_fields)
        """
        should_reprocess = False
        changed_fields = []

        if file_upload.file_type in [FileType.PAYMENTS, FileType.TRIPS]:
            metadata = getattr(file_upload, 'metadata', None)
            if not metadata:
                return should_reprocess, changed_fields

            current_company_id = metadata.company_id if metadata.company else None
            current_from_date = metadata.from_date
            current_to_date = metadata.to_date

            # Check company change
            if 'company' in request_data:
                new_company_id = request_data.get('company')
                if new_company_id and int(new_company_id) != original_data.get('company_id'):
                    should_reprocess = True
                    changed_fields.append('company')

            # Check date changes
            if 'from_date' in request_data and current_from_date != original_data.get('from_date'):
                should_reprocess = True
                changed_fields.append('from_date')

            if 'to_date' in request_data and current_to_date != original_data.get('to_date'):
                should_reprocess = True
                changed_fields.append('to_date')

        return should_reprocess, changed_fields

    @staticmethod
    def check_file_changed(request_data: Dict[str, Any]) -> bool:
        """
        Check if file was changed in request.

        Args:
            request_data: Request data dictionary

        Returns:
            True if file was changed, False otherwise
        """
        if 'file' in request_data:
            file_obj = request_data.get('file')
            if file_obj and hasattr(file_obj, 'read'):
                return True
        return False

    @staticmethod
    def queue_processing_task(file_upload: FileUpload, changed_fields: Optional[List[str]] = None) -> None:
        """
        Queue the appropriate processing task based on file type.
        Used for both initial processing and reprocessing.

        Args:
            file_upload: FileUpload instance to process
            changed_fields: Optional list of changed fields (for reprocessing logging)
        """
        task_map = {
            FileType.PAYMENTS: ('logims.payroll.tasks', 'process_payment_file_task'),
            FileType.TRIPS: ('logims.trips.tasks', 'process_trip_file_task'),
            FileType.EXPENSES: ('logims.uploads.tasks', 'process_document_file_task'),
            FileType.CONTRACTS: ('logims.uploads.tasks', 'process_document_file_task'),
            FileType.OTHER: ('logims.uploads.tasks', 'process_document_file_task'),
        }

        module_path, task_name = task_map.get(file_upload.file_type)
        if not module_path:
            if changed_fields:
                logger.warning(f"No reprocessing task found for file_type={file_upload.file_type}")
            return

        module = __import__(module_path, fromlist=[task_name])
        task = getattr(module, task_name)

        transaction.on_commit(lambda: task.delay(file_upload.id))

        if changed_fields:
            logger.info(
                f"Reprocessing queued | file_upload_id={file_upload.id} | "
                f"file_type={file_upload.file_type} | changed_fields={changed_fields} | "
                f"file_changed={'file' in changed_fields}"
            )
        else:
            logger.info(
                f"Processing queued | file_upload_id={file_upload.id} | "
                f"file_type={file_upload.file_type}"
            )

    @staticmethod
    def prepare_for_reprocessing(file_upload: FileUpload):
        """Reset file upload status to allow reprocessing"""
        file_upload.status = ProcessingStatus.PENDING
        file_upload.error_message = None
        file_upload.processed_records_count = 0
        file_upload.processing_started_at = None
        file_upload.processing_completed_at = None
        file_upload.save(update_fields=[
            'status', 'error_message', 'processed_records_count',
            'processing_started_at', 'processing_completed_at'
        ])

    @staticmethod
    def log_audit(file_upload: FileUpload, action: str, user: Optional[User] = None) -> None:
        """
        Log audit trail entry with denormalized data.
        Preserves history even if file or user is deleted.

        Args:
            file_upload: FileUpload instance
            action: Action performed (e.g., 'created', 'updated', 'deleted')
            user: Optional user who performed the action
        """
        FileUploadAudit.objects.create(
            file_upload_id=file_upload.id,
            file_title=file_upload.title,
            file_type=file_upload.file_type,
            action=action,
            user_id=user.id if user else None,
            username=user.username if user else None
        )

    @staticmethod
    def log_file_upload_operation(
        file_upload: FileUpload,
        action: str,
        user: User,
        operation_type: str = "FileUpload"
    ) -> None:
        """
        Log file upload operation using logging utils.

        Args:
            file_upload: FileUpload instance
            action: Action performed
            user: User who performed the action
            operation_type: Type of operation (default: "FileUpload")
        """
        company_name = FileUploadService.get_company_name(file_upload)
        log_model_change(
            action=action,
            model_name=operation_type,
            instance_id=file_upload.id,
            user=user,
            company=company_name or "N/A",
            file_type=file_upload.file_type
        )

    @staticmethod
    def should_reprocess(
        file_upload: FileUpload,
        request_data: Dict[str, Any],
        original_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Determine if file upload should be reprocessed based on changes.

        Args:
            file_upload: FileUpload instance
            request_data: Request data dictionary
            original_data: Original metadata dictionary

        Returns:
            Tuple of (should_reprocess, changed_fields)
        """
        should_reprocess = False
        changed_fields = []

        # Check if file was changed (new file uploaded)
        if FileUploadService.check_file_changed(request_data):
            should_reprocess = True
            changed_fields.append('file')
            logger.info(
                f"File change detected | file_upload_id={file_upload.id} | "
                f"old_file={file_upload.file.name if file_upload.file else 'None'} | "
                f"new_file={getattr(request_data.get('file'), 'name', 'unknown')}"
            )

        # Check metadata changes
        metadata_reprocess, metadata_changed = FileUploadService.check_metadata_changes(
            file_upload, request_data, original_data
        )
        should_reprocess = should_reprocess or metadata_reprocess
        changed_fields.extend(metadata_changed)

        # Check if title changed (informational only)
        if 'title' in request_data and request_data['title'] != original_data.get('title'):
            changed_fields.append('title')

        return should_reprocess, changed_fields

    @staticmethod
    def prepare_and_queue_reprocessing(
        file_upload: FileUpload,
        changed_fields: List[str],
        user: User
    ) -> None:
        """
        Prepare file upload for reprocessing and queue the task.

        Args:
            file_upload: FileUpload instance
            changed_fields: List of fields that changed
            user: User instance for logging
        """
        if file_upload.file_type not in PROCESSABLE_FILE_TYPES:
            # Contracts and other types don't require processing, but mark as completed
            file_upload.status = ProcessingStatus.COMPLETED
            file_upload.processed_records_count = 0
            file_upload.save(update_fields=['status', 'processed_records_count'])
            logger.info(
                f"File type {file_upload.file_type} does not require processing | file_upload_id={file_upload.id}"
            )
            return

        # Reset file upload status
        FileUploadService.prepare_for_reprocessing(file_upload)

        # Log reprocessing trigger
        FileUploadService.log_audit(file_upload, 'reprocess_queued', user)

        # Queue reprocessing task
        FileUploadService.queue_processing_task(file_upload, changed_fields)

