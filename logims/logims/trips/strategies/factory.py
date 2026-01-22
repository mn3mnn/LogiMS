"""
Factory for creating trip parsing strategies.
"""
from typing import Type
from .base import TripParsingStrategy
from .companies.uber_eats import UberEatsTripStrategy


class TripStrategyFactory:
    """Factory class to create company-specific trip strategies"""

    _strategies = {
        'uber_eats': UberEatsTripStrategy,
        # Add more companies here as needed
    }

    @classmethod
    def get_strategy(cls, company_code: str, company) -> TripParsingStrategy:
        """Get the appropriate strategy for the company"""
        company_code_lower = company_code.lower()

        if company_code_lower not in cls._strategies:
            available_strategies = ', '.join(cls._strategies.keys())
            raise ValueError(
                f"No trip strategy found for company '{company_code}'. "
                f"Available strategies: {available_strategies}"
            )

        strategy_class = cls._strategies[company_code_lower]
        return strategy_class(company)

    @classmethod
    def register_strategy(cls, company_code: str, strategy_class: Type[TripParsingStrategy]):
        """Register a new strategy for a company"""
        cls._strategies[company_code.lower()] = strategy_class

    @classmethod
    def is_strategy_available(cls, company_code: str) -> bool:
        """Check if a strategy is available for a company"""
        return company_code.lower() in cls._strategies
