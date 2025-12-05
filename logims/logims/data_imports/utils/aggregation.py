"""
Reusable aggregation utilities for Payment and Trip records.
Supports flexible grouping by driver, supervisor, period, status, etc.
"""
from typing import Dict, List, Any, Optional, Tuple
from django.db.models import QuerySet, Sum, Count, Avg, Max, Min, Q
from django.db.models.functions import Coalesce
from decimal import Decimal


class AggregationService:
    """Service for aggregating payment and trip records with flexible grouping"""

    @staticmethod
    def get_group_by_fields(group_by: str, model_type: str = 'payment') -> Tuple[List[str], bool]:
        """
        Parse group_by parameter and return list of fields to group by.

        Args:
            group_by: Comma-separated string like "driver,period" or "supervisor"
            model_type: 'payment' or 'trip'

        Returns:
            Tuple of (list of field names for values() grouping, includes_driver)
        """
        if not group_by:
            return [], False

        groups = [g.strip().lower() for g in group_by.split(',')]
        fields = []
        includes_driver = False

        for group in groups:
            if group == 'driver':
                fields.extend(['driver_id_at_calculation', 'driver_uuid', 'driver_first_name', 'driver_last_name'])
                # Include supervisor fields when grouping by driver so they're available in results
                fields.extend(['supervisor_id_at_calculation', 'supervisor_name_at_calculation'])
                includes_driver = True
            elif group == 'supervisor':
                # Use calculation snapshot fields for supervisor
                fields.extend(['supervisor_id_at_calculation', 'supervisor_name_at_calculation'])
            elif group == 'period':
                fields.extend(['file_upload__from_date', 'file_upload__to_date'])
            elif group == 'company':
                fields.extend(['file_upload__company__id', 'file_upload__company__name', 'file_upload__company__code'])
            elif group == 'file_upload':
                fields.append('file_upload')
            elif group == 'status' and model_type == 'trip':
                fields.append('trip_status')

        return fields, includes_driver

    @staticmethod
    def get_aggregation_annotations(model_type: str = 'payment') -> Dict[str, Any]:
        """
        Get aggregation annotations based on model type.

        Args:
            model_type: 'payment' or 'trip'

        Returns:
            Dictionary of annotation expressions
        """
        if model_type == 'payment':
            return {
                'total_revenue': Coalesce(Sum('total_revenue'), Decimal('0')),
                'tips': Coalesce(Sum('tips'), Decimal('0')),
                'total_deductions': Coalesce(Sum('total_deductions'), Decimal('0')),
                'tax_deduction': Coalesce(Sum('tax_deduction'), Decimal('0')),
                'agency_share_deduction': Coalesce(Sum('agency_share_deduction'), Decimal('0')),
                'insurance_deduction': Coalesce(Sum('insurance_deduction'), Decimal('0')),
                'final_net_earnings': Coalesce(Sum('final_net_earnings'), Decimal('0')),
                'payouts': Coalesce(Sum('payouts'), Decimal('0')),
                'record_count': Count('id'),
            }
        else:  # trip
            return {
                'total_fare': Coalesce(Sum('fare_amount'), Decimal('0')),
                'total_distance': Coalesce(Sum('trip_distance'), Decimal('0')),
                'avg_distance': Avg('trip_distance'),
                'trip_count': Count('id'),
                'avg_duration': Avg('trip_duration_minutes'),
            }

    @staticmethod
    def aggregate_payments(
        queryset: QuerySet,
        group_by: Optional[str] = None,
        supervisor_id: Optional[int] = None,
        driver_id: Optional[int] = None
    ) -> QuerySet:
        """
        Aggregate payment records with flexible grouping.

        Args:
            queryset: Filtered PaymentRecord queryset
            group_by: Comma-separated grouping dimensions (driver, supervisor, period, company)
            supervisor_id: Optional filter by supervisor
            driver_id: Optional filter by driver

        Returns:
            Aggregated queryset
        """
        # Apply supervisor/driver filters using calculation snapshot fields
        if supervisor_id:
            queryset = queryset.filter(supervisor_id_at_calculation=supervisor_id)
        if driver_id:
            queryset = queryset.filter(driver_id_at_calculation=driver_id)

        # Optimize queryset
        queryset = queryset.select_related(
            'driver', 'driver__supervisor', 'file_upload', 'file_upload__company'
        )

        if not group_by:
            # No aggregation, return records as-is
            return queryset

        # Get grouping fields
        group_fields, includes_driver = AggregationService.get_group_by_fields(group_by, 'payment')

        if not group_fields:
            # Invalid group_by, return records
            return queryset

        # Get aggregation annotations
        annotations = AggregationService.get_aggregation_annotations('payment')

        # For supervisor-only grouping, we need to count distinct drivers
        if 'supervisor' in group_by.lower() and not includes_driver:
            annotations['driver_count'] = Count('driver_id_at_calculation', distinct=True)

        # Perform aggregation
        aggregated = queryset.values(*group_fields).annotate(**annotations)

        # Apply sensible ordering based on grouping
        if 'supervisor' in group_by.lower() and not includes_driver:
            # Order by supervisor name, then period, then company
            order_fields = ['supervisor_name_at_calculation']
            if 'period' in group_by.lower():
                order_fields.append('file_upload__from_date')
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)
        elif includes_driver:
            # Order by driver name, then period, then company
            order_fields = ['driver_first_name', 'driver_last_name']
            if 'period' in group_by.lower():
                order_fields.append('file_upload__from_date')
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)
        elif 'period' in group_by.lower():
            # Order by period, then company
            order_fields = ['file_upload__from_date']
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)

        return aggregated

    @staticmethod
    def aggregate_trips(
        queryset: QuerySet,
        group_by: Optional[str] = None,
        supervisor_id: Optional[int] = None,
        driver_id: Optional[int] = None
    ) -> QuerySet:
        """
        Aggregate trip records with flexible grouping.

        Args:
            queryset: Filtered TripRecord queryset
            group_by: Comma-separated grouping dimensions (driver, supervisor, period, status, company)
            supervisor_id: Optional filter by supervisor
            driver_id: Optional filter by driver

        Returns:
            Aggregated queryset
        """
        # Apply supervisor/driver filters using calculation snapshot fields
        if supervisor_id:
            queryset = queryset.filter(supervisor_id_at_calculation=supervisor_id)
        if driver_id:
            queryset = queryset.filter(driver_id_at_calculation=driver_id)

        # Optimize queryset
        queryset = queryset.select_related(
            'driver', 'driver__supervisor', 'file_upload', 'file_upload__company'
        )

        if not group_by:
            # No aggregation, return records as-is
            return queryset

        # Get grouping fields
        group_fields, includes_driver = AggregationService.get_group_by_fields(group_by, 'trip')

        if not group_fields:
            # Invalid group_by, return records
            return queryset

        # Get aggregation annotations
        annotations = AggregationService.get_aggregation_annotations('trip')

        # For supervisor-only grouping, we need to count distinct drivers
        if 'supervisor' in group_by.lower() and not includes_driver:
            annotations['driver_count'] = Count('driver_id_at_calculation', distinct=True)

        # Perform aggregation
        aggregated = queryset.values(*group_fields).annotate(**annotations)

        # Apply sensible ordering based on grouping
        if 'supervisor' in group_by.lower() and not includes_driver:
            # Order by supervisor name, then period, then status, then company
            order_fields = ['supervisor_name_at_calculation']
            if 'period' in group_by.lower():
                order_fields.append('file_upload__from_date')
            if 'status' in group_by.lower():
                order_fields.append('trip_status')
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)
        elif includes_driver:
            # Order by driver name, then period, then status, then company
            order_fields = ['driver_first_name', 'driver_last_name']
            if 'period' in group_by.lower():
                order_fields.append('file_upload__from_date')
            if 'status' in group_by.lower():
                order_fields.append('trip_status')
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)
        elif 'period' in group_by.lower():
            # Order by period, then status, then company
            order_fields = ['file_upload__from_date']
            if 'status' in group_by.lower():
                order_fields.append('trip_status')
            if 'company' in group_by.lower():
                order_fields.append('file_upload__company__name')
            aggregated = aggregated.order_by(*order_fields)

        return aggregated

    @staticmethod
    def format_payment_aggregation_result(row) -> Dict[str, Any]:
        """
        Format a payment aggregation row into a standardized structure.

        Args:
            row: Dictionary from aggregated queryset or PaymentRecord model instance

        Returns:
            Formatted dictionary with standardized field names
        """
        # Handle model instance (when no group_by)
        if hasattr(row, '_meta'):
            # Convert model instance to dictionary
            row_dict = {
                'driver_id_at_calculation': getattr(row, 'driver_id_at_calculation', None),
                'driver_uuid': getattr(row, 'driver_uuid', ''),
                'driver_first_name': getattr(row, 'driver_first_name', ''),
                'driver_last_name': getattr(row, 'driver_last_name', ''),
                'supervisor_id_at_calculation': getattr(row, 'supervisor_id_at_calculation', None),
                'supervisor_name_at_calculation': getattr(row, 'supervisor_name_at_calculation', ''),
                'file_upload__company__id': row.file_upload.company.id if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else None,
                'file_upload__company__name': row.file_upload.company.name if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else '',
                'file_upload__company__code': row.file_upload.company.code if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else '',
                'file_upload': row.file_upload.id if hasattr(row, 'file_upload') and row.file_upload else None,
                'file_upload__from_date': row.file_upload.from_date if hasattr(row, 'file_upload') and row.file_upload else None,
                'file_upload__to_date': row.file_upload.to_date if hasattr(row, 'file_upload') and row.file_upload else None,
                'total_revenue': getattr(row, 'total_revenue', None) or Decimal('0'),
                'tips': getattr(row, 'tips', None) or Decimal('0'),
                'total_deductions': getattr(row, 'total_deductions', None) or Decimal('0'),
                'tax_deduction': getattr(row, 'tax_deduction', None) or Decimal('0'),
                'agency_share_deduction': getattr(row, 'agency_share_deduction', None) or Decimal('0'),
                'insurance_deduction': getattr(row, 'insurance_deduction', None) or Decimal('0'),
                'final_net_earnings': getattr(row, 'final_net_earnings', None) or Decimal('0'),
                'payouts': getattr(row, 'payouts', None) or Decimal('0'),
                'record_count': 1,
            }
            row = row_dict

        # Now row is guaranteed to be a dictionary
        driver_first_name = row.get('driver_first_name', '')
        driver_last_name = row.get('driver_last_name', '')
        driver_name = f"{driver_first_name} {driver_last_name}".strip() if driver_first_name or driver_last_name else ''

        result = {
            'driver_id': row.get('driver_id_at_calculation'),
            'driver_uuid': row.get('driver_uuid', ''),
            'driver_first_name': driver_first_name,
            'driver_last_name': driver_last_name,
            'driver_name': driver_name,
            'supervisor_id_at_calculation': row.get('supervisor_id_at_calculation'),
            'supervisor_name_at_calculation': row.get('supervisor_name_at_calculation', ''),
            'company_id': row.get('file_upload__company__id'),
            'company_name': row.get('file_upload__company__name', ''),
            'company_code': row.get('file_upload__company__code', ''),
            'file_upload': row.get('file_upload'),
            'from_date': row.get('file_upload__from_date'),
            'to_date': row.get('file_upload__to_date'),
            'total_revenue': row.get('total_revenue', Decimal('0')),
            'tips': row.get('tips', Decimal('0')),
            'total_deductions': row.get('total_deductions', Decimal('0')),
            'tax_deduction': row.get('tax_deduction', Decimal('0')),
            'agency_share_deduction': row.get('agency_share_deduction', Decimal('0')),
            'insurance_deduction': row.get('insurance_deduction', Decimal('0')),
            'final_net_earnings': row.get('final_net_earnings', Decimal('0')),
            'payouts': row.get('payouts', Decimal('0')),
            'record_count': row.get('record_count', 0),
            'driver_count': row.get('driver_count'),  # For supervisor-level aggregation
        }

        # Remove None values for cleaner output (but keep important IDs)
        return {k: v for k, v in result.items() if v is not None or k in ['driver_id', 'supervisor_id_at_calculation', 'company_id', 'file_upload']}

    @staticmethod
    def format_trip_aggregation_result(row) -> Dict[str, Any]:
        """
        Format a trip aggregation row into a standardized structure.

        Args:
            row: Dictionary from aggregated queryset or TripRecord model instance

        Returns:
            Formatted dictionary with standardized field names
        """
        # Handle model instance (when no group_by)
        if hasattr(row, '_meta'):
            # Convert model instance to dictionary
            row_dict = {
                'driver_id_at_calculation': getattr(row, 'driver_id_at_calculation', None),
                'driver_uuid': getattr(row, 'driver_uuid', ''),
                'driver_first_name': getattr(row, 'driver_first_name', ''),
                'driver_last_name': getattr(row, 'driver_last_name', ''),
                'supervisor_id_at_calculation': getattr(row, 'supervisor_id_at_calculation', None),
                'supervisor_name_at_calculation': getattr(row, 'supervisor_name_at_calculation', ''),
                'file_upload__company__id': row.file_upload.company.id if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else None,
                'file_upload__company__name': row.file_upload.company.name if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else '',
                'file_upload__company__code': row.file_upload.company.code if hasattr(row, 'file_upload') and row.file_upload and hasattr(row.file_upload, 'company') and row.file_upload.company else '',
                'file_upload': row.file_upload.id if hasattr(row, 'file_upload') and row.file_upload else None,
                'file_upload__from_date': row.file_upload.from_date if hasattr(row, 'file_upload') and row.file_upload else None,
                'file_upload__to_date': row.file_upload.to_date if hasattr(row, 'file_upload') and row.file_upload else None,
                'trip_status': getattr(row, 'trip_status', None),
                'total_fare': getattr(row, 'fare_amount', None) or Decimal('0'),
                'total_distance': getattr(row, 'trip_distance', None) or Decimal('0'),
                'avg_distance': getattr(row, 'trip_distance', None),
                'trip_count': 1,
                'avg_duration': getattr(row, 'trip_duration_minutes', None),
            }
            row = row_dict

        # Now row is guaranteed to be a dictionary
        driver_first_name = row.get('driver_first_name', '')
        driver_last_name = row.get('driver_last_name', '')
        driver_name = f"{driver_first_name} {driver_last_name}".strip() if driver_first_name or driver_last_name else ''

        result = {
            'driver_id': row.get('driver_id_at_calculation'),
            'driver_uuid': row.get('driver_uuid', ''),
            'driver_first_name': driver_first_name,
            'driver_last_name': driver_last_name,
            'driver_name': driver_name,
            'supervisor_id_at_calculation': row.get('supervisor_id_at_calculation'),
            'supervisor_name_at_calculation': row.get('supervisor_name_at_calculation', ''),
            'company_id': row.get('file_upload__company__id'),
            'company_name': row.get('file_upload__company__name', ''),
            'company_code': row.get('file_upload__company__code', ''),
            'file_upload': row.get('file_upload'),
            'from_date': row.get('file_upload__from_date'),
            'to_date': row.get('file_upload__to_date'),
            'trip_status': row.get('trip_status'),
            'total_fare': row.get('total_fare', Decimal('0')),
            'total_distance': row.get('total_distance', Decimal('0')),
            'avg_distance': row.get('avg_distance'),
            'trip_count': row.get('trip_count', 0),
            'avg_duration': row.get('avg_duration'),
            'driver_count': row.get('driver_count'),  # For supervisor-level aggregation
        }

        # Remove None values for cleaner output (but keep important IDs)
        return {k: v for k, v in result.items() if v is not None or k in ['driver_id', 'supervisor_id_at_calculation', 'company_id', 'file_upload', 'trip_status']}

