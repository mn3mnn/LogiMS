"""
Trip processing service.
Orchestrates the trip file processing flow.
"""
from typing import Tuple
from django.db import transaction
from logims.uploads.adapters.factory import AdapterFactory
from logims.uploads.orchestrator.base import ProcessingOrchestrator
from ..strategies.factory import TripStrategyFactory
from ..transforms.duration_calculator import DurationCalculatorTransformer
from ..transforms.driver_metadata import DriverMetadataTransformer
from ..transforms.validation import TripValidationTransformer
from ..repositories.trip_repository import TripRepository


class TripProcessingOrchestrator(ProcessingOrchestrator):
    """Trip-specific orchestrator"""

    def _save_records(self, records) -> int:
        """Save trip records using repository"""
        repository = TripRepository(self.file_upload)
        return repository.bulk_create(records)


class TripProcessingService:
    """Service for processing trip files"""

    def __init__(self, file_upload):
        """Initialize trip processing service"""
        self.file_upload = file_upload
        self.metadata = file_upload.metadata
        if not self.metadata:
            raise ValueError("DocumentUploadMetadata not found for file_upload")

    def process(self) -> Tuple[int, str]:
        """Process trip file"""
        # Get adapter based on file extension
        adapter = AdapterFactory.get_adapter(self.file_upload.file)

        # Get company-specific strategy
        strategy = TripStrategyFactory.get_strategy(
            company_code=self.metadata.company.code,
            company=self.metadata.company
        )

        # Create orchestrator
        orchestrator = TripProcessingOrchestrator(
            file_upload=self.file_upload,
            strategy=strategy,
            adapter=adapter
        )

        # Build transformation pipeline
        orchestrator.add_transformer(
            DurationCalculatorTransformer()
        ).add_transformer(
            DriverMetadataTransformer()
        ).add_transformer(
            TripValidationTransformer()
        )

        # Process entire file in single transaction
        with transaction.atomic():
            return orchestrator.process()
