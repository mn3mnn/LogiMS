"""
Payment processing service.
Orchestrates the payment file processing flow.
"""
from typing import Tuple
from django.db import transaction
from logims.uploads.adapters.factory import AdapterFactory
from logims.uploads.orchestrator.base import ProcessingOrchestrator
from ..strategies.factory import PaymentStrategyFactory
from ..transforms.driver_metadata import DriverMetadataTransformer
from ..transforms.tax_calculator import TaxCalculationTransformer
from ..transforms.agency_share_calculator import AgencyShareCalculatorTransformer
from ..transforms.insurance_calculator import InsuranceCalculatorTransformer
from ..transforms.deduction_aggregator import DeductionAggregatorTransformer
from ..transforms.validation import PaymentValidationTransformer
from ..repositories.payment_repository import PaymentRepository


class PaymentProcessingOrchestrator(ProcessingOrchestrator):
    """Payment-specific orchestrator"""

    def _save_records(self, records) -> int:
        """
        Save payment records using repository.

        Args:
            records: List of transformed payment record dictionaries

        Returns:
            int: Number of records saved
        """
        repository = PaymentRepository(self.file_upload)
        return repository.bulk_create(records)


class PaymentProcessingService:
    """
    Service for processing payment files.
    Coordinates adapter, strategy, transformers, and repository.
    """

    def __init__(self, file_upload):
        """
        Initialize payment processing service.

        Args:
            file_upload: FileUpload instance with payment_metadata
        """
        self.file_upload = file_upload
        self.metadata = file_upload.metadata
        if not self.metadata:
            raise ValueError("DocumentUploadMetadata not found for file_upload")

    def process(self) -> Tuple[int, str]:
        """
        Process payment file.

        Returns:
            Tuple[int, str]: (records_count, status_message)
        """
        # Get adapter based on file extension
        adapter = AdapterFactory.get_adapter(self.file_upload.file)

        # Get company-specific strategy
        strategy = PaymentStrategyFactory.get_strategy(
            company_code=self.metadata.company.code,
            company=self.metadata.company
        )

        # Create orchestrator
        orchestrator = PaymentProcessingOrchestrator(
            file_upload=self.file_upload,
            strategy=strategy,
            adapter=adapter
        )

        # Build transformation pipeline
        orchestrator.add_transformer(
            DriverMetadataTransformer()
        ).add_transformer(
            TaxCalculationTransformer(company=self.metadata.company)
        ).add_transformer(
            AgencyShareCalculatorTransformer()
        ).add_transformer(
            InsuranceCalculatorTransformer()
        ).add_transformer(
            DeductionAggregatorTransformer()
        ).add_transformer(
            PaymentValidationTransformer()
        )

        # Process entire file in single transaction
        with transaction.atomic():
            return orchestrator.process()
