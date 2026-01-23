"""
Base transformer interface for data transformation pipeline.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Transformer(ABC):
    """Abstract base class for data transformers"""

    def __init__(self):
        self._next_transformer: Optional['Transformer'] = None

    def set_next(self, transformer: 'Transformer') -> 'Transformer':
        """
        Set next transformer in chain.

        Args:
            transformer: Next transformer to execute

        Returns:
            Transformer: The transformer that was set (for chaining)
        """
        self._next_transformer = transformer
        return transformer

    @abstractmethod
    def transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform data.

        Args:
            data: Input data dictionary

        Returns:
            Dict[str, Any]: Transformed data dictionary
        """
        pass

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute transformation and pass to next transformer in chain.

        Args:
            data: Input data dictionary

        Returns:
            Dict[str, Any]: Final transformed data after all transformers
        """
        transformed = self.transform(data)
        if self._next_transformer:
            return self._next_transformer.execute(transformed)
        return transformed
