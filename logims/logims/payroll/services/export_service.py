"""
Export service for payment records.
Handles CSV export logic separated from viewset.
"""
import csv
from io import StringIO
from typing import List, Dict, Any
from django.http import HttpResponse
from django.utils import timezone


class PaymentExportService:
    """Service for exporting payment records to CSV"""

    @staticmethod
    def export_aggregated(
        results: List[Dict[str, Any]],
        group_by: str
    ) -> HttpResponse:
        """
        Export aggregated payment records as CSV.

        Args:
            results: List of aggregated payment records
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
            if 'company' in group_by_lower:
                headers.append("Company")
            headers.extend([
                "Total Revenue", "Tips", "Total Deductions", "Tax Deduction",
                "Agency Share Deduction", "Insurance Deduction", "Final Net Earnings",
                "Payouts", "Record Count"
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
            headers = ["Driver ID", "Driver UUID", "Driver Name", "Supervisor Name"]
            if 'period' in group_by_lower:
                headers.extend(["Period From", "Period To"])
            if 'company' in group_by_lower:
                headers.append("Company")
            headers.extend([
                "Total Revenue", "Tips", "Total Deductions", "Tax Deduction",
                "Agency Share Deduction", "Insurance Deduction", "Final Net Earnings",
                "Payouts", "Record Count"
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
            # Default headers
            headers = [
                "Driver ID", "Driver UUID", "Driver Name", "Supervisor Name", "Company",
                "Total Revenue", "Tips", "Total Deductions", "Tax Deduction",
                "Agency Share Deduction", "Insurance Deduction", "Final Net Earnings",
                "Payouts", "Record Count"
            ]
            writer.writerow(headers)

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

        group_name = group_by or 'raw'
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="payment_records_aggregated_{group_name}_{timezone.now().date()}.csv"'
        )
        return response

    @staticmethod
    def export_records(queryset) -> HttpResponse:
        """
        Export payment records as CSV.

        Args:
            queryset: QuerySet of PaymentRecord instances

        Returns:
            HttpResponse with CSV content
        """
        buffer = StringIO()
        writer = csv.writer(buffer)

        headers = [
            "ID", "Upload ID", "Period From", "Period To", "Company", "Driver UUID",
            "Driver Name", "Total Revenue", "Net Fare", "Promotions", "Refunds and Fees",
            "Payouts", "Bank Transfer", "Cash Collected", "Fare Tax", "Tips", "Taxes",
            "Other Revenue", "Total Deductions", "Tax Deduction", "Agency Share Deduction",
            "Insurance Deduction", "Final Net Earnings", "Created At"
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

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="payment_records_export_{timezone.now().date()}.csv"'
        return response
