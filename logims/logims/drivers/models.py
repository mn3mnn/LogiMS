from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

from .utils import driver_document_path
from .enums import DriverDocumentsStatus
from logims.storage_backends import R2MediaStorage


class Supervisor(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    percentage = models.FloatField(
        help_text="Percentage (e.g., 15 for 15%)",
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Driver(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    nid = models.CharField(max_length=100, unique=True, null=True, blank=True)
    uuid = models.CharField(max_length=100, null=True, blank=True, unique=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    supervisor = models.ForeignKey(Supervisor, on_delete=models.SET_NULL, null=True, blank=True, related_name="drivers")
    phone_number = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    company = models.ForeignKey("companies.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="drivers")
    insurance = models.FloatField(
        null=True, blank=True, help_text="Insurance amount",
        validators=[MinValueValidator(0), MaxValueValidator(100000)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.first_name + " " + self.last_name


class Document(models.Model):
    # Store driver documents in R2
    file = models.FileField(upload_to=driver_document_path, storage=R2MediaStorage())
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Ensure the underlying file is deleted from storage when the document
        is deleted via the admin or API.
        """
        if self.file:
            self.file.delete(save=False)
        return super().delete(using=using, keep_parents=keep_parents)

    @property
    def is_expired(self):
        return self.expiry_date and self.expiry_date < timezone.now().date()

    @property
    def status(self):
        """
        Get the status of this individual document.
        Returns DriverDocumentsStatus enum value.
        """
        if not self.file:
            return DriverDocumentsStatus.MISSING

        if self.is_expired:
            return DriverDocumentsStatus.EXPIRED

        return DriverDocumentsStatus.VALID

class DriverNationalID(Document):
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name="national_id_doc")


class DriverContract(Document):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="contracts")
    contract_number = models.CharField(max_length=50, blank=True)



class DriverLicense(Document):
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name="license")
    license_number = models.CharField(max_length=50, blank=True)
    license_type = models.CharField(max_length=50, blank=True)


class DriverVehicleLicense(Document):
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE, related_name="vehicle_license")
    license_number = models.CharField(max_length=50, blank=True)
    license_plate = models.CharField(max_length=20, blank=True)
    license_type = models.CharField(max_length=20, blank=True)
    vehicle_type = models.CharField(max_length=50, blank=True)


