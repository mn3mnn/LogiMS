import csv
import logging
from io import StringIO
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from logims.drivers.models import Driver
from django.db.models.functions import TruncDay

from ..models import FileUpload, PaymentRecord, TripRecord
from ..processors.factory import ProcessorFactory
from .serializers import (
    FileUploadSerializer, FileUploadListSerializer, FileUploadDetailSerializer,
    PaymentRecordSerializer, TripRecordSerializer, TripRecordAggregatedSerializer
)
from ..tasks import process_excel_file
from .filters import FileUploadFilterSet, PaymentRecordFilterSet, TripRecordFilterSet
from logims.contrib.logging_utils import log_api_call, log_model_change, log_error

logger = logging.getLogger(__name__)


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
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Create the file upload
            file_upload = serializer.save(created_by=request.user)

            # Safe logging
            try:
                logger.info(
                    f"File upload created | id={file_upload.id} | "
                    f"company={file_upload.company.name} | "
                    f"file_type={file_upload.file_type} | "
                    f"user={request.user.username}"
                )
            except Exception:
                pass

            # Check if processor is available for this company
            if ProcessorFactory.is_processor_available(file_upload.company.code):
                # Start processing asynchronously after transaction commits
                # This prevents race condition where task runs before DB commit
                file_upload_id = file_upload.id
                transaction.on_commit(lambda: process_excel_file.delay(file_upload_id))
                processing_status = "Processing started automatically"

                # Safe logging
                try:
                    logger.info(
                        f"File processing queued | file_upload_id={file_upload.id} | "
                        f"company={file_upload.company.name}"
                    )
                except Exception:
                    pass
            else:
                # Mark as failed if no processor is available
                file_upload.mark_processing_failed(
                    f"No processor available for company '{file_upload.company.name}'"
                )
                processing_status = "Processing failed - no processor available"

                # Safe logging
                try:
                    logger.warning(
                        f"No processor available | file_upload_id={file_upload.id} | "
                        f"company={file_upload.company.name} | company_code={file_upload.company.code}"
                    )
                except Exception:
                    pass

            # Utility function is already safe via @_safe_log decorator
            log_model_change(
                action="create",
                model_name="FileUpload",
                instance_id=file_upload.id,
                user=request.user,
                company=file_upload.company.name,
                file_type=file_upload.file_type
            )

            # Return detailed response
            response_serializer = FileUploadDetailSerializer(file_upload)
            return Response({
                'file_upload': response_serializer.data,
                'message': f'File uploaded successfully. {processing_status}.',
                'processing_status': processing_status
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Utility function is already safe via @_safe_log decorator
            log_error(e, context="File upload creation failed", user=request.user.username)
            raise

    def destroy(self, request, *args, **kwargs):
        """Delete file upload with logging."""
        instance = self.get_object()
        file_id = instance.id
        company_name = instance.company.name

        # Direct logger call needs protection
        try:
            logger.info(
                f"File upload deletion | id={file_id} | company={company_name} | "
                f"user={request.user.username}"
            )
        except Exception:
            pass

        # Utility function is already safe via @_safe_log decorator
        log_model_change(
            action="delete",
            model_name="FileUpload",
            instance_id=file_id,
            user=request.user,
            company=company_name
        )

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Basic stats: counts by status and file_type"""
        from django.db.models import Count

        logger.debug(f"File upload stats requested | user={request.user.username}")

        qs = self.filter_queryset(self.get_queryset())
        by_status = qs.values('status').annotate(count=Count('id')).order_by()
        by_type = qs.values('file_type').annotate(count=Count('id')).order_by()

        return Response({
            'by_status': list(by_status),
            'by_type': list(by_type),
            'total': qs.count(),
        })

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
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid', 'supervisor_name_at_calculation']
    ordering_fields = ['created_at', 'total_revenue', 'payouts', 'final_net_earnings', 'applied_tax_rate', 'applied_agency_share_rate', 'tax_deduction', 'agency_share_deduction', 'insurance_deduction', 'total_deductions']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset().select_related('file_upload__company', 'driver', 'driver__supervisor')
        company_code = self.request.query_params.get('company_code')
        if company_code:
            queryset = queryset.filter(file_upload__company__code=company_code)
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics for payment records.

        This endpoint powers the admin dashboard Payment Summary section.
        Returned fields:
          - total_records: number of payment records
          - total_revenue: gross revenue received from Uber Eats
          - total_payouts: total payouts reported in the file
          - total_net_earnings: net amount paid to drivers (after all deductions)
          - agency_profit: total agency share deducted from drivers
          - total_tax_deduction: total tax deducted from drivers
          - total_insurance_deduction: total insurance deducted from drivers
          - total_tax_and_insurance: tax + insurance deductions combined
        """
        from django.db.models import Sum, Count

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

        return Response(summary)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Top companies by totals and counts"""
        from django.db.models import Sum, Count
        qs = self.filter_queryset(self.get_queryset())
        top_companies = (
            qs.values('file_upload__company__name')
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

        Query Parameters:
            - group_by: Comma-separated grouping dimensions (driver, supervisor, period, company)
                       Examples: "driver", "supervisor", "driver,period", "supervisor,period"
            - driver_id: Filter by specific driver
            - supervisor_id: Filter by specific supervisor
            - Other filters from PaymentRecordFilterSet apply

        Returns paginated aggregated results.
        """
        from ..utils.aggregation import AggregationService
        from ..api.serializers import PaymentRecordAggregatedSerializer

        # Get group_by parameter
        group_by = request.query_params.get('group_by', '').strip()
        driver_id = request.query_params.get('driver_id')
        supervisor_id = request.query_params.get('supervisor_id')

        # Get base queryset with filters applied
        queryset = self.filter_queryset(self.get_queryset())

        # Apply aggregation
        aggregated_qs = AggregationService.aggregate_payments(
            queryset,
            group_by=group_by if group_by else None,
            supervisor_id=int(supervisor_id) if supervisor_id else None,
            driver_id=int(driver_id) if driver_id else None
        )

        # Convert to list and format results
        results = []
        for row in aggregated_qs:
            formatted = AggregationService.format_payment_aggregation_result(row)
            results.append(formatted)

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request)
        if page is not None:
            serializer = PaymentRecordAggregatedSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = PaymentRecordAggregatedSerializer(results, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Export aggregated payment records as CSV."
    )
    @action(detail=False, methods=['get'], url_path='aggregated/export')
    def export_aggregated(self, request):
        """Export aggregated payment records as CSV with all current filters applied."""
        try:
            from ..utils.aggregation import AggregationService
            import csv
            from io import StringIO
            from django.http import HttpResponse

            # Get group_by parameter
            group_by = request.query_params.get('group_by', '').strip()
            driver_id = request.query_params.get('driver_id')
            supervisor_id = request.query_params.get('supervisor_id')

            # Get base queryset with filters applied
            queryset = self.filter_queryset(self.get_queryset())

            # Apply aggregation
            aggregated_qs = AggregationService.aggregate_payments(
                queryset,
                group_by=group_by if group_by else None,
                supervisor_id=int(supervisor_id) if supervisor_id else None,
                driver_id=int(driver_id) if driver_id else None
            )

            # Convert to list and format results
            results = []
            for row in aggregated_qs:
                formatted = AggregationService.format_payment_aggregation_result(row)
                results.append(formatted)

            record_count = len(results)

            # Safe logging
            try:
                logger.info(
                    f"Aggregated payment records export started | user={request.user.username} | count={record_count} | group_by={group_by}"
                )
            except Exception:
                pass

            # Prepare CSV data
            buffer = StringIO()
            writer = csv.writer(buffer)

            # Determine headers based on group_by
            group_by_lower = group_by.lower()
            if 'supervisor' in group_by_lower and 'driver' not in group_by_lower:
                # Supervisor view: supervisor, period, company
                headers = ["Supervisor ID", "Supervisor Name", "Driver Count"]
                if 'period' in group_by_lower:
                    headers.extend(["Period From", "Period To"])
                if 'company' in group_by_lower:
                    headers.append("Company")
                headers.extend([
                    "Total Revenue", "Tips", "Total Deductions", "Tax Deduction", "Agency Share Deduction",
                    "Insurance Deduction", "Final Net Earnings", "Payouts", "Record Count"
                ])
                writer.writerow(headers)
                for row in results:
                    row_data = [
                        row.get('supervisor_id_at_calculation') or "",
                        row.get('supervisor_name_at_calculation') or "",
                        row.get('driver_count') or 0,
                    ]
                    if 'period' in group_by_lower:
                        row_data.extend([
                            row.get('from_date') or "",
                            row.get('to_date') or "",
                        ])
                    if 'company' in group_by_lower:
                        row_data.append(row.get('company_name') or "")
                    row_data.extend([
                        row.get('total_revenue') or 0,
                        row.get('tips') or 0,
                        row.get('total_deductions') or 0,
                        row.get('tax_deduction') or 0,
                        row.get('agency_share_deduction') or 0,
                        row.get('insurance_deduction') or 0,
                        row.get('final_net_earnings') or 0,
                        row.get('payouts') or 0,
                        row.get('record_count') or 0,
                    ])
                    writer.writerow(row_data)
            elif 'driver' in group_by_lower:
                # Driver view: driver, period, company
                headers = ["Driver ID", "Driver UUID", "Driver Name", "Supervisor Name"]
                if 'period' in group_by_lower:
                    headers.extend(["Period From", "Period To"])
                if 'company' in group_by_lower:
                    headers.append("Company")
                headers.extend([
                    "Total Revenue", "Tips", "Total Deductions", "Tax Deduction", "Agency Share Deduction",
                    "Insurance Deduction", "Final Net Earnings", "Payouts", "Record Count"
                ])
                writer.writerow(headers)
                for row in results:
                    row_data = [
                        row.get('driver_id') or "",
                        row.get('driver_uuid') or "",
                        row.get('driver_name') or "",
                        row.get('supervisor_name_at_calculation') or "",
                    ]
                    if 'period' in group_by_lower:
                        row_data.extend([
                            row.get('from_date') or "",
                            row.get('to_date') or "",
                        ])
                    if 'company' in group_by_lower:
                        row_data.append(row.get('company_name') or "")
                    row_data.extend([
                        row.get('total_revenue') or 0,
                        row.get('tips') or 0,
                        row.get('total_deductions') or 0,
                        row.get('tax_deduction') or 0,
                        row.get('agency_share_deduction') or 0,
                        row.get('insurance_deduction') or 0,
                        row.get('final_net_earnings') or 0,
                        row.get('payouts') or 0,
                        row.get('record_count') or 0,
                    ])
                    writer.writerow(row_data)
            else:
                # Default: same as driver
                writer.writerow([
                    "Driver ID", "Driver UUID", "Driver Name", "Supervisor Name", "Company",
                    "Total Revenue", "Tips", "Total Deductions", "Tax Deduction", "Agency Share Deduction",
                    "Insurance Deduction", "Final Net Earnings", "Payouts", "Record Count"
                ])
                for row in results:
                    writer.writerow([
                        row.get('driver_id') or "",
                        row.get('driver_uuid') or "",
                        row.get('driver_name') or "",
                        row.get('supervisor_name_at_calculation') or "",
                        row.get('company_name') or "",
                        row.get('total_revenue') or 0,
                        row.get('tips') or 0,
                        row.get('total_deductions') or 0,
                        row.get('tax_deduction') or 0,
                        row.get('agency_share_deduction') or 0,
                        row.get('insurance_deduction') or 0,
                        row.get('final_net_earnings') or 0,
                        row.get('payouts') or 0,
                        row.get('record_count') or 0,
                    ])

            # Safe logging
            try:
                logger.info(
                    f"Aggregated payment records export completed | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            # Create HTTP response
            group_name = group_by or 'raw'
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="payment_records_aggregated_{group_name}_{timezone.now().date()}.csv"'
            return response

        except Exception as e:
            log_error(e, context="Aggregated payment records export failed", user=request.user.username)
            raise

    @action(detail=False, methods=['get'])
    def timeseries(self, request):
        """Time series for revenue/net/payouts.
        Params:
          - segments=true: collapse contiguous daily data into ranges; gap_days (default 3)
          - monthly=auto: if a contiguous range fully covers a calendar month, collapse to monthly point
        """
        from django.db.models import Sum
        import datetime, calendar
        qs = self.filter_queryset(self.get_queryset())
        # Upload-period aggregation mode
        if request.query_params.get('period') == 'upload':
            series = (
                qs.values('file_upload_id', 'file_upload__from_date', 'file_upload__to_date', 'file_upload__company__name')
                .annotate(
                    total_net=Sum('final_net_earnings'),
                    total_revenue=Sum('total_revenue'),
                    total_payouts=Sum('payouts'),
                )
                .order_by('file_upload__from_date')
            )
            # normalize keys
            result = []
            for row in series:
                result.append({
                    'upload_id': row['file_upload_id'],
                    'from_date': row['file_upload__from_date'],
                    'to_date': row['file_upload__to_date'],
                    'company': row['file_upload__company__name'],
                    'total_net': row['total_net'],
                    'total_revenue': row['total_revenue'],
                    'total_payouts': row['total_payouts'],
                })
            return Response(result)

        series = (
            qs.annotate(day=TruncDay('file_upload__from_date'))
            .values('day')
            .annotate(
                total_net=Sum('final_net_earnings'),
                total_revenue=Sum('total_revenue'),
                total_payouts=Sum('payouts'),
            )
            .order_by('day')
        )
        segments = request.query_params.get('segments') == 'true'
        monthly = request.query_params.get('monthly') == 'auto'
        if not segments:
            return Response(list(series))

        gap_days = int(request.query_params.get('gap_days') or 3)
        # Build contiguous segments
        items = list(series)
        out = []
        current = None
        prev_day = None
        days_in_segment = set()
        for row in items:
            day = row['day'].date() if hasattr(row['day'], 'date') else row['day']
            if prev_day is None or (day - prev_day).days >= gap_days:
                # finalize previous
                if current:
                    # monthly collapse if eligible
                    if monthly:
                        start = current['start']
                        end = current['end']
                        if start.day == 1 and start.month == end.month and start.year == end.year:
                            _, mdays = calendar.monthrange(start.year, start.month)
                            if (end.day == mdays) and (len(days_in_segment) == mdays):
                                current['period_type'] = 'month'
                                current['month'] = start.strftime('%Y-%m')
                    out.append(current)
                # start new
                current = {
                    'start': day,
                    'end': day,
                    'total_net': row['total_net'] or 0,
                    'total_revenue': row['total_revenue'] or 0,
                    'total_payouts': row['total_payouts'] or 0,
                    'period_type': 'range',
                }
                days_in_segment = {day}
            else:
                # extend
                current['end'] = day
                current['total_net'] += row['total_net'] or 0
                current['total_revenue'] += row['total_revenue'] or 0
                current['total_payouts'] += row['total_payouts'] or 0
                days_in_segment.add(day)
            prev_day = day
        if current:
            if monthly:
                start = current['start']
                end = current['end']
                if start.day == 1 and start.month == end.month and start.year == end.year:
                    _, mdays = calendar.monthrange(start.year, start.month)
                    if (end.day == mdays) and (len(days_in_segment) == mdays):
                        current['period_type'] = 'month'
                        current['month'] = start.strftime('%Y-%m')
            out.append(current)
        return Response(out)

    @extend_schema(
        description="Export payment records as CSV."
    )
    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Export payment records as CSV with all current filters applied."""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            record_count = queryset.count()

            # Safe logging
            try:
                logger.info(
                    f"Payment records export started | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            # Prepare CSV data
            buffer = StringIO()
            writer = csv.writer(buffer)
            writer.writerow([
                "ID", "Upload ID", "Period From", "Period To", "Company", "Driver UUID",
                "Driver Name", "Total Revenue", "Net Fare", "Promotions", "Refunds and Fees",
                "Payouts", "Bank Transfer", "Cash Collected", "Fare Tax", "Tips", "Taxes",
                "Other Revenue", "Total Deductions", "Tax Deduction", "Agency Share Deduction",
                "Insurance Deduction", "Final Net Earnings", "Created At"
            ])

            for record in queryset.select_related('file_upload__company'):
                writer.writerow([
                    record.id,
                    record.file_upload.id if record.file_upload else "",
                    record.file_upload.from_date if record.file_upload else "",
                    record.file_upload.to_date if record.file_upload else "",
                    record.file_upload.company.name if record.file_upload and record.file_upload.company else "",
                    record.driver_uuid or "",
                    f"{record.driver_first_name} {record.driver_last_name}".strip(),
                    record.total_revenue or "",
                    record.net_fare or "",
                    record.promotions or "",
                    record.refunds_and_fees or "",
                    record.payouts or "",
                    record.bank_transfer or "",
                    record.cash_collected or "",
                    record.fare_tax or "",
                    record.tips or "",
                    record.taxes or "",
                    record.other_revenue or "",
                    record.total_deductions or "",
                    record.tax_deduction or "",
                    record.agency_share_deduction or "",
                    record.insurance_deduction or "",
                    record.final_net_earnings or "",
                    record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else "",
                ])

            # Safe logging
            try:
                logger.info(
                    f"Payment records export completed | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            # Create HTTP response
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="payment_records_export_{timezone.now().date()}.csv"'
            return response

        except Exception as e:
            log_error(e, context="Payment records export failed", user=request.user.username)
            raise

@extend_schema(
    parameters=[
        OpenApiParameter(name="company", description="Filter by company ID (maps to file_upload__company)", required=False, type=int, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="company_code", description="Filter by company code (maps to file_upload__company__code)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="from_date", description="Filter by file upload period overlap (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="to_date", description="Filter by file upload period overlap (YYYY-MM-DD)", required=False, type=str, location=OpenApiParameter.QUERY),
        OpenApiParameter(name="search", description="Search by driver first/last name or UUID", required=False, type=str, location=OpenApiParameter.QUERY),
    ]
)
class TripRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing trip records"""

    queryset = TripRecord.objects.all()
    serializer_class = TripRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TripRecordFilterSet
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid', 'trip_uuid', 'supervisor_name_at_calculation']
    ordering_fields = ['created_at', 'order_time', 'fare_amount', 'trip_distance', 'trip_duration_minutes']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """Get queryset with select_related for performance."""
        return super().get_queryset().select_related('file_upload__company', 'driver')

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
        by_status = qs.values('trip_status').annotate(count=Count('id')).order_by()
        by_service = qs.values('service_type').annotate(count=Count('id')).order_by()
        top_drivers_qs = (
            qs.values('driver_uuid', 'driver_first_name', 'driver_last_name')
            .annotate(
                trips=Count('id'),
                fare=Sum('fare_amount'),
            )
            .order_by('-fare')[:3]
        )
        top_drivers = list(top_drivers_qs)
        # Map driver_uuid -> driver_id
        uuids = [d['driver_uuid'] for d in top_drivers if d.get('driver_uuid')]
        uuid_to_id = {
            row['uuid']: row['id']
            for row in Driver.objects.filter(uuid__in=uuids).values('uuid', 'id')
        }
        for d in top_drivers:
            d['driver_id'] = uuid_to_id.get(d.get('driver_uuid'))
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

        Query Parameters:
            - group_by: Comma-separated grouping dimensions (driver, supervisor, period, status, company)
                       Examples: "driver", "supervisor", "driver,period", "driver,period,status"
                       Default: "driver,period,status" (backward compatible)
            - driver_id: Filter by specific driver
            - supervisor_id: Filter by specific supervisor
            - Other filters from TripRecordFilterSet apply

        Returns paginated aggregated results.
        """
        from ..utils.aggregation import AggregationService
        from ..api.serializers import TripRecordAggregatedSerializer

        # Get group_by parameter (default to backward-compatible grouping)
        group_by = request.query_params.get('group_by', 'driver,period,status').strip()
        driver_id = request.query_params.get('driver_id')
        supervisor_id = request.query_params.get('supervisor_id')

        # Get base queryset with filters applied
        queryset = self.filter_queryset(self.get_queryset())

        # Apply aggregation
        aggregated_qs = AggregationService.aggregate_trips(
            queryset,
            group_by=group_by if group_by else None,
            supervisor_id=int(supervisor_id) if supervisor_id else None,
            driver_id=int(driver_id) if driver_id else None
        )

        # Convert to list and format results
        results = []
        for row in aggregated_qs:
            formatted = AggregationService.format_trip_aggregation_result(row)
            results.append(formatted)

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(results, request)
        if page is not None:
            serializer = TripRecordAggregatedSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = TripRecordAggregatedSerializer(results, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Export aggregated trip records as CSV."
    )
    @action(detail=False, methods=['get'], url_path='aggregated/export')
    def export_aggregated(self, request):
        """Export aggregated trip records as CSV with all current filters applied."""
        try:
            from ..utils.aggregation import AggregationService
            import csv
            from io import StringIO
            from django.http import HttpResponse

            # Get group_by parameter (default to backward-compatible grouping)
            group_by = request.query_params.get('group_by', 'driver,period,status').strip()
            driver_id = request.query_params.get('driver_id')
            supervisor_id = request.query_params.get('supervisor_id')

            # Get base queryset with filters applied
            queryset = self.filter_queryset(self.get_queryset())

            # Apply aggregation
            aggregated_qs = AggregationService.aggregate_trips(
                queryset,
                group_by=group_by if group_by else None,
                supervisor_id=int(supervisor_id) if supervisor_id else None,
                driver_id=int(driver_id) if driver_id else None
            )

            # Convert to list and format results
            results = []
            for row in aggregated_qs:
                formatted = AggregationService.format_trip_aggregation_result(row)
                results.append(formatted)

            record_count = len(results)

            # Safe logging
            try:
                logger.info(
                    f"Aggregated trip records export started | user={request.user.username} | count={record_count} | group_by={group_by}"
                )
            except Exception:
                pass

            # Prepare CSV data
            buffer = StringIO()
            writer = csv.writer(buffer)

            # Determine headers based on group_by
            if 'supervisor' in group_by and 'driver' not in group_by:
                writer.writerow([
                    "Supervisor ID", "Supervisor Name", "Driver Count", "Company",
                    "Total Fare", "Total Distance", "Avg Distance", "Trip Count", "Avg Duration (min)"
                ])
                for row in results:
                    writer.writerow([
                        row.get('supervisor_id_at_calculation') or "",
                        row.get('supervisor_name_at_calculation') or "",
                        row.get('driver_count') or 0,
                        row.get('company_name') or "",
                        row.get('total_fare') or 0,
                        row.get('total_distance') or 0,
                        row.get('avg_distance') or 0,
                        row.get('trip_count') or 0,
                        row.get('avg_duration') or 0,
                    ])
            elif 'driver' in group_by:
                writer.writerow([
                    "Driver ID", "Driver UUID", "Driver Name", "Supervisor Name", "Company",
                    "Period From", "Period To", "Trip Status",
                    "Total Fare", "Total Distance", "Avg Distance", "Trip Count", "Avg Duration (min)"
                ])
                for row in results:
                    writer.writerow([
                        row.get('driver_id') or "",
                        row.get('driver_uuid') or "",
                        row.get('driver_name') or "",
                        row.get('supervisor_name_at_calculation') or "",
                        row.get('company_name') or "",
                        row.get('from_date') or "",
                        row.get('to_date') or "",
                        row.get('trip_status') or "",
                        row.get('total_fare') or 0,
                        row.get('total_distance') or 0,
                        row.get('avg_distance') or 0,
                        row.get('trip_count') or 0,
                        row.get('avg_duration') or 0,
                    ])
            else:
                # Default headers
                writer.writerow([
                    "Driver ID", "Driver UUID", "Driver Name", "Supervisor Name", "Company",
                    "Total Fare", "Total Distance", "Avg Distance", "Trip Count", "Avg Duration (min)"
                ])
                for row in results:
                    writer.writerow([
                        row.get('driver_id') or "",
                        row.get('driver_uuid') or "",
                        row.get('driver_name') or "",
                        row.get('supervisor_name_at_calculation') or "",
                        row.get('company_name') or "",
                        row.get('total_fare') or 0,
                        row.get('total_distance') or 0,
                        row.get('avg_distance') or 0,
                        row.get('trip_count') or 0,
                        row.get('avg_duration') or 0,
                    ])

            # Safe logging
            try:
                logger.info(
                    f"Aggregated trip records export completed | user={request.user.username} | count={record_count}"
                )
            except Exception:
                pass

            # Create HTTP response
            group_name = group_by.replace(',', '_') if group_by else 'raw'
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="trip_records_aggregated_{group_name}_{timezone.now().date()}.csv"'
            return response

        except Exception as e:
            log_error(e, context="Trip records export failed", user=request.user.username)
            raise

    @action(detail=False, methods=['get'])
    def timeseries(self, request):
        """Trips per day and fare sum. Supports segments and monthly=auto (see payments)."""
        from django.db.models import Sum, Count
        import datetime, calendar
        qs = self.filter_queryset(self.get_queryset())
        if request.query_params.get('period') == 'upload':
            series = (
                qs.values('file_upload_id', 'file_upload__from_date', 'file_upload__to_date', 'file_upload__company__name')
                .annotate(
                    trips=Count('id'),
                    fare=Sum('fare_amount'),
                )
                .order_by('file_upload__from_date')
            )
            result = []
            for row in series:
                result.append({
                    'upload_id': row['file_upload_id'],
                    'from_date': row['file_upload__from_date'],
                    'to_date': row['file_upload__to_date'],
                    'company': row['file_upload__company__name'],
                    'trips': row['trips'],
                    'fare': row['fare'],
                })
            return Response(result)
        series = (
            qs.annotate(day=TruncDay('order_time'))
            .values('day')
            .annotate(
                trips=Count('id'),
                fare=Sum('fare_amount'),
            )
            .order_by('day')
        )
        segments = request.query_params.get('segments') == 'true'
        monthly = request.query_params.get('monthly') == 'auto'
        if not segments:
            return Response(list(series))

        gap_days = int(request.query_params.get('gap_days') or 3)
        items = list(series)
        out = []
        current = None
        prev_day = None
        days_in_segment = set()
        for row in items:
            day = row['day'].date() if hasattr(row['day'], 'date') else row['day']
            if prev_day is None or (day - prev_day).days >= gap_days:
                if current:
                    if monthly:
                        start = current['start']
                        end = current['end']
                        if start.day == 1 and start.month == end.month and start.year == end.year:
                            _, mdays = calendar.monthrange(start.year, start.month)
                            if (end.day == mdays) and (len(days_in_segment) == mdays):
                                current['period_type'] = 'month'
                                current['month'] = start.strftime('%Y-%m')
                    out.append(current)
                current = {
                    'start': day,
                    'end': day,
                    'trips': row['trips'] or 0,
                    'fare': row['fare'] or 0,
                    'period_type': 'range',
                }
                days_in_segment = {day}
            else:
                current['end'] = day
                current['trips'] += row['trips'] or 0
                current['fare'] += row['fare'] or 0
                days_in_segment.add(day)
            prev_day = day
        if current:
            if monthly:
                start = current['start']
                end = current['end']
                if start.day == 1 and start.month == end.month and start.year == end.year:
                    _, mdays = calendar.monthrange(start.year, start.month)
                    if (end.day == mdays) and (len(days_in_segment) == mdays):
                        current['period_type'] = 'month'
                        current['month'] = start.strftime('%Y-%m')
            out.append(current)
        return Response(out)
