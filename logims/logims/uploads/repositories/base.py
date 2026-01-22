"""
Base repository interface for data persistence.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BaseRepository(ABC):
    """Abstract base class for repositories"""

    @abstractmethod
    def bulk_create(self, records: List[Dict[str, Any]]) -> int:
        """
        Bulk create records.

        Args:
            records: List of record dictionaries

        Returns:
            int: Number of records created
        """
        pass
