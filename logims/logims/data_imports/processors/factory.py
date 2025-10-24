from typing import Type
from .base import BaseExcelProcessor
from .uber_eats import UberEatsProcessor
from ..models import FileUpload


class ProcessorFactory:
    """Factory class to create company-specific Excel processors"""

    _processors = {
        'uber_eats': UberEatsProcessor,
        # Add more companies here as needed
        # 'deliveroo': DeliverooProcessor,
        # 'foodpanda': FoodPandaProcessor,
    }

    @classmethod
    def get_processor(cls, file_upload: FileUpload) -> BaseExcelProcessor:
        """
        Get the appropriate processor for the company

        Args:
            file_upload: FileUpload instance with company information

        Returns:
            BaseExcelProcessor: Company-specific processor instance

        Raises:
            ValueError: If no processor is found for the company
        """
        company_code = file_upload.company.code.lower()

        if company_code not in cls._processors:
            available_processors = ', '.join(cls._processors.keys())
            raise ValueError(
                f"No processor found for company '{company_code}'. "
                f"Available processors: {available_processors}"
            )

        processor_class = cls._processors[company_code]
        return processor_class(file_upload)

    @classmethod
    def register_processor(cls, company_code: str, processor_class: Type[BaseExcelProcessor]):
        """
        Register a new processor for a company

        Args:
            company_code: Company code (e.g., 'uber_eats')
            processor_class: Processor class that extends BaseExcelProcessor
        """
        cls._processors[company_code.lower()] = processor_class

    @classmethod
    def get_available_processors(cls) -> list:
        """Get list of available processor company codes"""
        return list(cls._processors.keys())

    @classmethod
    def is_processor_available(cls, company_code: str) -> bool:
        """Check if a processor is available for a company"""
        return company_code.lower() in cls._processors
