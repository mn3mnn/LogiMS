from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter

from ..models import FileUpload, PaymentRecord, TripRecord
from ..processors.factory import ProcessorFactory
from .serializers import (
    FileUploadSerializer, FileUploadListSerializer, FileUploadDetailSerializer,
    PaymentRecordSerializer, TripRecordSerializer
)
from ..tasks import process_excel_file
from .filters import FileUploadFilterSet, PaymentRecordFilterSet


class StandardResultsSetPagination(PageNumberPagination):
    """Custom pagination class for consistent pagination across the API"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema(
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID", required=False, type=int, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="company_code", description="Filter by company code", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="from_date", description="Filter uploads with from_date >= value (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="to_date", description="Filter uploads with to_date <= value (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="search", description="Search by company name or file name", required=False, type=str, location=OpenApiParameter.QUERY),
    ]
)
class FileUploadViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Excel file uploads"""

    queryset = FileUpload.objects.all()
    serializer_class = FileUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = FileUploadFilterSet
    search_fields = ['file']
    ordering_fields = ['created_at', 'from_date', 'to_date', 'processed_records_count']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'delete']  # Remove PUT and PATCH

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return FileUploadListSerializer
        elif self.action == 'retrieve':
            return FileUploadDetailSerializer
        return FileUploadSerializer

    def get_queryset(self):
        """Filter queryset based on user permissions and support company_code param."""
        queryset = super().get_queryset().select_related('company', 'created_by')

        company_code = self.request.query_params.get('company_code')
        if company_code:
            queryset = queryset.filter(company__code=company_code)

        return queryset

    def create(self, request, *args, **kwargs):
        """Create file upload and automatically start processing"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create the file upload
        file_upload = serializer.save(created_by=request.user)

        # Check if processor is available for this company
        if ProcessorFactory.is_processor_available(file_upload.company.code):
            # Start processing asynchronously
            process_excel_file.delay(file_upload.id)
            processing_status = "Processing started automatically"
        else:
            # Mark as failed if no processor is available
            file_upload.mark_processing_failed(
                f"No processor available for company '{file_upload.company.name}'"
            )
            processing_status = "Processing failed - no processor available"

        # Return detailed response
        response_serializer = FileUploadDetailSerializer(file_upload)
        return Response({
            'file_upload': response_serializer.data,
            'message': f'File uploaded successfully. {processing_status}.',
            'processing_status': processing_status
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID (maps to file_upload__company)", required=False, type=int, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="company_code", description="Filter by company code (maps to file_upload__company__code)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="from_date", description="Filter by file upload from_date >= (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="to_date", description="Filter by file upload to_date <= (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="search", description="Search by driver first/last name or UUID", required=False, type=str, location=OpenApiParameter.QUERY),
    ]
)
class PaymentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing payment records"""

    queryset = PaymentRecord.objects.all()
    serializer_class = PaymentRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PaymentRecordFilterSet
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid']
    ordering_fields = ['created_at', 'total_revenue', 'payouts', 'final_net_earnings', 'applied_tax_rate', 'applied_agency_share_rate']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset().select_related('file_upload__company')
        company_code = self.request.query_params.get('company_code')
        if company_code:
            queryset = queryset.filter(file_upload__company__code=company_code)
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics for payment records"""
        from django.db.models import Sum, Count, Avg

        queryset = self.filter_queryset(self.get_queryset())

        summary = queryset.aggregate(
            total_records=Count('id'),
            total_revenue=Sum('total_revenue'),
            total_payouts=Sum('payouts'),
            total_net_earnings=Sum('final_net_earnings'),
            avg_revenue=Avg('total_revenue'),
            avg_payouts=Avg('payouts')
        )

        return Response(summary)


class TripRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing trip records"""

    queryset = TripRecord.objects.all()
    serializer_class = TripRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['file_upload', 'file_upload__company', 'driver_uuid', 'trip_status', 'service_type']
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid', 'trip_uuid']
    ordering_fields = ['created_at', 'order_time', 'fare_amount', 'trip_distance', 'trip_duration_minutes']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics for trip records"""
        from django.db.models import Sum, Count, Avg

        queryset = self.filter_queryset(self.get_queryset())

        summary = queryset.aggregate(
            total_trips=Count('id'),
            total_fare_amount=Sum('fare_amount'),
            total_distance=Sum('trip_distance'),
            avg_fare=Avg('fare_amount'),
            avg_distance=Avg('trip_distance'),
            avg_duration=Avg('trip_duration_minutes')
        )

        return Response(summary)
