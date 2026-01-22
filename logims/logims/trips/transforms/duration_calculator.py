"""
Trip duration calculation transformer.
Calculates trip duration from order_time and trip_start_time.
"""
from typing import Dict, Any
import pandas as pd
from logims.uploads.transforms.base import Transformer

# Constants
MINUTES_PER_DAY = 1440  # 24 hours in minutes


class DurationCalculatorTransformer(Transformer):
    """
    Calculate trip duration in minutes.
    Separated from driver lookup and metadata attachment.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate trip duration from order_time and trip_start_time.

        Args:
            data: Trip data dictionary with order_time and trip_start_time

        Returns:
            Dict with trip_duration_minutes added
        """
        trip_duration = None

        if data.get('order_time') and data.get('trip_start_time'):
            try:
                order_time = pd.to_datetime(data['order_time'])
                start_time = pd.to_datetime(data['trip_start_time'])
                duration_seconds = (start_time - order_time).total_seconds()
                trip_duration = int(duration_seconds / 60)

                # Validate duration is reasonable (non-negative and not more than 24 hours)
                if trip_duration < 0:
                    trip_duration = None
                elif trip_duration > MINUTES_PER_DAY:
                    # Still store it but it's unusual
                    pass
            except Exception:
                trip_duration = None

        data['trip_duration_minutes'] = trip_duration
        return data
