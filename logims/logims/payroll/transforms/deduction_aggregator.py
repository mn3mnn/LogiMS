"""
Deduction aggregator transformer.
Aggregates all deductions and calculates final net earnings.
"""
from typing import Dict, Any
from logims.uploads.transforms.base import Transformer


class DeductionAggregatorTransformer(Transformer):
    """
    Aggregate all deductions and calculate final net earnings.
    Should be used after all individual deduction transformers.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregate deductions and calculate final net earnings.

        Args:
            data: Payment data dictionary with all deductions calculated

        Returns:
            Dict with total_deductions and final_net_earnings added
        """
        # Get total income (total_revenue - tips)
        total_revenue = data.get('total_revenue', 0) or 0
        tips = data.get('tips', 0) or 0
        total_income = float(total_revenue) - float(tips)

        # Get all deductions
        tax_deduction = data.get('tax_deduction', 0) or 0
        agency_share_deduction = data.get('agency_share_deduction', 0) or 0
        insurance_deduction = data.get('insurance_deduction', 0) or 0

        # Calculate total deductions
        total_deductions = tax_deduction + agency_share_deduction + insurance_deduction

        # Calculate final net earnings: total_income - total_deductions
        final_net_earnings = total_income - total_deductions

        # Update data
        data.update({
            'total_deductions': total_deductions,
            'final_net_earnings': final_net_earnings,
        })

        return data
