"""
Validation service for file uploads.
Handles validation logic separated from serializers.
"""
import os
from typing import Optional, Tuple, Any, TYPE_CHECKING
from rest_framework import serializers
from logims.uploads.models import FileType, FileUpload

if TYPE_CHECKING:
    from django.db.models import Model


# Constants
ALLOWED_FILE_EXTENSIONS = frozenset([
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv',
    '.jpg', '.jpeg', '.png', '.zip', '.rar'
])

FILE_TYPES_REQUIRING_COMPANY = {FileType.PAYMENTS, FileType.TRIPS}
FILE_TYPES_REQUIRING_DATES = {FileType.PAYMENTS, FileType.TRIPS, FileType.EXPENSES}


class FileUploadValidationService:
    """Service for validating file upload data"""

    @staticmethod
    def validate_file_type_and_metadata(
        data: dict,
        instance: Optional[FileUpload] = None
    ) -> None:
        """
        Validate file type and required metadata fields.

        Args:
            data: Serializer data dictionary
            instance: Existing FileUpload instance (for updates)

        Raises:
            serializers.ValidationError: If validation fails
        """
        file_type = data.get('file_type') or (instance.file_type if instance else None)
        if not file_type:
            raise serializers.ValidationError({'file_type': 'File type is required'})

        # Extract and enrich metadata from instance if available
        company_id, from_date, to_date = FileUploadValidationService._extract_metadata(
            data, instance
        )

        # Validate file type specific requirements
        FileUploadValidationService._validate_file_type_requirements(
            file_type, company_id, from_date, to_date
        )

        # Validate date range
        FileUploadValidationService._validate_date_range(from_date, to_date)

        # Validate file extension
        FileUploadValidationService._validate_file_extension(data.get('file'))

    @staticmethod
    def _extract_metadata(
        data: dict,
        instance: Optional[FileUpload]
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """
        Extract metadata from data and instance, enriching with existing values for partial updates.

        Args:
            data: Serializer data dictionary
            instance: Optional FileUpload instance

        Returns:
            Tuple of (company_id, from_date, to_date)
        """
        company_id = data.get('company')
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        # For partial updates, enrich with existing metadata if not provided
        if instance:
            # Use select_related if available, otherwise access directly
            metadata = getattr(instance, 'metadata', None)
            if metadata:
                if from_date is None:
                    from_date = metadata.from_date
                if to_date is None:
                    to_date = metadata.to_date
                if company_id is None and metadata.company:
                    company_id = metadata.company.id

        return company_id, from_date, to_date

    @staticmethod
    def _validate_file_type_requirements(
        file_type: str,
        company_id: Optional[int],
        from_date: Optional[str],
        to_date: Optional[str]
    ) -> None:
        """
        Validate file type specific requirements.

        Args:
            file_type: File type string
            company_id: Optional company ID
            from_date: Optional from date string
            to_date: Optional to date string

        Raises:
            serializers.ValidationError: If validation fails
        """
        # Company validation for payments and trips
        if file_type in FILE_TYPES_REQUIRING_COMPANY:
            if not company_id:
                raise serializers.ValidationError({
                    'company': 'Company is required for payments and trips'
                })
            FileUploadValidationService._validate_strategy_available(file_type, company_id)

        # Date validation for payments, trips, and expenses
        if file_type in FILE_TYPES_REQUIRING_DATES:
            if not from_date or not to_date:
                file_type_display = dict(FileType.choices).get(file_type, file_type)
                raise serializers.ValidationError({
                    'from_date': f'Date range is required for {file_type_display.lower()}',
                    'to_date': f'Date range is required for {file_type_display.lower()}'
                })

    @staticmethod
    def _validate_date_range(from_date: Optional[str], to_date: Optional[str]) -> None:
        """
        Validate that from_date is not later than to_date.

        Args:
            from_date: Optional from date string
            to_date: Optional to date string

        Raises:
            serializers.ValidationError: If validation fails
        """
        if from_date and to_date and from_date > to_date:
            raise serializers.ValidationError({
                'from_date': 'From date cannot be later than to date'
            })

    @staticmethod
    def _validate_file_extension(file: Optional[Any]) -> None:
        """
        Validate file extension against allowed list.

        Args:
            file: Optional file object

        Raises:
            serializers.ValidationError: If validation fails
        """
        if not file:
            return

        # Use os.path.splitext for proper extension extraction
        _, ext = os.path.splitext(file.name)
        ext_lower = ext.lower()

        if ext_lower not in ALLOWED_FILE_EXTENSIONS:
            raise serializers.ValidationError({
                'file': f"Unsupported file type '{ext_lower}'. "
                       f"Allowed: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
            })

    @staticmethod
    def _validate_strategy_available(file_type: str, company_id: int):
        """
        Validate that a processing strategy is available for the company.

        Args:
            file_type: Type of file (PAYMENTS or TRIPS)
            company_id: Company ID

        Raises:
            serializers.ValidationError: If strategy is not available
        """
        from logims.companies.models import Company

        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            raise serializers.ValidationError({'company': 'Company not found'})

        # Strategy factory mapping
        strategy_factories = {
            FileType.PAYMENTS: ('logims.payroll.strategies.factory', 'PaymentStrategyFactory'),
            FileType.TRIPS: ('logims.trips.strategies.factory', 'TripStrategyFactory'),
        }

        factory_path, factory_name = strategy_factories.get(file_type, (None, None))
        if not factory_path:
            return  # No strategy validation needed for this file type

        # Dynamically import and check strategy availability
        module = __import__(factory_path, fromlist=[factory_name])
        factory_class = getattr(module, factory_name)

        if not factory_class.is_strategy_available(company.code):
            raise serializers.ValidationError({
                'company': f"No processor available for company '{company.name}'"
            })
