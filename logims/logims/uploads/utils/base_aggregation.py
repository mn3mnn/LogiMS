"""
Base aggregation service with common logic for trips and payments.
"""
from typing import Dict, List, Any, Optional, Tuple
from django.db.models import QuerySet, Count
from decimal import Decimal


class BaseAggregationService:
    """
    Base class for aggregation services.
    Provides common functionality for grouping and formatting.
    """

    @staticmethod
    def get_group_by_fields(
        group_by: str,
        driver_fields: List[str],
        supervisor_fields: List[str],
        period_fields: List[str],
        company_fields: List[str],
        file_upload_field: str,
        status_field: Optional[str] = None
    ) -> Tuple[List[str], bool]:
        """
        Parse group_by parameter and return list of fields to group by.

        Args:
            group_by: Comma-separated list of groups (e.g., 'driver,period,status')
            driver_fields: Fields to include when grouping by driver
            supervisor_fields: Fields to include when grouping by supervisor
            period_fields: Fields to include when grouping by period
            company_fields: Fields to include when grouping by company
            file_upload_field: Field name for file_upload grouping
            status_field: Optional field name for status grouping

        Returns:
            Tuple of (fields_list, includes_driver)
        """
        if not group_by:
            return [], False

        groups = [g.strip().lower() for g in group_by.split(',')]
        fields = []
        includes_driver = False

        for group in groups:
            if group == 'driver':
                fields.extend(driver_fields)
                includes_driver = True
            elif group == 'supervisor':
                fields.extend(supervisor_fields)
            elif group == 'period':
                fields.extend(period_fields)
            elif group == 'company':
                fields.extend(company_fields)
            elif group == 'file_upload':
                fields.append(file_upload_field)
            elif group == 'status' and status_field:
                fields.append(status_field)

        return fields, includes_driver

    @staticmethod
    def add_driver_count_annotation(
        annotations: Dict[str, Any],
        group_by: str,
        includes_driver: bool,
        driver_id_field: str
    ) -> Dict[str, Any]:
        """
        Add driver count annotation for supervisor-only grouping.

        Args:
            annotations: Dictionary of aggregation annotations
            group_by: Group by string
            includes_driver: Whether driver is included in grouping
            driver_id_field: Field name for driver ID

        Returns:
            Updated annotations dictionary
        """
        if 'supervisor' in group_by.lower() and not includes_driver:
            annotations['driver_count'] = Count(driver_id_field, distinct=True)
        return annotations

    @staticmethod
    def build_order_fields(
        group_by: str,
        includes_driver: bool,
        supervisor_name_field: str,
        driver_name_fields: List[str],
        period_from_field: str,
        company_name_field: str,
        status_field: Optional[str] = None
    ) -> List[str]:
        """
        Build ordering fields based on grouping.

        Args:
            group_by: Group by string
            includes_driver: Whether driver is included in grouping
            supervisor_name_field: Field name for supervisor name
            driver_name_fields: List of field names for driver name
            period_from_field: Field name for period start date
            company_name_field: Field name for company name
            status_field: Optional field name for status

        Returns:
            List of field names for ordering
        """
        order_fields = []

        if 'supervisor' in group_by.lower() and not includes_driver:
            order_fields.append(supervisor_name_field)
            if 'period' in group_by.lower():
                order_fields.append(period_from_field)
            if status_field and 'status' in group_by.lower():
                order_fields.append(status_field)
            if 'company' in group_by.lower():
                order_fields.append(company_name_field)
        elif includes_driver:
            order_fields.extend(driver_name_fields)
            if 'period' in group_by.lower():
                order_fields.append(period_from_field)
            if status_field and 'status' in group_by.lower():
                order_fields.append(status_field)
            if 'company' in group_by.lower():
                order_fields.append(company_name_field)
        elif 'period' in group_by.lower():
            order_fields.append(period_from_field)
            if status_field and 'status' in group_by.lower():
                order_fields.append(status_field)
            if 'company' in group_by.lower():
                order_fields.append(company_name_field)

        return order_fields if order_fields else ['id']  # Default ordering

    @staticmethod
    def format_driver_name(row: Dict[str, Any]) -> str:
        """
        Format driver name from first and last name fields.

        Args:
            row: Dictionary with driver name fields

        Returns:
            Formatted driver name string
        """
        driver_first_name = row.get('driver_first_name', '')
        driver_last_name = row.get('driver_last_name', '')
        return f"{driver_first_name} {driver_last_name}".strip() if driver_first_name or driver_last_name else ''
