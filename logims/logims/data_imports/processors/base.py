from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple
import pandas as pd
from django.db import transaction
from ..models import FileUpload, PaymentRecord, TripRecord


class BaseExcelProcessor(ABC):
    """Abstract base class for company-specific Excel file processing"""

    def __init__(self, file_upload: FileUpload):
        self.file_upload = file_upload
        self.company = file_upload.company

    def process_file(self) -> Tuple[int, str]:
        """
        Main processing method that handles the entire workflow
        Returns: (processed_records_count, status_message)
        """
        try:
            # Mark processing as started
            self.file_upload.mark_processing_started()

            # Read and validate Excel file
            df = self._read_excel_file()
            df = self._validate_and_clean_data(df)

            # Process based on file type
            if self.file_upload.file_type == 'payments':
                records_count = self._process_payments(df)
            elif self.file_upload.file_type == 'trips':
                records_count = self._process_trips(df)
            else:
                raise ValueError(f"Unknown file type: {self.file_upload.file_type}")

            # Mark as completed
            self.file_upload.mark_processing_completed(records_count)
            return records_count, "Processing completed successfully"

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.file_upload.mark_processing_failed(error_msg)
            raise e

    def _read_excel_file(self) -> pd.DataFrame:
        """Read Excel or CSV file and return DataFrame"""
        try:
            file_path = self.file_upload.file.path
            if file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            return df
        except Exception as e:
            raise ValueError(f"Failed to read file: {str(e)}")

    def _validate_and_clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean the DataFrame"""
        if df.empty:
            raise ValueError("File is empty")

        # Remove completely empty rows
        df = df.dropna(how='all')

        # Validate required columns exist
        required_columns = self._get_required_columns()
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        return df

    @abstractmethod
    def _get_required_columns(self) -> List[str]:
        """Return list of required column names for this company's format"""
        pass

    @abstractmethod
    def _process_payments(self, df: pd.DataFrame) -> int:
        """Process payment/payroll data"""
        pass

    @abstractmethod
    def _process_trips(self, df: pd.DataFrame) -> int:
        """Process trip/order data"""
        pass

    def _map_payment_data(self, row: pd.Series) -> Dict[str, Any]:
        """Map Excel row data to PaymentRecord fields"""
        # This will be overridden by company-specific processors
        return {}

    def _map_trip_data(self, row: pd.Series) -> Dict[str, Any]:
        """Map Excel row data to TripRecord fields"""
        # This will be overridden by company-specific processors
        return {}

    def _calculate_payment_fields(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate additional fields for payment records"""
        # Default calculations - can be overridden
        net_earnings = 0
        commission = 0

        if payment_data.get('payouts'):
            net_earnings = float(payment_data['payouts'])

        if payment_data.get('total_revenue') and payment_data.get('payouts'):
            commission = float(payment_data['total_revenue']) - float(payment_data['payouts'])

        # Get applied rates (default values)
        applied_tax_rate = payment_data.get('applied_tax_rate', 0)
        applied_agency_share_rate = payment_data.get('applied_agency_share_rate', 0)
        applied_insurance_amount = payment_data.get('applied_insurance_amount', 0)

        payment_data.update({
            'applied_tax_rate': applied_tax_rate,
            'applied_agency_share_rate': applied_agency_share_rate,
            'applied_insurance_amount': applied_insurance_amount,
            'final_net_earnings': net_earnings
        })

        return payment_data

    def _calculate_trip_fields(self, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate additional fields for trip records"""
        # Default calculations - can be overridden
        trip_duration = None
        if trip_data.get('order_time') and trip_data.get('trip_start_time'):
            try:
                from datetime import datetime
                order_time = pd.to_datetime(trip_data['order_time'])
                start_time = pd.to_datetime(trip_data['trip_start_time'])
                trip_duration = int((start_time - order_time).total_seconds() / 60)
            except:
                pass

        trip_data.update({
            'trip_duration_minutes': trip_duration
        })

        return trip_data
