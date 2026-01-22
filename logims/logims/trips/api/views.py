"""
Trip record API views.
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from ..models import TripRecord
from .serializers import TripRecordSerializer, TripRecordAggregatedSerializer
from .filters import TripRecordFilterSet
from ..services.aggregation_service import TripAggregationService
from ..services.export_service import TripExportService
from logims.contrib.logging_utils import log_error
from logims.contrib.api.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Trips"],
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID", required=False, type=int),
        OpenApiParameter(name="company_code", description="Filter by company code", required=False, type=str),
        OpenApiParameter(name="from_date", description="Filter by file upload from_date >= (YYYY-MM-DD)", required=False, type=str),
        OpenApiParameter(name="to_date", description="Filter by file upload to_date <= (YYYY-MM-DD)", required=False, type=str),
        OpenApiParameter(name="search", description="Search by driver first/last name or UUID", required=False, type=str),
    ]
)
class TripRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing trip records"""

    queryset = TripRecord.objects.all()
    serializer_class = TripRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TripRecordFilterSet
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid', 'supervisor_name_at_calculation', 'trip_uuid']
    ordering_fields = ['created_at', 'order_time', 'fare_amount', 'trip_distance', 'trip_duration_minutes']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """Get queryset with select_related for performance"""
        from django.db.models import OuterRef, Subquery, IntegerField
        from logims.drivers.models import Driver

        queryset = super().get_queryset().select_related(
            'file_upload', 'file_upload__metadata', 'file_upload__metadata__company',
            'driver', 'driver__supervisor'
        )

        # Annotate with current driver_id by UUID to handle deleted/re-added drivers
        # This ensures we get the current driver ID even if driver was deleted and re-added
        current_driver_subquery = Driver.objects.filter(
            uuid=OuterRef('driver_uuid')
        ).values('id')[:1]

        queryset = queryset.annotate(
            current_driver_id_by_uuid=Subquery(
                current_driver_subquery,
                output_field=IntegerField()
            )
        )

        company_code = self.request.query_params.get('company_code')
        if company_code:
            queryset = queryset.filter(file_upload__metadata__company__code=company_code)
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics for trip records"""
        from django.db.models import Sum, Count, Avg

        queryset = self.filter_queryset(self.get_queryset())

        summary = queryset.aggregate(
            total_trips=Count('id'),
            total_fare_amount=Sum('fare_amount'),
            total_distance=Sum('trip_distance')
        )

        return Response(summary)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Counts by status and service type for trips"""
        from django.db.models import Count, Sum

        qs = self.filter_queryset(self.get_queryset())
        # Use only() to limit fields fetched for aggregation queries
        by_status = qs.values('trip_status').annotate(count=Count('id')).order_by()
        by_service = qs.values('service_type').annotate(count=Count('id')).order_by()

        # Optimize top_drivers query - use current_driver_id_by_uuid annotation (handles deleted/re-added drivers)
        top_drivers_qs = (
            qs.values('driver_uuid', 'driver_first_name', 'driver_last_name',
                     'driver_id_at_calculation', 'current_driver_id_by_uuid')
            .annotate(
                trips=Count('id'),
                fare=Sum('fare_amount'),
            )
            .order_by('-fare')[:3]
        )
        top_drivers = list(top_drivers_qs)

        # Use current_driver_id_by_uuid (from annotation) or fall back to driver_id_at_calculation
        for d in top_drivers:
            # Priority: current_driver_id_by_uuid > driver_id_at_calculation
            d['driver_id'] = d.get('current_driver_id_by_uuid') or d.get('driver_id_at_calculation')

        return Response({
            'by_status': list(by_status),
            'by_service_type': list(by_service),
            'top_drivers': top_drivers,
            'total': qs.count(),
        })

    @action(detail=False, methods=['get'])
    def aggregated(self, request):
        """
        Get aggregated trip records with flexible grouping.
        """
        # Get group_by parameter (default to backward-compatible grouping)
        group_by = request.query_params.get('group_by', 'driver,period,status').strip()
        driver_id = request.query_params.get('driver_id')
        supervisor_id = request.query_params.get('supervisor_id')

        # Get base queryset with filters applied
        queryset = self.filter_queryset(self.get_queryset())

        # Apply aggregation
        aggregated_qs = TripAggregationService.aggregate_trips(
            queryset,
            group_by=group_by if group_by else None,
            supervisor_id=int(supervisor_id) if supervisor_id else None,
            driver_id=int(driver_id) if driver_id else None
        )

        # Convert to list and format results
        results = []
        for row in aggregated_qs:
            formatted = TripAggregationService.format_trip_aggregation_result(row)
            results.append(formatted)

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request)
        if page is not None:
            serializer = TripRecordAggregatedSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = TripRecordAggregatedSerializer(results, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def timeseries(self, request):
        """
        Time series for trip data aggregated by upload period.
        Only supports upload period aggregation.
        """
        from django.db.models import Sum, Count

        qs = self.filter_queryset(self.get_queryset())

        # Only support upload-period aggregation
        series = (
            qs.values(
                'file_upload_id',
                'file_upload__metadata__from_date',
                'file_upload__metadata__to_date',
                'file_upload__metadata__company__name'
            )
            .annotate(
                total_fare=Sum('fare_amount'),
                total_distance=Sum('trip_distance'),
                trip_count=Count('id'),
            )
            .order_by('file_upload__metadata__from_date')
        )

        result = []
        for row in series:
            result.append({
                'upload_id': row['file_upload_id'],
                'from_date': row['file_upload__metadata__from_date'],
                'to_date': row['file_upload__metadata__to_date'],
                'company': row['file_upload__metadata__company__name'],
                'total_fare': row['total_fare'],
                'total_distance': row['total_distance'],
                'trips': row['trip_count'],
            })
        return Response(result)

    @extend_schema(description="Export aggregated trip records as CSV.")
    @action(detail=False, methods=['get'], url_path='aggregated/export')
    def export_aggregated(self, request):
        """Export aggregated trip records as CSV"""
        try:
            # Get group_by parameter (default to backward-compatible grouping)
            group_by = request.query_params.get('group_by', 'driver,period,status').strip()
            driver_id = request.query_params.get('driver_id')
            supervisor_id = request.query_params.get('supervisor_id')

            # Get base queryset with filters applied
            queryset = self.filter_queryset(self.get_queryset())

            # Apply aggregation
            aggregated_qs = TripAggregationService.aggregate_trips(
                queryset,
                group_by=group_by if group_by else None,
                supervisor_id=int(supervisor_id) if supervisor_id else None,
                driver_id=int(driver_id) if driver_id else None
            )

            # Convert to list and format results
            results = []
            for row in aggregated_qs:
                formatted = TripAggregationService.format_trip_aggregation_result(row)
                results.append(formatted)

            # Use export service
            return TripExportService.export_aggregated(results, group_by)

        except Exception as e:
            log_error(e, context="Aggregated trip records export failed", user=request.user.username)
            raise

    @extend_schema(description="Export trip records as CSV.")
    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Export trip records as CSV"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            return TripExportService.export_records(queryset)
        except Exception as e:
            log_error(e, context="Trip records export failed", user=request.user.username)
            raise
