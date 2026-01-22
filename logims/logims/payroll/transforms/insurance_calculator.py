"""
Insurance calculation transformer.
Calculates insurance deduction (fixed amount).
"""
from typing import Dict, Any
from logims.uploads.transforms.base import Transformer


class InsuranceCalculatorTransformer(Transformer):
    """
    Calculate insurance deduction.
    Separated from other deduction calculations.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate insurance deduction for payment data.

        Args:
            data: Payment data dictionary with driver insurance amount

        Returns:
            Dict with insurance_deduction and applied_insurance_amount added
        """
        # Get insurance amount from driver data (already looked up)
        insurance_amount = data.get('insurance_amount', 0) or 0

        # Insurance deduction is a fixed amount
        insurance_deduction = float(insurance_amount)

        # Update data
        data.update({
            'insurance_deduction': insurance_deduction,
            'applied_insurance_amount': round(insurance_amount, 2),
        })

        return data
