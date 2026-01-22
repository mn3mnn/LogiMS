"""
Factory for creating payment parsing strategies.
"""
from typing import Type
from .base import PaymentParsingStrategy
from .companies.uber_eats import UberEatsPaymentStrategy


class PaymentStrategyFactory:
    """Factory class to create company-specific payment strategies"""

    _strategies = {
        'uber_eats': UberEatsPaymentStrategy,
        # Add more companies here as needed
    }

    @classmethod
    def get_strategy(cls, company_code: str, company) -> PaymentParsingStrategy:
        """
        Get the appropriate strategy for the company.

        Args:
            company_code: Company code (e.g., 'uber_eats')
            company: Company instance

        Returns:
            PaymentParsingStrategy: Company-specific strategy instance

        Raises:
            ValueError: If no strategy is found for the company
        """
        company_code_lower = company_code.lower()

        if company_code_lower not in cls._strategies:
            available_strategies = ', '.join(cls._strategies.keys())
            raise ValueError(
                f"No payment strategy found for company '{company_code}'. "
                f"Available strategies: {available_strategies}"
            )

        strategy_class = cls._strategies[company_code_lower]
        return strategy_class(company)

    @classmethod
    def register_strategy(cls, company_code: str, strategy_class: Type[PaymentParsingStrategy]):
        """
        Register a new strategy for a company.

        Args:
            company_code: Company code (e.g., 'uber_eats')
            strategy_class: Strategy class that extends PaymentParsingStrategy
        """
        cls._strategies[company_code.lower()] = strategy_class

    @classmethod
    def get_available_strategies(cls) -> list:
        """Get list of available strategy company codes"""
        return list(cls._strategies.keys())

    @classmethod
    def is_strategy_available(cls, company_code: str) -> bool:
        """Check if a strategy is available for a company"""
        return company_code.lower() in cls._strategies
