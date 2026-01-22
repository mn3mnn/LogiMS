"""
Tax calculation transformer.
Calculates tax deductions based on company tax configuration.
"""
from typing import Dict, Tuple, Any
from logims.uploads.transforms.base import Transformer
from ..models import TaxConfiguration


class TaxCalculationTransformer(Transformer):
    """
    Calculate tax deduction based on company tax configuration.
    Separated from other deduction calculations.
    """

    def __init__(self, company):
        """
        Initialize tax calculation transformer.

        Args:
            company: Company instance for tax configuration lookup
        """
        super().__init__()
        self.company = company

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate tax deduction for payment data.

        Args:
            data: Payment data dictionary with total_income

        Returns:
            Dict with tax_deduction and applied_tax_rate added
        """
        # Get total income (total_revenue - tips)
        total_revenue = data.get('total_revenue', 0) or 0
        tips = data.get('tips', 0) or 0
        total_income = float(total_revenue) - float(tips)

        # Calculate tax deduction
        tax_deduction, total_tax_rate = self._calculate_tax_deduction(total_income)

        # Update data with tax information
        data.update({
            'tax_deduction': tax_deduction,
            'applied_tax_rate': round(total_tax_rate, 2),
        })

        return data

    def _calculate_tax_deduction(self, total_income: float) -> Tuple[float, float]:
        """
        Calculate tax deduction based on company tax configuration.
        Returns: (total_tax_amount, total_tax_rate_percentage)

        Args:
            total_income: Total income amount (total_revenue - tips)

        Returns:
            Tuple of (tax_amount, tax_rate_percentage)
        """
        try:
            # Get active tax configurations for this company
            tax_configs = TaxConfiguration.objects.filter(
                company=self.company,
                is_active=True
            )

            total_tax = 0
            total_tax_rate = 0
            for tax_config in tax_configs:
                tax_rate = float(tax_config.tax_rate)
                tax_amount = (total_income * tax_rate / 100)
                total_tax += tax_amount
                total_tax_rate += tax_rate

            return total_tax, total_tax_rate
        except Exception:
            # If no tax configuration found, return 0
            return 0.0, 0.0
