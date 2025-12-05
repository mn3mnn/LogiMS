from django.db import models
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from enum import Enum

from logims.storage_backends import R2MediaStorage


class FileType(models.TextChoices):
    PAYMENTS = "payments", "Payments/Payroll"
    TRIPS = "trips", "Trip Details"


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class TaxConfiguration(models.Model):
    """Model to configure tax rates and deductions for different companies"""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="tax_configurations"
    )
    name = models.CharField(max_length=100, help_text="Tax configuration name (e.g., 'Income Tax', 'Social Security')")
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Tax rate as percentage (e.g., 15.5 for 15.5%)"
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True, help_text="Description of what this tax covers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'name']
        unique_together = ['company', 'name']

    def __str__(self):
        return f"{self.company.name} - {self.name} ({self.tax_rate}%)"


class FileUpload(models.Model):
    """Model to track uploaded Excel files for processing"""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="file_uploads"
    )
    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        help_text="Type of data in the file (Excel or CSV)"
    )
    file = models.FileField(
        upload_to="file_uploads/%Y/%m/%d/",
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv'])],
        storage=R2MediaStorage(),  # Store uploaded Excel/CSV files in R2
    )
    from_date = models.DateField(help_text="Start date for the data period")
    to_date = models.DateField(help_text="End date for the data period")
    status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    processed_records_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_files"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'file_type']),
            models.Index(fields=['status']),
            models.Index(fields=['from_date', 'to_date']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.get_file_type_display()} ({self.from_date} to {self.to_date})"

    def delete(self, using=None, keep_parents=False):
        """
        Ensure the underlying uploaded file is deleted from storage when the
        FileUpload record is deleted via the admin or API.
        """
        if self.file:
            self.file.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)

    def mark_processing_started(self):
        """Mark file as processing started"""
        self.status = ProcessingStatus.PROCESSING
        self.processing_started_at = timezone.now()
        self.save(update_fields=['status', 'processing_started_at'])

    def mark_processing_completed(self, records_count=0):
        """Mark file as processing completed"""
        self.status = ProcessingStatus.COMPLETED
        self.processing_completed_at = timezone.now()
        self.processed_records_count = records_count
        self.save(update_fields=['status', 'processing_completed_at', 'processed_records_count'])

    def mark_processing_failed(self, error_message):
        """Mark file as processing failed"""
        self.status = ProcessingStatus.FAILED
        self.processing_completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'processing_completed_at', 'error_message'])


class PaymentRecord(models.Model):
    """Model to store processed payment/payroll data"""

    file_upload = models.ForeignKey(
        FileUpload,
        on_delete=models.CASCADE,
        related_name="payment_records"
    )
    driver = models.ForeignKey("drivers.Driver", on_delete=models.SET_NULL, null=True,
                               blank=True, related_name="payment_records", help_text="Foreign key to Driver model")

    driver_uuid = models.CharField(max_length=100, db_index=True)
    driver_first_name = models.CharField(max_length=255)
    driver_last_name = models.CharField(max_length=255)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    net_fare = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promotions = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refunds_and_fees = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payouts = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bank_transfer = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cash_collected = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fare_tax = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tips = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    taxes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    other_revenue = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)


    # Deduction fields
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Total deductions (tax + agency share + insurance)")
    tax_deduction = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Tax amount deducted")
    agency_share_deduction = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Agency share amount deducted")
    insurance_deduction = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Insurance amount deducted")
    final_net_earnings = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Final earnings after all deductions")

    # Calculation metadata fields
    calculation_version = models.CharField(max_length=50, default='1.0', help_text="Version of calculation logic used")
    calculated_at = models.DateTimeField(null=True, blank=True, help_text="When calculations were last performed")

    # Applied rates at calculation time (for audit)
    applied_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                           help_text="Total tax rate used at calculation time (sum of all active tax rates)")
    applied_agency_share_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                                    help_text="Agency share percentage used at calculation time")
    applied_insurance_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                                   help_text="Insurance amount used at calculation time")

    # supervisor snapshots at calculation time
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
            models.Index(fields=['driver_uuid']),
            models.Index(fields=['file_upload']),
        ]

    def __str__(self):
        return f"{self.driver_first_name} {self.driver_last_name} - {self.file_upload.company.name}"

    @classmethod
    def upsert_payment_record(cls, file_upload, driver_uuid, payment_data):
        """
        Create or update a payment record for a specific company, period, and driver.
        This ensures only one payment record exists per company/period/driver combination.
        """
        # Find existing record for the same company, period, and driver
        existing_record = cls.objects.filter(
            file_upload__company=file_upload.company,
            file_upload__from_date=file_upload.from_date,
            file_upload__to_date=file_upload.to_date,
            driver_uuid=driver_uuid
        ).first()

        if existing_record:
            # Update existing record
            for field, value in payment_data.items():
                setattr(existing_record, field, value)
            existing_record.save()
            return existing_record, False  # False = updated
        else:
            # Create new record
            payment_data['file_upload'] = file_upload
            payment_data['driver_uuid'] = driver_uuid
            new_record = cls.objects.create(**payment_data)
            return new_record, True  # True = created

    def get_uniqueness_key(self):
        """Get the uniqueness key for this payment record"""
        return f"{self.file_upload.company.name}_{self.file_upload.from_date}_{self.file_upload.to_date}_{self.driver_uuid}"


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
