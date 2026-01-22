"""
Driver metadata transformer for trips.
Attaches driver and supervisor information to trip data.
"""
from typing import Dict, Any
from django.utils import timezone
from logims.uploads.transforms.base import Transformer


class DriverMetadataTransformer(Transformer):
    """
    Lookup driver and attach driver/supervisor metadata.
    Separated from duration calculation.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lookup driver and attach metadata.

        Args:
            data: Trip data dictionary with driver_uuid

        Returns:
            Dict with driver metadata added
        """
        driver_uuid = data.get('driver_uuid', '')
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

        # Update trip data with metadata
        data.update({
            # Calculation metadata
            'calculation_version': '1.0',
            'calculated_at': timezone.now(),
            'driver_id_at_calculation': driver.id if driver else None,
            'supervisor_id_at_calculation': supervisor_id,
            'supervisor_name_at_calculation': supervisor_name,
            # Set driver foreign key
            'driver': driver,
        })

        return data
