"""
Excel file adapter.
"""
import pandas as pd
from typing import Iterator, Dict, Any
from .base import DataAdapter


class ExcelAdapter(DataAdapter):
    """Adapter for reading Excel files"""

    def read(self, file) -> Iterator[Dict[str, Any]]:
        """Read Excel file and yield rows as dictionaries"""
        df = pd.read_excel(file)
        # Remove completely empty rows
        df = df.dropna(how='all')
        for _, row in df.iterrows():
            yield row.to_dict()
