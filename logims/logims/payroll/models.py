"""
Payroll module models.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from logims.uploads.models import FileUpload


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
            # Performance indexes for common query patterns
            models.Index(fields=['driver_id_at_calculation']),
            models.Index(fields=['supervisor_id_at_calculation']),
            models.Index(fields=['file_upload', 'driver_uuid']),  # Composite for filtering
            models.Index(fields=['driver_id_at_calculation', 'file_upload']),  # For aggregation queries
        ]

    def __str__(self):
        metadata = self.file_upload.metadata
        company_name = metadata.company.name if metadata else "Unknown"
        return f"{self.driver_first_name} {self.driver_last_name} - {company_name}"

    @classmethod
    def upsert_payment_record(cls, file_upload, driver_uuid, payment_data):
        """
        Create or update a payment record for a specific company, period, and driver.
        This ensures only one payment record exists per company/period/driver combination.
        """
        metadata = file_upload.payment_metadata
        if not metadata:
            raise ValueError("PaymentUploadMetadata not found for file_upload")

        # Find existing record for the same company, period, and driver
        existing_record = cls.objects.filter(
            file_upload__payment_metadata__company=metadata.company,
            file_upload__payment_metadata__from_date=metadata.from_date,
            file_upload__payment_metadata__to_date=metadata.to_date,
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
        metadata = self.file_upload.metadata
        if metadata:
            return f"{metadata.company.name}_{metadata.from_date}_{metadata.to_date}_{self.driver_uuid}"
        return f"{self.driver_uuid}"
