"""
Uber Eats payment parsing strategy.
"""
from typing import Dict, List, Any
import pandas as pd
from decimal import Decimal
from ..base import PaymentParsingStrategy


class UberEatsPaymentStrategy(PaymentParsingStrategy):
    """Uber Eats specific payment parsing strategy"""

    def get_field_mapping(self) -> Dict[str, str]:
        """Uber Eats specific field mapping"""
        return {
            'Fahrer-UUID': 'driver_uuid',
            'Vorname des Fahrers': 'driver_first_name',
            'Nachname des Fahrers': 'driver_last_name',
            'Gesamtumsätze': 'total_revenue',
            'Gesamtumsätze : Netto-Fahrpreis': 'net_fare',
            'Gesamtumsätze : Aktionen': 'promotions',
            'Rückerstattungen und Fahrtauslagen': 'refunds_and_fees',
            'Auszahlungen': 'payouts',
            'Auszahlungen : Auf Bankkonto überwiesen': 'bank_transfer',
            'Auszahlungen : Eingenommenes Bargeld': 'cash_collected',
            'Rückerstattungen und Fahrtauslagen:Steuern:Steuer auf Fahrpreis': 'fare_tax',
            'Gesamtumsätze:Trinkgeld': 'tips',
            'Gesamtumsätze:Steuern': 'taxes',
            'Gesamtumsätze:Sonstige Umsätze:Anpassung': 'other_revenue',
        }

    def parse_row(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Uber Eats payment row.
        """
        return {
            'driver_uuid': str(raw_data.get('Fahrer-UUID', '')),
            'driver_first_name': str(raw_data.get('Vorname des Fahrers', '')),
            'driver_last_name': str(raw_data.get('Nachname des Fahrers', '')),
            'total_revenue': self._safe_decimal(raw_data.get('Gesamtumsätze')),
            'net_fare': self._safe_decimal(raw_data.get('Gesamtumsätze : Netto-Fahrpreis')),
            'promotions': self._safe_decimal(raw_data.get('Gesamtumsätze : Aktionen')),
            'refunds_and_fees': self._safe_decimal(raw_data.get('Rückerstattungen und Fahrtauslagen')),
            'payouts': self._safe_decimal(raw_data.get('Auszahlungen')),
            'bank_transfer': self._safe_decimal(raw_data.get('Auszahlungen : Auf Bankkonto überwiesen')),
            'cash_collected': self._safe_decimal(raw_data.get('Auszahlungen : Eingenommenes Bargeld')),
            'fare_tax': self._safe_decimal(raw_data.get('Rückerstattungen und Fahrtauslagen:Steuern:Steuer auf Fahrpreis')),
            'tips': self._safe_decimal(raw_data.get('Gesamtumsätze:Trinkgeld')),
            'taxes': self._safe_decimal(raw_data.get('Gesamtumsätze:Steuern')),
            'other_revenue': self._safe_decimal(raw_data.get('Gesamtumsätze:Sonstige Umsätze:Anpassung')),
        }

    def validate_schema(self, columns: List[str]) -> bool:
        """Validate Uber Eats payment file schema"""
        required_columns = [
            'Fahrer-UUID',
            'Vorname des Fahrers',
            'Nachname des Fahrers',
            'Gesamtumsätze',
            'Auszahlungen'
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
