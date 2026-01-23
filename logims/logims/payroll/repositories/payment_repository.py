"""
Payment repository for persisting payment records.
"""
from typing import Dict, List, Any
from django.db import transaction
from ..models import PaymentRecord

# Constants
BATCH_SIZE = 500


class PaymentRepository:
    """Repository for PaymentRecord persistence"""

    def __init__(self, file_upload):
        """
        Initialize repository.

        Args:
            file_upload: FileUpload instance
        """
        self.file_upload = file_upload
        self.metadata = file_upload.metadata
        if not self.metadata:
            raise ValueError("DocumentUploadMetadata not found for file_upload")

    def bulk_create(self, records: List[Dict[str, Any]]) -> int:
        """
        Bulk create payment records in a single transaction.
        Handles upsert logic (create or update existing).

        Args:
            records: List of payment record dictionaries

        Returns:
            int: Number of records created/updated
        """
        if not records:
            return 0

        # Extract driver UUIDs for lookup
        driver_uuids = [r['driver_uuid'] for r in records if r.get('driver_uuid')]

        # Fetch existing records
        # Match by company, date range, and driver_uuid to avoid duplicates
        # Also prioritize records from the same file_upload (for reprocessing)
        existing_records = {}
        for record in PaymentRecord.objects.filter(
            file_upload__metadata__company=self.metadata.company,
            file_upload__metadata__from_date=self.metadata.from_date,
            file_upload__metadata__to_date=self.metadata.to_date,
            driver_uuid__in=driver_uuids
        ).select_related('file_upload__metadata').order_by(
            # Prioritize records from the same file_upload (for reprocessing)
            '-file_upload_id' if self.file_upload.id else 'file_upload_id'
        ):
            # If multiple records exist for same driver_uuid, prefer the one from this file_upload
            driver_uuid = record.driver_uuid
            if driver_uuid not in existing_records:
                existing_records[driver_uuid] = record
            elif record.file_upload_id == self.file_upload.id:
                # Prefer record from this file_upload (reprocessing case)
                existing_records[driver_uuid] = record

        # Get valid model field names to filter out intermediate/calculation fields
        valid_fields = {f.name for f in PaymentRecord._meta.get_fields()}

        # Separate new and existing records
        new_records = []
        update_records = []

        for record_data in records:
            driver_uuid = record_data.get('driver_uuid')
            if not driver_uuid:
                continue

            # Filter record_data to only include fields that exist on the model
            filtered_data = {k: v for k, v in record_data.items() if k in valid_fields}

            if driver_uuid in existing_records:
                # Update existing record
                existing = existing_records[driver_uuid]
                for field, value in filtered_data.items():
                    if field != 'driver_uuid':  # Don't update UUID
                        setattr(existing, field, value)
                existing.file_upload = self.file_upload
                update_records.append(existing)
            else:
                # Create new record - only use fields that exist on the model
                filtered_data['file_upload'] = self.file_upload
                new_records.append(PaymentRecord(**filtered_data))

        # Bulk create new records
        created_count = 0
        if new_records:
            PaymentRecord.objects.bulk_create(new_records, batch_size=BATCH_SIZE)
            created_count = len(new_records)

        # Bulk update existing records
        updated_count = 0
        if update_records:
            # Get updateable fields (exclude primary key, id, and created_at)
            updateable_fields = [
                f.name for f in PaymentRecord._meta.get_fields()
                if not f.primary_key and f.name not in ('id', 'created_at')
            ]
            PaymentRecord.objects.bulk_update(update_records, fields=updateable_fields, batch_size=BATCH_SIZE)
            updated_count = len(update_records)

        return created_count + updated_count
