from typing import Dict, List, Any, Tuple
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
        """Process Uber Eats payment data using bulk operations with chunking for better performance.
        The entire file processing is wrapped in a single transaction for atomicity.
        """
        import math

        CHUNK_SIZE = 5000
        total_records = len(df)
        total_processed = 0
        total_created = 0
        total_updated = 0

        # Process in chunks to manage memory and allow progress updates
        num_chunks = math.ceil(total_records / CHUNK_SIZE)

        # Wrap entire file processing in a single transaction
        with transaction.atomic():
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * CHUNK_SIZE
                end_idx = min(start_idx + CHUNK_SIZE, total_records)
                chunk_df = df.iloc[start_idx:end_idx]

                # Prepare payment data for this chunk
                payment_records = []
                driver_uuids = []

                for _, row in chunk_df.iterrows():
                    payment_data = self._map_payment_data(row)
                    payment_data = self._calculate_payment_fields(payment_data)
                    driver_uuid = payment_data.pop('driver_uuid')
                    driver = payment_data.pop('driver', None)  # Extract driver FK

                    payment_records.append({
                        'driver_uuid': driver_uuid,
                        'driver': driver,  # Include driver FK
                        'payment_data': payment_data
                    })
                    driver_uuids.append(driver_uuid)

                if not payment_records:
                    continue

                records_created = 0
                records_updated = 0

                # Fetch existing records for this chunk matching uniqueness criteria
                existing_records = {}
                for record in PaymentRecord.objects.filter(
                    file_upload__company=self.company,
                    file_upload__from_date=self.file_upload.from_date,
                    file_upload__to_date=self.file_upload.to_date,
                    driver_uuid__in=driver_uuids
                ).select_related('file_upload'):
                    existing_records[record.driver_uuid] = record

                # Separate new and existing records
                new_records = []
                update_records = []

                for record_info in payment_records:
                    driver_uuid = record_info['driver_uuid']
                    driver = record_info.get('driver')  # Get driver FK
                    payment_data = record_info['payment_data']

                    if driver_uuid in existing_records:
                        # Update existing record
                        existing = existing_records[driver_uuid]
                        for field, value in payment_data.items():
                            setattr(existing, field, value)
                        existing.file_upload = self.file_upload
                        existing.driver = driver  # Update driver FK
                        update_records.append(existing)
                    else:
                        # Create new record
                        payment_data['file_upload'] = self.file_upload
                        payment_data['driver_uuid'] = driver_uuid
                        payment_data['driver'] = driver  # Set driver FK
                        new_records.append(PaymentRecord(**payment_data))

                # Bulk create new records
                if new_records:
                    PaymentRecord.objects.bulk_create(new_records, ignore_conflicts=False, batch_size=500)
                    records_created = len(new_records)

                # Bulk update existing records
                if update_records:
                    PaymentRecord.objects.bulk_update(
                        update_records,
                        fields=[f.name for f in PaymentRecord._meta.get_fields()
                               if not f.primary_key and f.name != 'id' and f.name != 'created_at'],
                        batch_size=500
                    )
                    records_updated = len(update_records)

                total_created += records_created
                total_updated += records_updated
                total_processed += len(payment_records)

                # Update progress periodically (every chunk) - within the transaction
                self.file_upload.processed_records_count = total_processed
                self.file_upload.save(update_fields=['processed_records_count'])

        return total_created + total_updated

    def _process_trips(self, df: pd.DataFrame) -> int:
        """Process Uber Eats trip data using bulk operations with chunking for better performance.
        The entire file processing is wrapped in a single transaction for atomicity.
        """
        import math

        CHUNK_SIZE = 5000
        total_records = len(df)
        total_processed = 0
        total_created = 0
        total_updated = 0

        # Process in chunks to manage memory and allow progress updates
        num_chunks = math.ceil(total_records / CHUNK_SIZE)

        # Wrap entire file processing in a single transaction
        with transaction.atomic():
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * CHUNK_SIZE
                end_idx = min(start_idx + CHUNK_SIZE, total_records)
                chunk_df = df.iloc[start_idx:end_idx]

                # Prepare trip data for this chunk
                trip_records = []
                trip_uuids = []

                for _, row in chunk_df.iterrows():
                    trip_data = self._map_trip_data(row)
                    trip_data = self._calculate_trip_fields(trip_data)
                    trip_uuid = trip_data.pop('trip_uuid')
                    driver = trip_data.pop('driver', None)  # Extract driver FK

                    trip_records.append({
                        'trip_uuid': trip_uuid,
                        'driver': driver,  # Include driver FK
                        'trip_data': trip_data
                    })
                    trip_uuids.append(trip_uuid)

                if not trip_records:
                    continue

                records_created = 0
                records_updated = 0

                # Fetch existing records for this chunk
                existing_records = {
                    record.trip_uuid: record
                    for record in TripRecord.objects.filter(trip_uuid__in=trip_uuids)
                }

                # Separate new and existing records
                new_records = []
                update_records = []

                for record_info in trip_records:
                    trip_uuid = record_info['trip_uuid']
                    driver = record_info.get('driver')  # Get driver FK
                    trip_data = record_info['trip_data']

                    if trip_uuid in existing_records:
                        # Update existing record
                        existing = existing_records[trip_uuid]
                        for field, value in trip_data.items():
                            setattr(existing, field, value)
                        existing.file_upload = self.file_upload
                        existing.driver = driver  # Update driver FK
                        update_records.append(existing)
                    else:
                        # Create new record
                        trip_data['file_upload'] = self.file_upload
                        trip_data['trip_uuid'] = trip_uuid
                        trip_data['driver'] = driver  # Set driver FK
                        new_records.append(TripRecord(**trip_data))

                # Bulk create new records
                if new_records:
                    TripRecord.objects.bulk_create(new_records, ignore_conflicts=False, batch_size=500)
                    records_created = len(new_records)

                # Bulk update existing records
                if update_records:
                    TripRecord.objects.bulk_update(
                        update_records,
                        fields=[f.name for f in TripRecord._meta.get_fields()
                               if not f.primary_key and f.name != 'id' and f.name != 'created_at'],
                        batch_size=500
                    )
                    records_updated = len(update_records)

                total_created += records_created
                total_updated += records_updated
                total_processed += len(trip_records)

                # Update progress periodically (every chunk) - within the transaction
                self.file_upload.processed_records_count = total_processed
                self.file_upload.save(update_fields=['processed_records_count'])

        return total_created + total_updated

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
        from django.utils import timezone

        # Get total revenue and tips
        total_revenue = payment_data.get('total_revenue', 0) or 0
        if total_revenue:
            total_revenue = float(total_revenue)

        tips = payment_data.get('tips', 0) or 0
        if tips:
            tips = float(tips)

        # Calculate total income (total_revenue + tips) - this is the base for deductions
        total_income = total_revenue + tips

        # Get driver information for agency share and insurance
        driver_uuid = payment_data.get('driver_uuid', '')
        driver_agency_share = 0
        driver_insurance = 0
        driver = None
        supervisor_id = None
        supervisor_name = None

        # Try to get driver's agency share (from supervisor) and insurance from the driver model
        try:
            from logims.drivers.models import Driver
            driver = Driver.objects.select_related('supervisor').filter(uuid=driver_uuid).first()
            if driver:
                # Get agency_share from supervisor's percentage
                if driver.supervisor:
                    supervisor_id = driver.supervisor.id
                    supervisor_name = driver.supervisor.name
                    if driver.supervisor.percentage is not None:
                        driver_agency_share = float(driver.supervisor.percentage)
                else:
                    driver_agency_share = 0
                driver_insurance = float(driver.insurance or 0)
        except Exception:
            # If driver not found or error, use default values
            pass

        # Calculate tax deduction and get tax rate (based on total_income = total_revenue + tips)
        tax_deduction, total_tax_rate = self._calculate_tax_deduction(total_income)

        # Calculate agency share deduction (percentage of total_income = total_revenue + tips)
        agency_share_deduction = (total_income * driver_agency_share / 100) if driver_agency_share else 0

        # Insurance deduction (fixed amount)
        insurance_deduction = driver_insurance

        # Calculate total deductions
        total_deductions = tax_deduction + agency_share_deduction + insurance_deduction

        # Calculate final net earnings: total_income - total_deductions
        final_net_earnings = total_income - total_deductions

        payment_data.update({
            'total_deductions': total_deductions,
            'tax_deduction': tax_deduction,
            'agency_share_deduction': agency_share_deduction,
            'insurance_deduction': insurance_deduction,
            'final_net_earnings': final_net_earnings,
            # Calculation metadata
            'calculation_version': '1.0',
            'calculated_at': timezone.now(),
            'applied_tax_rate': round(total_tax_rate, 2),
            'applied_agency_share_rate': round(driver_agency_share, 2),
            'applied_insurance_amount': round(driver_insurance, 2),
            'driver_id_at_calculation': driver.id if driver else None,
            'supervisor_id_at_calculation': supervisor_id,
            'supervisor_name_at_calculation': supervisor_name,
            # Set driver foreign key
            'driver': driver,
        })

        return payment_data

    def _calculate_tax_deduction(self, total_income: float) -> Tuple[float, float]:
        """Calculate tax deduction based on company tax configuration
        Returns: (total_tax_amount, total_tax_rate_percentage)
        """
        try:
            # Get active tax configurations for this company
            tax_configs = TaxConfiguration.objects.filter(
                company=self.company,
                is_active=True
            )

            total_tax = 0
            total_tax_rate = 0
            for tax_config in tax_configs:
                tax_rate = float(tax_config.tax_rate)
                tax_amount = (total_income * tax_rate / 100)
                total_tax += tax_amount
                total_tax_rate += tax_rate

            return total_tax, total_tax_rate
        except Exception:
            # If no tax configuration found, return 0
            return 0.0, 0.0

    def _calculate_trip_fields(self, trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Uber Eats specific trip calculations"""
        from django.utils import timezone

        # Get driver information
        driver_uuid = trip_data.get('driver_uuid', '')
        driver = None
        supervisor_id = None
        supervisor_name = None

        # Try to get driver for FK and snapshot
        try:
            from logims.drivers.models import Driver
            driver = Driver.objects.select_related('supervisor').filter(uuid=driver_uuid).first()
            if driver and driver.supervisor:
                supervisor_id = driver.supervisor.id
                supervisor_name = driver.supervisor.name
        except Exception:
            # If driver not found or error, continue without driver
            pass

        # Calculate trip duration
        trip_duration = None
        if trip_data.get('order_time') and trip_data.get('trip_start_time'):
            try:
                from datetime import datetime
                order_time = pd.to_datetime(trip_data['order_time'])
                start_time = pd.to_datetime(trip_data['trip_start_time'])
                duration_seconds = (start_time - order_time).total_seconds()
                trip_duration = int(duration_seconds / 60)

                # Validate duration is reasonable (non-negative and not more than 24 hours)
                if trip_duration < 0:
                    trip_duration = None
                elif trip_duration > 1440:  # More than 24 hours
                    # Still store it but it's unusual
                    pass
            except Exception:
                trip_duration = None

        # Update trip data with calculations and metadata
        trip_data.update({
            'trip_duration_minutes': trip_duration,
            # Calculation metadata
            'calculation_version': '1.0',
            'calculated_at': timezone.now(),
            'driver_id_at_calculation': driver.id if driver else None,
            'supervisor_id_at_calculation': supervisor_id,
            'supervisor_name_at_calculation': supervisor_name,
            # Set driver foreign key
            'driver': driver,
        })

        return trip_data
