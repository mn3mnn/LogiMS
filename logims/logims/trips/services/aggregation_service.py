"""
Trip aggregation service.
"""
from typing import Dict, List, Any, Optional, Tuple
from django.db.models import QuerySet, Sum, Count, Avg
from django.db.models.functions import Coalesce
from decimal import Decimal
from logims.uploads.utils.base_aggregation import BaseAggregationService


class TripAggregationService:
    """
    Service for aggregating trip records with flexible grouping.
    """

    @staticmethod
    def get_group_by_fields(group_by: str) -> Tuple[List[str], bool]:
        """
        Parse group_by parameter and return list of fields to group by.
        Uses base aggregation service for common logic.
        """
        return BaseAggregationService.get_group_by_fields(
            group_by=group_by,
            driver_fields=[
                'driver_id_at_calculation', 'driver_uuid', 'driver_first_name', 'driver_last_name',
                'supervisor_id_at_calculation', 'supervisor_name_at_calculation'
            ],
            supervisor_fields=['supervisor_id_at_calculation', 'supervisor_name_at_calculation'],
            period_fields=['file_upload__metadata__from_date', 'file_upload__metadata__to_date'],
            company_fields=[
                'file_upload__metadata__company__id',
                'file_upload__metadata__company__name',
                'file_upload__metadata__company__code'
            ],
            file_upload_field='file_upload',
            status_field='trip_status'
        )

    @staticmethod
    def get_aggregation_annotations() -> Dict[str, Any]:
        """
        Get aggregation annotations for trips.
        """
        return {
            'total_fare': Coalesce(Sum('fare_amount'), Decimal('0')),
            'total_distance': Coalesce(Sum('trip_distance'), Decimal('0')),
            'avg_distance': Avg('trip_distance'),
            'trip_count': Count('id'),
            'avg_duration': Avg('trip_duration_minutes'),
        }

    @staticmethod
    def aggregate_trips(
        queryset: QuerySet,
        group_by: Optional[str] = None,
        supervisor_id: Optional[int] = None,
        driver_id: Optional[int] = None
    ) -> QuerySet:
        """
        Aggregate trip records with flexible grouping.
        """
        # Apply supervisor/driver filters using calculation snapshot fields
        # Apply filters before select_related for better query planning
        if supervisor_id:
            queryset = queryset.filter(supervisor_id_at_calculation=supervisor_id)
        if driver_id:
            queryset = queryset.filter(driver_id_at_calculation=driver_id)

        # Optimize queryset - select_related is safe to apply multiple times
        # This ensures related objects are loaded even if queryset already has select_related
        queryset = queryset.select_related(
            'driver', 'driver__supervisor', 'file_upload', 'file_upload__metadata', 'file_upload__metadata__company'
        )

        if not group_by:
            # No aggregation, return records as-is
            return queryset

        # Get grouping fields
        group_fields, includes_driver = TripAggregationService.get_group_by_fields(group_by)

        if not group_fields:
            # Invalid group_by, return records
            return queryset

        # Get aggregation annotations
        annotations = TripAggregationService.get_aggregation_annotations()

        # For supervisor-only grouping, we need to count distinct drivers
        annotations = BaseAggregationService.add_driver_count_annotation(
            annotations, group_by, includes_driver, 'driver_id_at_calculation'
        )

        # Perform aggregation
        aggregated = queryset.values(*group_fields).annotate(**annotations)

        # Apply sensible ordering based on grouping
        order_fields = BaseAggregationService.build_order_fields(
            group_by=group_by,
            includes_driver=includes_driver,
            supervisor_name_field='supervisor_name_at_calculation',
            driver_name_fields=['driver_first_name', 'driver_last_name'],
            period_from_field='file_upload__metadata__from_date',
            company_name_field='file_upload__metadata__company__name',
            status_field='trip_status'
        )
        aggregated = aggregated.order_by(*order_fields)

        return aggregated

    @staticmethod
    def format_trip_aggregation_result(row) -> Dict[str, Any]:
        """
        Format a trip aggregation row into a standardized structure.
        """
        # Handle model instance (when no group_by)
        if hasattr(row, '_meta'):
            metadata = row.file_upload.metadata if hasattr(row, 'file_upload') and row.file_upload else None
            row_dict = {
                'driver_id_at_calculation': getattr(row, 'driver_id_at_calculation', None),
                'driver_uuid': getattr(row, 'driver_uuid', ''),
                'driver_first_name': getattr(row, 'driver_first_name', ''),
                'driver_last_name': getattr(row, 'driver_last_name', ''),
                'supervisor_id_at_calculation': getattr(row, 'supervisor_id_at_calculation', None),
                'supervisor_name_at_calculation': getattr(row, 'supervisor_name_at_calculation', ''),
                'file_upload__metadata__company__id': metadata.company.id if metadata and metadata.company else None,
                'file_upload__metadata__company__name': metadata.company.name if metadata and metadata.company else '',
                'file_upload__metadata__company__code': metadata.company.code if metadata and metadata.company else '',
                'file_upload': row.file_upload.id if hasattr(row, 'file_upload') and row.file_upload else None,
                'file_upload__metadata__from_date': metadata.from_date if metadata else None,
                'file_upload__metadata__to_date': metadata.to_date if metadata else None,
                'trip_status': getattr(row, 'trip_status', None),
                'total_fare': getattr(row, 'fare_amount', None) or Decimal('0'),
                'total_distance': getattr(row, 'trip_distance', None) or Decimal('0'),
                'avg_distance': getattr(row, 'trip_distance', None),
                'trip_count': 1,
                'avg_duration': getattr(row, 'trip_duration_minutes', None),
            }
            row = row_dict

        # Now row is guaranteed to be a dictionary
        driver_name = BaseAggregationService.format_driver_name(row)

        result = {
            'driver_id': row.get('driver_id_at_calculation'),
            'driver_uuid': row.get('driver_uuid', ''),
            'driver_first_name': row.get('driver_first_name', ''),
            'driver_last_name': row.get('driver_last_name', ''),
            'driver_name': driver_name,
            'supervisor_id_at_calculation': row.get('supervisor_id_at_calculation'),
            'supervisor_name_at_calculation': row.get('supervisor_name_at_calculation', ''),
            'company_id': row.get('file_upload__metadata__company__id'),
            'company_name': row.get('file_upload__metadata__company__name', ''),
            'company_code': row.get('file_upload__metadata__company__code', ''),
            'file_upload': row.get('file_upload'),
            'from_date': row.get('file_upload__metadata__from_date'),
            'to_date': row.get('file_upload__metadata__to_date'),
            'trip_status': row.get('trip_status'),
            'total_fare': row.get('total_fare', Decimal('0')),
            'total_distance': row.get('total_distance', Decimal('0')),
            'avg_distance': row.get('avg_distance'),
            'trip_count': row.get('trip_count', 0),
            'avg_duration': row.get('avg_duration'),
            'driver_count': row.get('driver_count'),
        }

        # Remove None values for cleaner output (but keep important IDs)
        return {k: v for k, v in result.items() if v is not None or k in ['driver_id', 'supervisor_id_at_calculation', 'company_id', 'file_upload', 'trip_status']}
