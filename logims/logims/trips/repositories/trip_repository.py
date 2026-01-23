"""
Trip repository for persisting trip records.
"""
from typing import Dict, List, Any
from ..models import TripRecord

# Constants
BATCH_SIZE = 500


class TripRepository:
    """Repository for TripRecord persistence"""

    def __init__(self, file_upload):
        """Initialize repository"""
        self.file_upload = file_upload

    def bulk_create(self, records: List[Dict[str, Any]]) -> int:
        """
        Bulk create trip records in a single transaction.
        Handles upsert logic (create or update existing by trip_uuid).
        """
        if not records:
            return 0

        # Extract trip UUIDs for lookup
        trip_uuids = [r['trip_uuid'] for r in records if r.get('trip_uuid')]

        # Fetch existing records
        # Prioritize records from the same file_upload (for reprocessing)
        existing_records = {}
        for record in TripRecord.objects.filter(trip_uuid__in=trip_uuids).order_by(
            # Prioritize records from the same file_upload (for reprocessing)
            '-file_upload_id' if self.file_upload.id else 'file_upload_id'
        ):
            trip_uuid = record.trip_uuid
            # If multiple records exist for same trip_uuid, prefer the one from this file_upload
            if trip_uuid not in existing_records:
                existing_records[trip_uuid] = record
            elif record.file_upload_id == self.file_upload.id:
                # Prefer record from this file_upload (reprocessing case)
                existing_records[trip_uuid] = record

        # Get valid model field names to filter out intermediate/calculation fields
        valid_fields = {f.name for f in TripRecord._meta.get_fields()}

        # Separate new and existing records
        new_records = []
        update_records = []

        for record_data in records:
            trip_uuid = record_data.get('trip_uuid')
            if not trip_uuid:
                continue

            # Filter record_data to only include fields that exist on the model
            filtered_data = {k: v for k, v in record_data.items() if k in valid_fields}

            if trip_uuid in existing_records:
                # Update existing record
                existing = existing_records[trip_uuid]
                for field, value in filtered_data.items():
                    if field != 'trip_uuid':  # Don't update UUID
                        setattr(existing, field, value)
                existing.file_upload = self.file_upload
                update_records.append(existing)
            else:
                # Create new record - only use fields that exist on the model
                filtered_data['file_upload'] = self.file_upload
                new_records.append(TripRecord(**filtered_data))

        # Bulk create new records
        created_count = 0
        if new_records:
            TripRecord.objects.bulk_create(new_records, batch_size=BATCH_SIZE)
            created_count = len(new_records)

        # Bulk update existing records
        updated_count = 0
        if update_records:
            # Get updateable fields (exclude primary key, id, and created_at)
            updateable_fields = [
                f.name for f in TripRecord._meta.get_fields()
                if not f.primary_key and f.name not in ('id', 'created_at')
            ]
            TripRecord.objects.bulk_update(update_records, fields=updateable_fields, batch_size=BATCH_SIZE)
            updated_count = len(update_records)

        return created_count + updated_count
