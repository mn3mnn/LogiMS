"""
Uber Eats trip parsing strategy.
"""
from typing import Dict, List, Any
import pandas as pd
from ..base import TripParsingStrategy


class UberEatsTripStrategy(TripParsingStrategy):
    """Uber Eats specific trip parsing strategy"""

    def get_field_mapping(self) -> Dict[str, str]:
        """Uber Eats specific field mapping"""
        return {
            'Fahrt-UUID': 'trip_uuid',
            'Fahrer-UUID': 'driver_uuid',
            'Vorname des Fahrers': 'driver_first_name',
            'Nachname des Fahrers': 'driver_last_name',
            'Fahrzeug-UUID': 'vehicle_uuid',
            'Kennzeichen': 'license_plate',
            'Serviceart': 'service_type',
            'Zeitpunkt der Fahrtbestellung': 'order_time',
            'Ankunftszeit der Fahrt': 'arrival_time',
            'Abholadresse': 'pickup_address',
            'Zieladresse': 'destination_address',
            'Fahrtdistanz': 'trip_distance',
            'Fahrtstatus': 'trip_status',
            'Zeitpunkt der Bestellübermittlung': 'order_submitted_time',
            'Startzeit der Fahrt': 'trip_start_time',
            'Fahrzeugstandort bei Bestellzuweisung': 'vehicle_location_at_assignment',
            'Fahrpreis (Änderungen aufgrund von Anpassungen nach der Fahrt vorbehalten)': 'fare_amount',
        }

    def parse_row(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Uber Eats trip row.
        """
        return {
            'trip_uuid': str(raw_data.get('Fahrt-UUID', '')),
            'driver_uuid': str(raw_data.get('Fahrer-UUID', '')),
            'driver_first_name': str(raw_data.get('Vorname des Fahrers', '')),
            'driver_last_name': str(raw_data.get('Nachname des Fahrers', '')),
            'vehicle_uuid': str(raw_data.get('Fahrzeug-UUID', '')) if pd.notna(raw_data.get('Fahrzeug-UUID')) else None,
            'license_plate': str(raw_data.get('Kennzeichen', '')) if pd.notna(raw_data.get('Kennzeichen')) else None,
            'service_type': str(raw_data.get('Serviceart', '')) if pd.notna(raw_data.get('Serviceart')) else None,
            'order_time': self._safe_datetime(raw_data.get('Zeitpunkt der Fahrtbestellung')),
            'arrival_time': self._safe_datetime(raw_data.get('Ankunftszeit der Fahrt')),
            'pickup_address': str(raw_data.get('Abholadresse', '')) if pd.notna(raw_data.get('Abholadresse')) else None,
            'destination_address': str(raw_data.get('Zieladresse', '')) if pd.notna(raw_data.get('Zieladresse')) else None,
            'trip_distance': self._safe_decimal(raw_data.get('Fahrtdistanz')),
            'trip_status': str(raw_data.get('Fahrtstatus', '')) if pd.notna(raw_data.get('Fahrtstatus')) else None,
            'order_submitted_time': self._safe_datetime(raw_data.get('Zeitpunkt der Bestellübermittlung')),
            'trip_start_time': self._safe_datetime(raw_data.get('Startzeit der Fahrt')),
            'vehicle_location_at_assignment': str(raw_data.get('Fahrzeugstandort bei Bestellzuweisung', '')) if pd.notna(raw_data.get('Fahrzeugstandort bei Bestellzuweisung')) else None,
            'fare_amount': self._safe_decimal(raw_data.get('Fahrpreis (Änderungen aufgrund von Anpassungen nach der Fahrt vorbehalten)')),
        }

    def validate_schema(self, columns: List[str]) -> bool:
        """Validate Uber Eats trip file schema"""
        required_columns = [
            'Fahrt-UUID',
            'Fahrer-UUID',
            'Vorname des Fahrers',
            'Nachname des Fahrers',
            'Zeitpunkt der Fahrtbestellung',
            'Fahrpreis (Änderungen aufgrund von Anpassungen nach der Fahrt vorbehalten)'
        ]
        missing_columns = [col for col in required_columns if col not in columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        return True

    def _safe_decimal(self, value) -> float:
        """Safely convert value to decimal, handling NaN and None"""
        if pd.isna(value) if hasattr(pd, 'isna') else (value is None):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_datetime(self, value) -> str:
        """Safely convert value to datetime string"""
        if pd.isna(value) if hasattr(pd, 'isna') else (value is None):
            return None
        try:
            # Try to parse as datetime
            dt = pd.to_datetime(value)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            return None
