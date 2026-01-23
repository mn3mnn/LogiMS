"""
Unified FileUpload API views.
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from logims.uploads.models import FileUpload, FileType, ProcessingStatus
from .serializers import FileUploadSerializer, FileUploadListSerializer, FileUploadDetailSerializer
from .filters import FileUploadFilterSet
from .mixins import FileUploadStatsMixin
from ..services.file_upload_service import FileUploadService, PROCESSABLE_FILE_TYPES
from logims.contrib.logging_utils import log_error
from logims.contrib.api.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Uploads"],
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID", required=False, type=int),
        OpenApiParameter(name="company_code", description="Filter by company code", required=False, type=str),
        OpenApiParameter(name="from_date", description="Filter uploads with from_date >= value", required=False, type=str),
        OpenApiParameter(name="to_date", description="Filter uploads with to_date <= value", required=False, type=str),
        OpenApiParameter(name="file_type", description="Filter by file type(s)", required=False, type=str),
        OpenApiParameter(name="status", description="Filter by status(es)", required=False, type=str),
        OpenApiParameter(name="is_processed", description="Filter by processed status", required=False, type=bool),
        OpenApiParameter(name="is_pending", description="Filter by pending status", required=False, type=bool),
        OpenApiParameter(name="search", description="Search by title, file name, or tags", required=False, type=str),
    ]
)
class FileUploadViewSet(FileUploadStatsMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing file uploads (unified for all types).
    Business logic is delegated to FileUploadService.
    """

    queryset = FileUpload.objects.all()
    serializer_class = FileUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = FileUploadFilterSet
    search_fields = ['title', 'file', 'tags__name']
    ordering_fields = ['created_at', 'processed_records_count', 'status']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'put', 'delete']
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return FileUploadListSerializer
        elif self.action == 'retrieve':
            return FileUploadDetailSerializer
        return FileUploadSerializer

    def get_queryset(self):
        """Get optimized queryset with select_related for performance"""
        queryset = super().get_queryset().select_related(
            'metadata__company',
            'created_by'
        ).prefetch_related('tags')

        # Use distinct() to avoid duplicate results when searching by tags
        return queryset.distinct()

    def create(self, request, *args, **kwargs):
        """Create file upload and automatically start processing"""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            file_upload = serializer.save()

            company_name = FileUploadService.get_company_name(file_upload)

            logger.info(
                f"File upload created | id={file_upload.id} | "
                f"title={file_upload.title} | "
                f"company={company_name} | "
                f"file_type={file_upload.file_type} | "
                f"user={request.user.username}"
            )

            processing_status = "File uploaded successfully"

            # Processing is queued in serializer.create() via transaction.on_commit
            if file_upload.file_type in PROCESSABLE_FILE_TYPES:
                processing_status = "Processing started automatically"

            FileUploadService.log_file_upload_operation(
                file_upload, "create", request.user
            )

            FileUploadService.log_audit(file_upload, 'created', request.user)

            response_serializer = FileUploadDetailSerializer(file_upload)
            return Response({
                'file_upload': response_serializer.data,
                'message': f'File uploaded successfully. {processing_status}.',
                'processing_status': processing_status
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            log_error(e, context="File upload creation failed", user=request.user.username)
            raise

    def update(self, request, *args, **kwargs):
        """Update file upload using PUT (with optional file)"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        file_upload = serializer.save()

        # Always reprocess if file type is processable
        if file_upload.file_type in PROCESSABLE_FILE_TYPES:
            FileUploadService.prepare_and_queue_reprocessing(
                file_upload, ['update'], request.user
            )

        # Log the update
        FileUploadService.log_file_upload_operation(
            file_upload, "update", request.user
        )

        # Log audit trail
        FileUploadService.log_audit(file_upload, 'updated', request.user)

        response_serializer = FileUploadDetailSerializer(file_upload)
        message = 'File upload updated successfully.'
        if file_upload.file_type in PROCESSABLE_FILE_TYPES:
            message += ' Reprocessing has been queued.'

        return Response({
            'file_upload': response_serializer.data,
            'message': message,
            'reprocessing_queued': file_upload.file_type in PROCESSABLE_FILE_TYPES
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """Delete file upload with logging"""
        instance = self.get_object()
        file_id = instance.id
        file_title = instance.title
        file_type = instance.file_type

        company_name = FileUploadService.get_company_name(instance)

        logger.info(
            f"File upload deletion | id={file_id} | company={company_name} | "
            f"user={request.user.username}"
        )

        FileUploadService.log_file_upload_operation(
            instance, "delete", request.user
        )

        # Log audit trail BEFORE deletion (so we have file info)
        FileUploadService.log_audit(instance, 'deleted', request.user)

        # Perform deletion
        result = super().destroy(request, *args, **kwargs)

        return result
