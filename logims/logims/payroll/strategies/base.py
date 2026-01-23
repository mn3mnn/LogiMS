"""
Base payment parsing strategy.
"""
from typing import Dict, List, Any
from logims.uploads.strategies.base import ParsingStrategy


class PaymentParsingStrategy(ParsingStrategy):
    """Base class for payment-specific parsing strategies"""

    def __init__(self, company):
        """
        Initialize payment strategy.

        Args:
            company: Company instance
        """
        self.company = company
