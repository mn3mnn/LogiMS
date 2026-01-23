"""
Export service for trip records.
Handles CSV export logic separated from viewset.
"""
import csv
from io import StringIO
from typing import List, Dict, Any
from django.http import HttpResponse
from django.utils import timezone
from ..services.aggregation_service import TripAggregationService


class TripExportService:
    """Service for exporting trip records to CSV"""

    @staticmethod
    def export_aggregated(
        results: List[Dict[str, Any]],
        group_by: str
    ) -> HttpResponse:
        """
        Export aggregated trip records as CSV.

        Args:
            results: List of aggregated trip records
            group_by: Grouping parameter used for aggregation

        Returns:
            HttpResponse with CSV content
        """
        buffer = StringIO()
        writer = csv.writer(buffer)

        group_by_lower = group_by.lower()

        # Determine headers and write data based on group_by
        if 'supervisor' in group_by_lower and 'driver' not in group_by_lower:
            headers = ["Supervisor ID", "Supervisor Name", "Driver Count"]
            if 'period' in group_by_lower:
                headers.extend(["Period From", "Period To"])
            if 'status' in group_by_lower:
                headers.append("Trip Status")
            if 'company' in group_by_lower:
                headers.append("Company")
            headers.extend([
                "Total Fare", "Total Distance", "Avg Distance",
                "Trip Count", "Avg Duration (min)"
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
                if 'status' in group_by_lower:
                    row_data.append(row.get('trip_status') or "")
                if 'company' in group_by_lower:
                    row_data.append(row.get('company_name') or "")
                row_data.extend([
                    row.get('total_fare') or 0,
                    row.get('total_distance') or 0,
                    row.get('avg_distance') or 0,
                    row.get('trip_count') or 0,
                    row.get('avg_duration') or 0,
                ])
                writer.writerow(row_data)

        elif 'driver' in group_by_lower:
            headers = ["Driver ID", "Driver UUID", "Driver Name", "Supervisor Name"]
            if 'period' in group_by_lower:
                headers.extend(["Period From", "Period To"])
            if 'status' in group_by_lower:
                headers.append("Trip Status")
            if 'company' in group_by_lower:
                headers.append("Company")
            headers.extend([
                "Total Fare", "Total Distance", "Avg Distance",
                "Trip Count", "Avg Duration (min)"
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
                if 'status' in group_by_lower:
                    row_data.append(row.get('trip_status') or "")
                if 'company' in group_by_lower:
                    row_data.append(row.get('company_name') or "")
                row_data.extend([
                    row.get('total_fare') or 0,
                    row.get('total_distance') or 0,
                    row.get('avg_distance') or 0,
                    row.get('trip_count') or 0,
                    row.get('avg_duration') or 0,
                ])
                writer.writerow(row_data)
        else:
            # Default headers
            headers = [
                "Driver ID", "Driver UUID", "Driver Name", "Supervisor Name", "Company",
                "Total Fare", "Total Distance", "Avg Distance", "Trip Count", "Avg Duration (min)"
            ]
            writer.writerow(headers)

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

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="trip_records_aggregated_{group_by or "raw"}_{timezone.now().date()}.csv"'
        )
        return response

    @staticmethod
    def export_records(queryset) -> HttpResponse:
        """
        Export trip records as CSV.

        Args:
            queryset: QuerySet of TripRecord instances

        Returns:
            HttpResponse with CSV content
        """
        buffer = StringIO()
        writer = csv.writer(buffer)

        headers = [
            "ID", "Upload ID", "Period From", "Period To", "Company", "Trip UUID",
            "Driver UUID", "Driver Name", "Vehicle UUID", "License Plate", "Service Type",
            "Order Time", "Arrival Time", "Pickup Address", "Destination Address",
            "Trip Distance", "Trip Status", "Fare Amount", "Trip Duration (minutes)", "Created At"
        ]
        writer.writerow(headers)

        for record in queryset.select_related('file_upload__metadata__company'):
            metadata = record.file_upload.metadata if hasattr(record.file_upload, 'metadata') else None
            writer.writerow([
                record.id,
                record.file_upload.id if record.file_upload else "",
                metadata.from_date if metadata else "",
                metadata.to_date if metadata else "",
                metadata.company.name if metadata and metadata.company else "",
                record.trip_uuid or "",
                record.driver_uuid or "",
                f"{record.driver_first_name} {record.driver_last_name}".strip(),
                record.vehicle_uuid or "",
                record.license_plate or "",
                record.service_type or "",
                record.order_time.strftime('%Y-%m-%d %H:%M:%S') if record.order_time else "",
                record.arrival_time.strftime('%Y-%m-%d %H:%M:%S') if record.arrival_time else "",
                record.pickup_address or "",
                record.destination_address or "",
                record.trip_distance or "",
                record.trip_status or "",
                record.fare_amount or "",
                record.trip_duration_minutes or "",
                record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else "",
            ])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="trip_records_export_{timezone.now().date()}.csv"'
        return response
