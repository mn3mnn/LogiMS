"""
Payment record API views.
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter

from ..models import PaymentRecord
from .serializers import PaymentRecordSerializer, PaymentRecordAggregatedSerializer
from .filters import PaymentRecordFilterSet
from ..services.aggregation_service import PaymentAggregationService
from ..services.export_service import PaymentExportService
from logims.contrib.logging_utils import log_error
from logims.contrib.api.pagination import StandardResultsSetPagination

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Payroll"],
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID", required=False, type=int),
        OpenApiParameter(name="company_code", description="Filter by company code", required=False, type=str),
        OpenApiParameter(name="from_date", description="Filter by file upload from_date >= (YYYY-MM-DD)", required=False, type=str),
        OpenApiParameter(name="to_date", description="Filter by file upload to_date <= (YYYY-MM-DD)", required=False, type=str),
        OpenApiParameter(name="search", description="Search by driver first/last name or UUID", required=False, type=str),
    ]
)
class PaymentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing payment records"""

    queryset = PaymentRecord.objects.all()
    serializer_class = PaymentRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PaymentRecordFilterSet
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid', 'supervisor_name_at_calculation']
    ordering_fields = ['created_at', 'total_revenue', 'payouts', 'final_net_earnings', 'applied_tax_rate', 'applied_agency_share_rate', 'tax_deduction', 'agency_share_deduction', 'insurance_deduction', 'total_deductions']
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
        """
        Get summary statistics for payment records.
        """
        from django.db.models import Sum, Count, Q
        from logims.uploads.models import FileUpload, FileType

        queryset = self.filter_queryset(self.get_queryset())

        summary = queryset.aggregate(
            total_records=Count('id'),
            total_revenue=Sum('total_revenue'),
            total_payouts=Sum('payouts'),
            total_net_earnings=Sum('final_net_earnings'),
            agency_profit=Sum('agency_share_deduction'),
            total_tax_deduction=Sum('tax_deduction'),
            total_insurance_deduction=Sum('insurance_deduction'),
        )

        # Convenience field: combined tax + insurance
        tax = summary.get('total_tax_deduction') or 0
        insurance = summary.get('total_insurance_deduction') or 0
        summary['total_tax_and_insurance'] = tax + insurance

        # Calculate total expenses from expenses file uploads
        # Apply the same filters as payment records
        expenses_queryset = FileUpload.objects.filter(
            file_type=FileType.EXPENSES
        ).select_related('metadata')

        # Apply company filter if provided
        company_code = request.query_params.get('company_code')
        if company_code:
            expenses_queryset = expenses_queryset.filter(
                metadata__company__code=company_code
            )

        # Apply date range filters (same logic as payment records)
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        if from_date and to_date:
            expenses_queryset = expenses_queryset.filter(
                Q(metadata__from_date__lte=to_date) &
                Q(metadata__to_date__gte=from_date)
            )
        elif from_date:
            expenses_queryset = expenses_queryset.filter(
                metadata__to_date__gte=from_date
            )
        elif to_date:
            expenses_queryset = expenses_queryset.filter(
                metadata__from_date__lte=to_date
            )

        # Sum amounts from expenses metadata
        expenses_aggregate = expenses_queryset.aggregate(
            total_expenses=Sum('metadata__amount')
        )
        total_expenses = expenses_aggregate.get('total_expenses') or 0
        summary['total_expenses'] = total_expenses

        # Calculate net agency profit
        agency_profit = summary.get('agency_profit') or 0
        summary['net_agency_profit'] = agency_profit - total_expenses

        return Response(summary)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Top companies by totals and counts"""
        from django.db.models import Sum, Count
        qs = self.filter_queryset(self.get_queryset())
        top_companies = (
            qs.values('file_upload__metadata__company__name')
            .annotate(
                total_net=Sum('final_net_earnings'),
                total_revenue=Sum('total_revenue'),
                records=Count('id'),
            )
            .order_by('-total_net')[:5]
        )
        return Response({
            'top_companies': list(top_companies),
            'total_records': qs.count(),
        })

    @action(detail=False, methods=['get'])
    def aggregated(self, request):
        """
        Get aggregated payment records with flexible grouping.
        """
        # Get group_by parameter
        group_by = request.query_params.get('group_by', '').strip()
        driver_id = request.query_params.get('driver_id')
        supervisor_id = request.query_params.get('supervisor_id')

        # Get base queryset with filters applied
        queryset = self.filter_queryset(self.get_queryset())

        # Apply aggregation
        aggregated_qs = PaymentAggregationService.aggregate_payments(
            queryset,
            group_by=group_by if group_by else None,
            supervisor_id=int(supervisor_id) if supervisor_id else None,
            driver_id=int(driver_id) if driver_id else None
        )

        # Convert to list and format results
        results = []
        for row in aggregated_qs:
            formatted = PaymentAggregationService.format_payment_aggregation_result(row)
            results.append(formatted)

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request)
        if page is not None:
            serializer = PaymentRecordAggregatedSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = PaymentRecordAggregatedSerializer(results, many=True)
        return Response(serializer.data)

    @extend_schema(description="Export aggregated payment records as CSV.")
    @action(detail=False, methods=['get'], url_path='aggregated/export')
    def export_aggregated(self, request):
        """Export aggregated payment records as CSV"""
        try:
            # Get group_by parameter
            group_by = request.query_params.get('group_by', '').strip()
            driver_id = request.query_params.get('driver_id')
            supervisor_id = request.query_params.get('supervisor_id')

            # Get base queryset with filters applied
            queryset = self.filter_queryset(self.get_queryset())

            # Apply aggregation
            aggregated_qs = PaymentAggregationService.aggregate_payments(
                queryset,
                group_by=group_by if group_by else None,
                supervisor_id=int(supervisor_id) if supervisor_id else None,
                driver_id=int(driver_id) if driver_id else None
            )

            # Convert to list and format results
            results = []
            for row in aggregated_qs:
                formatted = PaymentAggregationService.format_payment_aggregation_result(row)
                results.append(formatted)

            record_count = len(results)

            try:
                logger.info(
                    f"Aggregated payment records export started | user={request.user.username} | count={record_count} | group_by={group_by}"
                )
            except Exception:
                pass

            # Use export service
            response = PaymentExportService.export_aggregated(results, group_by)

            try:
                logger.info(
                    f"Aggregated payment records export completed | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            return response

        except Exception as e:
            log_error(e, context="Aggregated payment records export failed", user=request.user.username)
            raise

    @action(detail=False, methods=['get'])
    def timeseries(self, request):
        """
        Time series for revenue/net/payouts aggregated by upload period.
        """
        from django.db.models import Sum

        qs = self.filter_queryset(self.get_queryset())

        # Only support upload-period aggregation (what frontend uses)
        series = (
            qs.values(
                'file_upload_id',
                'file_upload__metadata__from_date',
                'file_upload__metadata__to_date',
                'file_upload__metadata__company__name'
            )
            .annotate(
                total_net=Sum('final_net_earnings'),
                total_revenue=Sum('total_revenue'),
                total_payouts=Sum('payouts'),
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
                'total_net': row['total_net'],
                'total_revenue': row['total_revenue'],
                'total_payouts': row['total_payouts'],
            })
        return Response(result)

    @action(detail=False, methods=['get'])
    def expenses_timeseries(self, request):
        """
        Time series for expenses aggregated by upload period.
        """
        from django.db.models import Sum, Q
        from logims.uploads.models import FileUpload, FileType

        # Query expenses file uploads with same filters as payment records
        expenses_queryset = FileUpload.objects.filter(
            file_type=FileType.EXPENSES
        ).select_related('metadata', 'metadata__company')

        # Apply company filter if provided
        company_code = request.query_params.get('company_code')
        if company_code:
            expenses_queryset = expenses_queryset.filter(
                metadata__company__code=company_code
            )

        # Apply date range filters (same logic as payment records)
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        if from_date and to_date:
            expenses_queryset = expenses_queryset.filter(
                Q(metadata__from_date__lte=to_date) &
                Q(metadata__to_date__gte=from_date)
            )
        elif from_date:
            expenses_queryset = expenses_queryset.filter(
                metadata__to_date__gte=from_date
            )
        elif to_date:
            expenses_queryset = expenses_queryset.filter(
                metadata__from_date__lte=to_date
            )

        # Group by period (from_date, to_date) and company, then sum amounts
        # This ensures all expenses in the same period are aggregated together
        series = (
            expenses_queryset.values(
                'metadata__from_date',
                'metadata__to_date',
                'metadata__company__name'
            )
            .annotate(
                total_expenses=Sum('metadata__amount')
            )
            .filter(metadata__amount__isnull=False, metadata__from_date__isnull=False, metadata__to_date__isnull=False)
            .order_by('metadata__from_date')
        )

        result = []
        for row in series:
            result.append({
                'upload_id': None,  # Not needed since we're grouping by period
                'from_date': row['metadata__from_date'],
                'to_date': row['metadata__to_date'],
                'company': row['metadata__company__name'],
                'total_expenses': row['total_expenses'] or 0,
            })
        return Response(result)

    @extend_schema(description="Export payment records as CSV.")
    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Export payment records as CSV"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            record_count = queryset.count()

            try:
                logger.info(
                    f"Payment records export started | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            response = PaymentExportService.export_records(queryset)

            try:
                logger.info(
                    f"Payment records export completed | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            return response

        except Exception as e:
            log_error(e, context="Payment records export failed", user=request.user.username)
            raise
