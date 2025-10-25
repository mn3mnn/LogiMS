from typing import Dict, List, Any
import pandas as pd
from django.db import transaction
from decimal import Decimal
from .base import BaseExcelProcessor
from ..models import PaymentRecord, TripRecord, TaxConfiguration


class UberEatsProcessor(BaseExcelProcessor):
    """Uber Eats specific Excel file processor"""

    def _get_required_columns(self) -> List[str]:
        """Uber Eats specific required columns"""
        if self.file_upload.file_type == 'payments':
            return [
                'Fahrer-UUID',
                'Vorname des Fahrers',
                'Nachname des Fahrers',
                'Gesamtumsätze',
                'Auszahlungen'
            ]
        elif self.file_upload.file_type == 'trips':
            return [
                'Fahrt-UUID',
                'Fahrer-UUID',
                'Vorname des Fahrers',
                'Nachname des Fahrers',
                'Zeitpunkt der Fahrtbestellung',
                'Fahrpreis (Änderungen aufgrund von Anpassungen nach der Fahrt vorbehalten)'
            ]
        return []

    def _process_payments(self, df: pd.DataFrame) -> int:
        """Process Uber Eats payment data"""
        records_created = 0
        records_updated = 0

        with transaction.atomic():
            for _, row in df.iterrows():
                payment_data = self._map_payment_data(row)
                payment_data = self._calculate_payment_fields(payment_data)

                # Extract driver_uuid for upsert
                driver_uuid = payment_data.pop('driver_uuid')

                # Use upsert to handle duplicates
                record, is_created = PaymentRecord.upsert_payment_record(
                    file_upload=self.file_upload,
                    driver_uuid=driver_uuid,
                    payment_data=payment_data
                )

                if is_created:
                    records_created += 1
                else:
                    records_updated += 1

        return records_created + records_updated

    def _process_trips(self, df: pd.DataFrame) -> int:
        """Process Uber Eats trip data"""
        records_created = 0

        with transaction.atomic():
            # Clear existing records for this file upload
            TripRecord.objects.filter(file_upload=self.file_upload).delete()

            for _, row in df.iterrows():
                trip_data = self._map_trip_data(row)
                trip_data = self._calculate_trip_fields(trip_data)

                TripRecord.objects.create(
                    file_upload=self.file_upload,
                    **trip_data
                )
                records_created += 1

        return records_created

    def _map_payment_data(self, row: pd.Series) -> Dict[str, Any]:
        """Map Uber Eats payment Excel row to PaymentRecord fields"""
        return {
            'driver_uuid': str(row.get('Fahrer-UUID', '')),
            'driver_first_name': str(row.get('Vorname des Fahrers', '')),
            'driver_last_name': str(row.get('Nachname des Fahrers', '')),
            'total_revenue': self._safe_decimal(row.get('Gesamtumsätze')),
            'net_fare': self._safe_decimal(row.get('Gesamtumsätze : Netto-Fahrpreis')),
            'promotions': self._safe_decimal(row.get('Gesamtumsätze : Aktionen')),
            'refunds_and_fees': self._safe_decimal(row.get('Rückerstattungen und Fahrtauslagen')),
            'payouts': self._safe_decimal(row.get('Auszahlungen')),
            'bank_transfer': self._safe_decimal(row.get('Auszahlungen : Auf Bankkonto überwiesen')),
            'cash_collected': self._safe_decimal(row.get('Auszahlungen : Eingenommenes Bargeld')),
            'fare_tax': self._safe_decimal(row.get('Rückerstattungen und Fahrtauslagen:Steuern:Steuer auf Fahrpreis')),
            'tips': self._safe_decimal(row.get('Gesamtumsätze:Trinkgeld')),
            'taxes': self._safe_decimal(row.get('Gesamtumsätze:Steuern')),
            'other_revenue': self._safe_decimal(row.get('Gesamtumsätze:Sonstige Umsätze:Anpassung')),
        }

    def _map_trip_data(self, row: pd.Series) -> Dict[str, Any]:
        """Map Uber Eats trip Excel row to TripRecord fields"""
        return {
            'trip_uuid': str(row.get('Fahrt-UUID', '')),
            'driver_uuid': str(row.get('Fahrer-UUID', '')),
            'driver_first_name': str(row.get('Vorname des Fahrers', '')),
            'driver_last_name': str(row.get('Nachname des Fahrers', '')),
            'vehicle_uuid': str(row.get('Fahrzeug-UUID', '')) if pd.notna(row.get('Fahrzeug-UUID')) else None,
            'license_plate': str(row.get('Kennzeichen', '')) if pd.notna(row.get('Kennzeichen')) else None,
            'service_type': str(row.get('Serviceart', '')) if pd.notna(row.get('Serviceart')) else None,
            'order_time': self._safe_datetime(row.get('Zeitpunkt der Fahrtbestellung')),
            'arrival_time': self._safe_datetime(row.get('Ankunftszeit der Fahrt')),
            'pickup_address': str(row.get('Abholadresse', '')) if pd.notna(row.get('Abholadresse')) else None,
            'destination_address': str(row.get('Zieladresse', '')) if pd.notna(row.get('Zieladresse')) else None,
            'trip_distance': self._safe_decimal(row.get('Fahrtdistanz')),
            'trip_status': str(row.get('Fahrtstatus', '')) if pd.notna(row.get('Fahrtstatus')) else None,
            'order_submitted_time': self._safe_datetime(row.get('Zeitpunkt der Bestellübermittlung')),
            'trip_start_time': self._safe_datetime(row.get('Startzeit der Fahrt')),
            'vehicle_location_at_assignment': str(row.get('Fahrzeugstandort bei Bestellzuweisung', '')) if pd.notna(row.get('Fahrzeugstandort bei Bestellzuweisung')) else None,
            'fare_amount': self._safe_decimal(row.get('Fahrpreis (Änderungen aufgrund von Anpassungen nach der Fahrt vorbehalten)')),
        }

    def _safe_decimal(self, value) -> float:
        """Safely convert value to decimal, handling NaN and None"""
        if pd.isna(value) or value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_datetime(self, value) -> str:
        """Safely convert value to datetime string"""
        if pd.isna(value) or value is None:
            return None
        try:
            # Try to parse as datetime
            dt = pd.to_datetime(value)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            return None

    def _calculate_payment_fields(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Uber Eats specific payment calculations with deductions"""
        # Get total income (اجمالي الدخل) - this should be the total_revenue field
        total_income = payment_data.get('total_revenue', 0) or 0
        if total_income:
            total_income = float(total_income)

        # Get driver information for agency share and insurance
        driver_uuid = payment_data.get('driver_uuid', '')
        driver_agency_share = 0
        driver_insurance = 0

        # Try to get driver's agency share and insurance from the driver model
        try:
            from logims.drivers.models import Driver
            driver = Driver.objects.filter(uuid=driver_uuid).first()
            if driver:
                driver_agency_share = float(driver.agency_share or 0)
                driver_insurance = float(driver.insurance or 0)
        except Exception:
            # If driver not found or error, use default values
            pass

        # Calculate tax deduction
        tax_deduction = self._calculate_tax_deduction(total_income)

        # Calculate agency share deduction (percentage of total income)
        agency_share_deduction = (total_income * driver_agency_share / 100) if driver_agency_share else 0

        # Insurance deduction (fixed amount)
        insurance_deduction = driver_insurance

        # Calculate total deductions
        total_deductions = tax_deduction + agency_share_deduction + insurance_deduction

        # Calculate final net earnings (total income - all deductions)
        final_net_earnings = total_income - total_deductions

        payment_data.update({
            'total_deductions': total_deductions,
            'tax_deduction': tax_deduction,
            'agency_share_deduction': agency_share_deduction,
            'insurance_deduction': insurance_deduction,
            'final_net_earnings': final_net_earnings
        })

        return payment_data

    def _calculate_tax_deduction(self, total_income: float) -> float:
        """Calculate tax deduction based on company tax configuration"""
        try:
            # Get active tax configurations for this company
            tax_configs = TaxConfiguration.objects.filter(
                company=self.company,
                is_active=True
            )

            total_tax = 0
            for tax_config in tax_configs:
                tax_amount = (total_income * float(tax_config.tax_rate) / 100)
                total_tax += tax_amount

            return total_tax
        except Exception:
            # If no tax configuration found, return 0
            return 0

    def _calculate_trip_fields(self, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Uber Eats specific trip calculations"""
        # Calculate trip duration
        trip_duration = None
        if trip_data.get('order_time') and trip_data.get('trip_start_time'):
            try:
                from datetime import datetime
                order_time = pd.to_datetime(trip_data['order_time'])
                start_time = pd.to_datetime(trip_data['trip_start_time'])
                trip_duration = int((start_time - order_time).total_seconds() / 60)
            except:
                pass

        # Calculate earnings (fare amount)
        trip_data.update({
            'trip_duration_minutes': trip_duration
        })

        return trip_data
