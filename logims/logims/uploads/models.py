"""
Uploads models for file uploads and document management.
Merged from core and documents modules.
"""
from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone

from logims.storage_backends import R2MediaStorage


class FileType(models.TextChoices):
    """File type choices"""
    PAYMENTS = "payments", "Payments/Payroll"
    TRIPS = "trips", "Trip Details"
    EXPENSES = "expenses", "Expenses"
    CONTRACTS = "contracts", "Contracts"
    OTHER = "other", "Other"


class ProcessingStatus(models.TextChoices):
    """Processing status choices"""
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Tag(models.Model):
    """Model for document tags"""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Tag name"
    )
    is_predefined = models.BooleanField(
        default=False,
        help_text="Whether this is a predefined system tag"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_predefined']),
        ]

    def __str__(self):
        return self.name


class FileUpload(models.Model):
    """
    Unified FileUpload model for all upload types.

    This is the frontend-facing model. Type-specific metadata is stored
    in a unified metadata table (DocumentUploadMetadata)
    using composition pattern.
    """

    title = models.CharField(
        max_length=255,
        help_text="Title or description of the document"
    )
    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        help_text="Type of document"
    )
    file = models.FileField(
        upload_to="file_uploads/%Y/%m/%d/",
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv',
                              'jpg', 'jpeg', 'png', 'zip', 'rar']
        )],
        storage=R2MediaStorage(),  # Store uploaded files in R2
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="file_uploads",
        help_text="Tags for categorizing documents"
    )
    status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    processed_records_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_files"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['file_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_file_type_display()})"

    def delete(self, using=None, keep_parents=False):
        """
        Ensure the underlying uploaded file is deleted from storage when the
        FileUpload record is deleted via the admin or API.
        """
        if self.file:
            self.file.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)

    def mark_processing_started(self):
        """Mark file as processing started"""
        self.status = ProcessingStatus.PROCESSING
        self.processing_started_at = timezone.now()
        self.save(update_fields=['status', 'processing_started_at'])

    def mark_processing_completed(self, records_count=0):
        """Mark file as processing completed"""
        self.status = ProcessingStatus.COMPLETED
        self.processing_completed_at = timezone.now()
        self.processed_records_count = records_count
        self.save(update_fields=['status', 'processing_completed_at', 'processed_records_count'])

    def mark_processing_failed(self, error_message):
        """Mark file as processing failed"""
        self.status = ProcessingStatus.FAILED
        self.processing_completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'processing_completed_at', 'error_message'])


class FileUploadAudit(models.Model):
    """
    Audit trail for FileUpload operations.
    Stores denormalized data to preserve history even if file/user is deleted.
    Tracks who, when, and what action was performed.
    """

    # Store file_upload_id instead of ForeignKey to preserve history on deletion
    file_upload_id = models.IntegerField(
        db_index=True,
        help_text="ID of the file upload (may reference deleted file)"
    )
    file_title = models.CharField(
        max_length=255,
        help_text="Title of the file upload at time of action"
    )
    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        help_text="Type of file at time of action"
    )

    action = models.CharField(
        max_length=50,
        help_text="Action performed (e.g., 'created', 'updated', 'deleted', 'processing_started', 'processing_completed', 'processing_failed')"
    )

    # Store user info instead of ForeignKey to preserve history on deletion
    user_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the user who performed the action (may reference deleted user)"
    )
    username = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Username at time of action"
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['file_upload_id', 'timestamp']),
            models.Index(fields=['action']),
            models.Index(fields=['user_id', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.file_title} (ID: {self.file_upload_id}) - {self.action} at {self.timestamp}"


# Unified metadata model for all file upload types

class DocumentUploadMetadata(models.Model):
    """
    Unified metadata model for all file upload types (payments, trips, expenses, contracts, other).
    Uses composition pattern with FileUpload.
    The file_type is determined by FileUpload.file_type, so we don't need document_type here.
    """
    file_upload = models.OneToOneField(
        FileUpload,
        on_delete=models.CASCADE,
        related_name="metadata"
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="file_upload_metadata",
        help_text="Company (for payments and trips)"
    )
    from_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date for the period (for payments and trips)"
    )
    to_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date for the period (for payments and trips)"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount"
    )

    class Meta:
        indexes = [
            models.Index(fields=['company', 'from_date', 'to_date']),
        ]

    def __str__(self):
        if self.company:
            return f"{self.file_upload.title} - {self.company.name} ({self.from_date} to {self.to_date})"
        elif self.amount:
            return f"{self.file_upload.title} - Amount: {self.amount}"
        return f"{self.file_upload.title} - {self.file_upload.get_file_type_display()}"


