"""
Factory for creating appropriate adapters based on file extension.
"""
from .base import DataAdapter
from .csv_adapter import CSVAdapter
from .excel_adapter import ExcelAdapter


class AdapterFactory:
    """Factory to create file format adapters"""

    @staticmethod
    def get_adapter(file_field) -> DataAdapter:
        """
        Get appropriate adapter based on file extension.

        Args:
            file_field: Django FileField instance

        Returns:
            DataAdapter: Appropriate adapter instance

        Raises:
            ValueError: If file format is not supported
        """
        file_name = (file_field.name or "").lower()

        if file_name.endswith(".csv"):
            return CSVAdapter()
        elif file_name.endswith((".xls", ".xlsx")):
            return ExcelAdapter()
        else:
            raise ValueError(
                f"Unsupported file format. Only CSV and Excel (.xls, .xlsx) files are supported. "
                f"File: {file_field.name}"
            )
