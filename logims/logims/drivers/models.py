from django.db import models
from django.utils import timezone

from .utils import driver_document_path


class Driver(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    uuid = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    company = models.ForeignKey("companies.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="drivers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.first_name + " " + self.last_name


class Document(models.Model):
    file = models.FileField(upload_to=driver_document_path)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        abstract = True

    @property
    def is_expired(self):
        return self.expiry_date and self.expiry_date < timezone.now().date()

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


