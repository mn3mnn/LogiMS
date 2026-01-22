"""
Base adapter interface for reading different file formats.
"""
from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any


class DataAdapter(ABC):
    """Abstract base class for file format adapters"""

    @abstractmethod
    def read(self, file) -> Iterator[Dict[str, Any]]:
        """
        Read file and yield rows as dictionaries.

        Args:
            file: File object or path

        Yields:
            Dict[str, Any]: Each row as a dictionary
        """
        pass
