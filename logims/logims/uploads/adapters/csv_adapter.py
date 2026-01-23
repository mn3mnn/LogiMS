"""
CSV file adapter.
"""
import pandas as pd
from typing import Iterator, Dict, Any
from .base import DataAdapter


class CSVAdapter(DataAdapter):
    """Adapter for reading CSV files"""

    def read(self, file) -> Iterator[Dict[str, Any]]:
        """Read CSV file and yield rows as dictionaries"""
        df = pd.read_csv(file)
        # Remove completely empty rows
        df = df.dropna(how='all')
        for _, row in df.iterrows():
            yield row.to_dict()
