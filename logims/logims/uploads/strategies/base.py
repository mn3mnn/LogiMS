"""
Base parsing strategy interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any


class ParsingStrategy(ABC):
    """Abstract base class for company-specific parsing strategies"""

    @abstractmethod
    def get_field_mapping(self) -> Dict[str, str]:
        """
        Map source columns to target fields.

        Returns:
            Dict[str, str]: Mapping of source column names to target field names
        """
        pass

    @abstractmethod
    def parse_row(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and transform a single row.

        Args:
            raw_data: Raw row data from file

        Returns:
            Dict[str, Any]: Parsed and mapped data
        """
        pass

    @abstractmethod
    def validate_schema(self, columns: List[str]) -> bool:
        """
        Validate file has required columns.

        Args:
            columns: List of column names in the file

        Returns:
            bool: True if schema is valid

        Raises:
            ValueError: If required columns are missing
        """
        pass
