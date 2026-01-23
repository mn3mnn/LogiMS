"""
Serializers for unified FileUpload API.
"""
import os
from django.db import transaction
from rest_framework import serializers
from logims.uploads.models import FileUpload, Tag, FileType, DocumentUploadMetadata
from logims.companies.models import Company
from ..services.validation_service import FileUploadValidationService
from ..services.file_upload_service import FileUploadService


class TagSerializer(serializers.ModelSerializer):
    """Serializer for tags"""

    class Meta:
        model = Tag
        fields = ['id', 'name', 'is_predefined', 'created_at']
        read_only_fields = ['id', 'created_at']


class FileUploadSerializer(serializers.ModelSerializer):
    """Serializer for file upload operations"""

    file = serializers.FileField(required=False, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False
    )
    tag_details = TagSerializer(source='tags', many=True, read_only=True)

    # Dynamic fields based on file_type
    company = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    company_name = serializers.SerializerMethodField()
    from_date = serializers.DateField(write_only=True, required=False, allow_null=True)
    to_date = serializers.DateField(write_only=True, required=False, allow_null=True)
    amount = serializers.DecimalField(write_only=True, max_digits=10, decimal_places=2, required=False, allow_null=True)

    class Meta:
        model = FileUpload
        fields = [
            'id', 'title', 'file_type', 'file_type_display', 'file',
            'company', 'company_name', 'from_date', 'to_date', 'amount',
            'tags', 'tag_details',
            'status', 'status_display', 'processing_started_at', 'processing_completed_at',
            'error_message', 'processed_records_count', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'company_name', 'status', 'status_display', 'file_type_display',
            'tag_details', 'processing_started_at', 'processing_completed_at', 'error_message',
            'processed_records_count', 'created_by', 'created_at', 'updated_at'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make file required for creation, optional for updates
        if self.instance is None:
            self.fields['file'].required = True
        else:
            self.fields['file'].required = False

    def get_company_name(self, obj):
        """Get company name from metadata"""
        metadata = getattr(obj, 'metadata', None)
        if metadata and metadata.company:
            return metadata.company.name
        return None

    def validate(self, data):
        """Validate file upload data"""
        FileUploadValidationService.validate_file_type_and_metadata(data, self.instance)
        return data

    def create(self, validated_data):
        """Create FileUpload and appropriate metadata"""
        # Extract metadata fields
        metadata_fields = self._extract_metadata_fields(validated_data)
        tags = validated_data.pop('tags', [])
        file_type = validated_data.get('file_type')

        with transaction.atomic():
            # Create FileUpload
            file_upload = FileUpload.objects.create(
                **validated_data,
                created_by=self.context['request'].user
            )

            # Set tags
            if tags:
                file_upload.tags.set(tags)

            # Create metadata
            self._create_metadata(file_upload, file_type, **metadata_fields)

            # Log audit and queue processing
            FileUploadService.log_audit(file_upload, 'created', self.context['request'].user)
            FileUploadService.queue_processing_task(file_upload)

        return file_upload

    def update(self, instance, validated_data):
        """Update FileUpload and metadata if provided"""
        # Extract metadata fields
        metadata_fields = self._extract_metadata_fields(validated_data)
        tags = validated_data.pop('tags', None)

        # Update FileUpload fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update tags if provided
        if tags is not None:
            instance.tags.set(tags)

        # Update or create metadata
        with transaction.atomic():
            self._update_metadata(instance, **metadata_fields)

        return instance

    def _extract_metadata_fields(self, validated_data):
        """Extract metadata fields from validated data."""
        return {
            'company_id': validated_data.pop('company', None),
            'from_date': validated_data.pop('from_date', None),
            'to_date': validated_data.pop('to_date', None),
            'amount': validated_data.pop('amount', None),
        }

    def _create_metadata(self, file_upload, file_type, company_id, from_date, to_date, amount):
        """Create metadata for file upload based on file type."""
        if file_type in {FileType.PAYMENTS, FileType.TRIPS} and company_id and from_date and to_date:
            company = Company.objects.get(id=company_id)
            DocumentUploadMetadata.objects.create(
                file_upload=file_upload,
                company=company,
                from_date=from_date,
                to_date=to_date
            )
        elif file_type in {FileType.EXPENSES, FileType.CONTRACTS, FileType.OTHER}:
            DocumentUploadMetadata.objects.create(
                file_upload=file_upload,
                amount=amount,
                from_date=from_date,
                to_date=to_date
            )

    def _update_metadata(self, instance, company_id, from_date, to_date, amount):
        """Update or create metadata for file upload."""
        if instance.file_type in {FileType.PAYMENTS, FileType.TRIPS}:
            if company_id and from_date and to_date:
                company = Company.objects.get(id=company_id)
                metadata, created = DocumentUploadMetadata.objects.get_or_create(
                    file_upload=instance,
                    defaults={
                        'company': company,
                        'from_date': from_date,
                        'to_date': to_date
                    }
                )
                if not created:
                    metadata.company = company
                    metadata.from_date = from_date
                    metadata.to_date = to_date
                    metadata.save()
        elif instance.file_type in {FileType.EXPENSES, FileType.CONTRACTS, FileType.OTHER}:
            metadata, created = DocumentUploadMetadata.objects.get_or_create(
                file_upload=instance,
                defaults={
                    'amount': amount,
                    'from_date': from_date,
                    'to_date': to_date
                }
            )
            if not created:
                if amount is not None:
                    metadata.amount = amount
                # For expenses, preserve existing dates if not provided
                # For contracts/other, allow clearing dates
                if instance.file_type == FileType.EXPENSES:
                    if from_date is not None:
                        metadata.from_date = from_date
                    if to_date is not None:
                        metadata.to_date = to_date
                else:
                    metadata.from_date = from_date
                    metadata.to_date = to_date
                metadata.save()


class FileUploadMetadataMixin:
    """Mixin for common metadata getter methods"""

    def get_company_name(self, obj):
        """Get company name from metadata"""
        metadata = getattr(obj, 'metadata', None)
        if metadata and metadata.company:
            return metadata.company.name
        return None

    def get_company(self, obj):
        """Get company ID from metadata"""
        metadata = getattr(obj, 'metadata', None)
        if metadata and metadata.company:
            return metadata.company.id
        return None

    def get_from_date(self, obj):
        """Get from_date from metadata"""
        metadata = getattr(obj, 'metadata', None)
        return metadata.from_date if metadata else None

    def get_to_date(self, obj):
        """Get to_date from metadata"""
        metadata = getattr(obj, 'metadata', None)
        return metadata.to_date if metadata else None

    def get_amount(self, obj):
        """Get amount from metadata"""
        metadata = getattr(obj, 'metadata', None)
        return metadata.amount if metadata else None

    def get_file_name(self, obj):
        """Get just the filename without path"""
        if not obj.file:
            return None
        # Use os.path for cross-platform compatibility
        return os.path.basename(obj.file.name)

    def get_file_url(self, obj):
        """Absolute or relative URL to the uploaded file"""
        if not obj.file:
            return None
        url = obj.file.url
        request = self.context.get('request') if hasattr(self, 'context') else None
        if request:
            return request.build_absolute_uri(url)
        return url


class FileUploadListSerializer(FileUploadMetadataMixin, serializers.ModelSerializer):
    """Simplified serializer for file upload listing"""

    company = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    tag_details = TagSerializer(source='tags', many=True, read_only=True)
    from_date = serializers.SerializerMethodField()
    to_date = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = [
            'id', 'title', 'file_type', 'file_type_display',
            'file_name', 'file_url', 'company', 'company_name', 'from_date', 'to_date', 'amount',
            'tag_details', 'status', 'status_display', 'processed_records_count', 'created_at'
        ]


class FileUploadDetailSerializer(FileUploadMetadataMixin, serializers.ModelSerializer):
    """Detailed serializer for file upload with related records"""

    company = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_name = serializers.SerializerMethodField()
    tag_details = TagSerializer(source='tags', many=True, read_only=True)
    from_date = serializers.SerializerMethodField()
    to_date = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = [
            'id', 'title', 'file_type', 'file_type_display',
            'file', 'file_name', 'company', 'company_name', 'from_date', 'to_date', 'amount',
            'tag_details', 'status', 'status_display', 'processing_started_at', 'processing_completed_at',
            'error_message', 'processed_records_count', 'created_by', 'created_at', 'updated_at'
        ]


