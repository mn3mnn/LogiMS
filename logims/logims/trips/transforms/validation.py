"""Trip validation transformer"""
from typing import Dict, Any
from logims.uploads.transforms.base import Transformer


class TripValidationTransformer(Transformer):
    """Validate trip data before saving"""

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate trip data"""
        if not data.get('trip_uuid'):
            raise ValueError("trip_uuid is required")
        return data
