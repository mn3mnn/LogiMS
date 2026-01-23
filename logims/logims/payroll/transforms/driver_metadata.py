"""
Driver metadata transformer for payments.
Attaches driver and supervisor information to payment data.
"""
from typing import Dict, Any
from django.utils import timezone
from logims.uploads.transforms.base import Transformer


class DriverMetadataTransformer(Transformer):
    """
    Lookup driver and attach driver/supervisor metadata.
    Separated from deduction calculations.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lookup driver and attach metadata including agency share and insurance.

        Args:
            data: Payment data dictionary with driver_uuid

        Returns:
            Dict with driver metadata added
        """
        driver_uuid = data.get('driver_uuid', '')
        driver = None
        supervisor_id = None
        supervisor_name = None
        agency_share_rate = 0
        insurance_amount = 0

        # Try to get driver's agency share (from supervisor) and insurance
        try:
            from logims.drivers.models import Driver
            driver = Driver.objects.select_related('supervisor').filter(uuid=driver_uuid).first()
            if driver:
                # Get agency_share from supervisor's percentage
                if driver.supervisor:
                    supervisor_id = driver.supervisor.id
                    supervisor_name = driver.supervisor.name
                    if driver.supervisor.percentage is not None:
                        agency_share_rate = float(driver.supervisor.percentage)
                else:
                    agency_share_rate = 0
                insurance_amount = float(driver.insurance or 0)
        except Exception:
            # If driver not found or error, use default values
            pass

        # Update data with metadata
        data.update({
            # Driver information for deduction calculations
            'agency_share_rate': agency_share_rate,
            'insurance_amount': insurance_amount,
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
