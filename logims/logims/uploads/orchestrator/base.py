"""
Base processing orchestrator using Template Method pattern.
"""
from typing import List, Tuple, Dict, Any
from ..adapters.base import DataAdapter
from ..strategies.base import ParsingStrategy
from ..transforms.base import Transformer


class ProcessingOrchestrator:
    """
    Orchestrates the file processing flow:
    Extract -> Validate -> Transform -> Load
    """

    def __init__(self, file_upload, strategy: ParsingStrategy, adapter: DataAdapter):
        """
        Initialize orchestrator.

        Args:
            file_upload: FileUpload instance
            strategy: Parsing strategy for company-specific format
            adapter: Data adapter for file format
        """
        self.file_upload = file_upload
        self.strategy = strategy
        self.adapter = adapter
        self.transformers: List[Transformer] = []

    def add_transformer(self, transformer: Transformer) -> 'ProcessingOrchestrator':
        """
        Add transformer to pipeline.

        Args:
            transformer: Transformer to add

        Returns:
            ProcessingOrchestrator: Self for chaining
        """
        self.transformers.append(transformer)
        return self

    def process(self) -> Tuple[int, str]:
        """
        Process file using template method pattern.

        Returns:
            Tuple[int, str]: (records_count, status_message)

        Raises:
            Exception: If processing fails
        """
        try:
            # Mark processing as started
            self.file_upload.mark_processing_started()

            # Extract data from file
            raw_data = list(self._extract_data())

            # Validate schema
            self._validate_schema(raw_data)

            # Transform all records
            records = []
            for row in raw_data:
                # Parse using strategy
                parsed = self.strategy.parse_row(row)
                # Apply transformation pipeline
                transformed = self._apply_transformations(parsed)
                records.append(transformed)

            # Load records (to be implemented by subclasses)
            count = self._save_records(records)

            # Mark as completed
            self.file_upload.mark_processing_completed(count)
            return count, "Processing completed successfully"

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.file_upload.mark_processing_failed(error_msg)
            raise

    def _extract_data(self):
        """Extract data using adapter"""
        return self.adapter.read(self.file_upload.file)

    def _validate_schema(self, raw_data: List[Dict[str, Any]]):
        """Validate file schema"""
        if not raw_data:
            raise ValueError("File is empty")

        # Get columns from first row
        columns = list(raw_data[0].keys()) if raw_data else []

        # Validate using strategy
        if not self.strategy.validate_schema(columns):
            raise ValueError(f"File schema validation failed")

    def _apply_transformations(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply transformation pipeline"""
        result = data
        for transformer in self.transformers:
            result = transformer.execute(result)
        return result

    def _save_records(self, records: List[Dict[str, Any]]) -> int:
        """
        Save records to database.
        To be implemented by specialized orchestrators.

        Args:
            records: List of transformed record dictionaries

        Returns:
            int: Number of records saved
        """
        raise NotImplementedError("Subclasses must implement _save_records")
