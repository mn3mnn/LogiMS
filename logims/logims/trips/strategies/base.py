"""
Base trip parsing strategy.
"""
from typing import Dict, List, Any
from logims.uploads.strategies.base import ParsingStrategy


class TripParsingStrategy(ParsingStrategy):
    """Base class for trip-specific parsing strategies"""

    def __init__(self, company):
        """
        Initialize trip strategy.

        Args:
            company: Company instance
        """
        self.company = company
