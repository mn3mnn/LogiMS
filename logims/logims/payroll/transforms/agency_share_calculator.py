"""
Agency share calculation transformer.
Calculates agency share deduction based on supervisor percentage.
"""
from typing import Dict, Any
from logims.uploads.transforms.base import Transformer


class AgencyShareCalculatorTransformer(Transformer):
    """
    Calculate agency share deduction.
    Separated from other deduction calculations.
    """

    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate agency share deduction for payment data.

        Args:
            data: Payment data dictionary with total_income and driver info

        Returns:
            Dict with agency_share_deduction and applied_agency_share_rate added
        """
        # Get total income (total_revenue - tips)
        total_revenue = data.get('total_revenue', 0) or 0
        tips = data.get('tips', 0) or 0
        total_income = float(total_revenue) - float(tips)

        # Get agency share rate from driver data (already looked up)
        agency_share_rate = data.get('agency_share_rate', 0) or 0

        # Calculate agency share deduction (percentage of total_income)
        agency_share_deduction = (total_income * agency_share_rate / 100) if agency_share_rate else 0

        # Update data
        data.update({
            'agency_share_deduction': agency_share_deduction,
            'applied_agency_share_rate': round(agency_share_rate, 2),
        })

        return data
