"""
Django admin configuration for uploads models.
Merged from core and documents modules.
"""
from django.contrib import admin
from .models import (
    FileUpload, Tag, FileUploadAudit,
    DocumentUploadMetadata
)


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ['title', 'file_type', 'status', 'processed_records_count', 'created_by', 'created_at']
    list_filter = ['file_type', 'status', 'created_at']
    search_fields = ['title', 'file']
    readonly_fields = ['processing_started_at', 'processing_completed_at', 'created_at', 'updated_at']
    filter_horizontal = ['tags']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_predefined', 'created_at']
    list_filter = ['is_predefined']
    search_fields = ['name']


@admin.register(FileUploadAudit)
class FileUploadAuditAdmin(admin.ModelAdmin):
    list_display = ['file_upload_id', 'file_title', 'action', 'username', 'timestamp']
    list_filter = ['action', 'file_type', 'timestamp']
    search_fields = ['file_title', 'username', 'file_upload_id']
    readonly_fields = ['file_upload_id', 'file_title', 'file_type', 'action', 'user_id', 'username', 'timestamp']
    ordering = ['-timestamp']


# Document models admin (merged from documents module)

@admin.register(DocumentUploadMetadata)
class DocumentUploadMetadataAdmin(admin.ModelAdmin):
    list_display = ['file_upload', 'company', 'from_date', 'to_date', 'amount']
    list_filter = ['company']
    search_fields = ['file_upload__title', 'company__name']


