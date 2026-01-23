"""
Trips module models.
"""
from django.db import models
from logims.uploads.models import FileUpload


class TripRecord(models.Model):
    """Model to store processed trip/order data"""

    file_upload = models.ForeignKey(
        FileUpload,
        on_delete=models.CASCADE,
        related_name="trip_records"
    )
    driver = models.ForeignKey("drivers.Driver", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="trip_records", help_text="Foreign key to Driver model")

    trip_uuid = models.CharField(max_length=100, db_index=True, unique=True)
    driver_uuid = models.CharField(max_length=100, db_index=True)
    driver_first_name = models.CharField(max_length=255)
    driver_last_name = models.CharField(max_length=255)
    vehicle_uuid = models.CharField(max_length=100, null=True, blank=True)
    license_plate = models.CharField(max_length=50, null=True, blank=True)
    service_type = models.CharField(max_length=100, null=True, blank=True)
    order_time = models.DateTimeField(null=True, blank=True)
    arrival_time = models.DateTimeField(null=True, blank=True)
    pickup_address = models.TextField(null=True, blank=True)
    destination_address = models.TextField(null=True, blank=True)
    trip_distance = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    trip_status = models.CharField(max_length=100, null=True, blank=True)
    order_submitted_time = models.DateTimeField(null=True, blank=True)
    trip_start_time = models.DateTimeField(null=True, blank=True)
    vehicle_location_at_assignment = models.TextField(null=True, blank=True)
    fare_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Additional calculated fields
    trip_duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Calculation metadata fields
    calculation_version = models.CharField(max_length=50, default='1.0', help_text="Version of calculation logic used")
    calculated_at = models.DateTimeField(null=True, blank=True, help_text="When calculations were last performed")

    # driver and supervisor snapshots at calculation time
    driver_id_at_calculation = models.IntegerField(null=True, blank=True, help_text="Driver ID at time of calculation")
    supervisor_id_at_calculation = models.IntegerField(null=True, blank=True,
                                                       help_text="Supervisor ID at time of calculation")
    supervisor_name_at_calculation = models.CharField(max_length=255, null=True, blank=True,
                                                      help_text="Supervisor name at time of calculation")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['trip_uuid']),
            models.Index(fields=['driver_uuid']),
            models.Index(fields=['file_upload']),
            models.Index(fields=['order_time']),
            # Performance indexes for common query patterns
            models.Index(fields=['driver_id_at_calculation']),
            models.Index(fields=['supervisor_id_at_calculation']),
            models.Index(fields=['trip_status']),
            models.Index(fields=['file_upload', 'driver_uuid']),  # Composite for filtering
            models.Index(fields=['driver_id_at_calculation', 'file_upload']),  # For aggregation queries
        ]

    def __str__(self):
        return f"Trip {self.trip_uuid} - {self.driver_first_name} {self.driver_last_name}"

    @classmethod
    def upsert_trip_record(cls, file_upload, trip_uuid, trip_data):
        """Create or update a trip record by unique trip_uuid.
        On update, also re-associate the record to the latest file_upload.
        """
        existing = cls.objects.filter(trip_uuid=trip_uuid).first()
        if existing:
            # update fields
            for field, value in trip_data.items():
                setattr(existing, field, value)
            # ensure association reflects latest upload
            existing.file_upload = file_upload
            existing.save()
            return existing, False
        else:
            trip_data['file_upload'] = file_upload
            trip_data['trip_uuid'] = trip_uuid
            new_rec = cls.objects.create(**trip_data)
            return new_rec, True
