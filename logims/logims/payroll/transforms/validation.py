"""
Payment validation transformer.
"""
from typing import Dict, Any
from logims.uploads.transforms.base import Transformer


class PaymentValidationTransformer(Transformer):
    """Validate payment data before saving"""

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate payment data.

        Args:
            data: Payment data dictionary

        Returns:
            Dict[str, Any]: Validated data

        Raises:
            ValueError: If validation fails
        """
        # Basic validation - ensure required fields exist
        if not data.get('driver_uuid'):
            raise ValueError("driver_uuid is required")

        # Additional validations can be added here

        return data
