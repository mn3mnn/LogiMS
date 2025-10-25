from rest_framework import serializers

from logims.companies.models import Company
from ..models import Driver, DriverNationalID, DriverContract, DriverLicense, DriverVehicleLicense


class BaseDocumentSerializer(serializers.ModelSerializer):
    driver_id = serializers.IntegerField()

    class Meta:
        fields = ["id", "driver_id", "file", "notes", "issue_date", "expiry_date", "status"]
        abstract = True

    def validate_driver_id(self, value):
        """Check that the driver exists."""
        if not Driver.objects.filter(id=value).exists():
            raise serializers.ValidationError("Driver with this ID does not exist.")
        return value

    def create(self, validated_data):
        """Attach the driver to the document before saving."""
        driver_id = validated_data.pop("driver_id")
        driver = Driver.objects.get(id=driver_id)
        return self.Meta.model.objects.create(driver=driver, **validated_data)


class DriverContractSerializer(BaseDocumentSerializer):
    class Meta(BaseDocumentSerializer.Meta):
        model = DriverContract
        fields = BaseDocumentSerializer.Meta.fields + ["contract_number"]


class DriverLicenseSerializer(BaseDocumentSerializer):
    class Meta(BaseDocumentSerializer.Meta):
        model = DriverLicense
        fields = BaseDocumentSerializer.Meta.fields + ["license_number", "license_type"]

    def validate_driver_id(self, value):
        value = super().validate_driver_id(value)
        if DriverLicense.objects.filter(driver_id=value).exists():
            raise serializers.ValidationError("A license already exists for this driver.")
        return value


class DriverVehicleLicenseSerializer(BaseDocumentSerializer):
    class Meta(BaseDocumentSerializer.Meta):
        model = DriverVehicleLicense
        fields = BaseDocumentSerializer.Meta.fields + [
            "license_number", "license_plate", "license_type", "vehicle_type"
        ]

    def validate_driver_id(self, value):
        value = super().validate_driver_id(value)
        if DriverVehicleLicense.objects.filter(driver_id=value).exists():
            raise serializers.ValidationError("A vehicle license already exists for this driver.")
        return value


class DriverNationalIDSerializer(BaseDocumentSerializer):
    class Meta(BaseDocumentSerializer.Meta):
        model = DriverNationalID
        fields = BaseDocumentSerializer.Meta.fields


class DriverSerializer(serializers.ModelSerializer):
    contracts = DriverContractSerializer(many=True, read_only=True)
    license = DriverLicenseSerializer(read_only=True)
    national_id_doc = DriverNationalIDSerializer(read_only=True)
    vehicle_license = DriverVehicleLicenseSerializer(read_only=True)
    company_code = serializers.CharField(source="company.code", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Driver
        fields = [
            "id", "first_name", "last_name", "nid", "uuid", "email", "reports_to", "phone_number",
            "is_active", "company_code", "company_name", "insurance", "agency_share",
            "contracts", "license", "national_id_doc", "vehicle_license",
            "created_at", "updated_at",
        ]


class DriverCreateUpdateSerializer(serializers.ModelSerializer):
    company_code = serializers.CharField(write_only=True)

    class Meta:
        model = Driver
        fields = [
            "id", "first_name", "last_name", "nid", "uuid", "email", "reports_to", "phone_number",
            "is_active", "company_code", "insurance", "agency_share",
        ]

    def create(self, validated_data):
        company_code = validated_data.pop("company_code")
        company = Company.objects.get(code=company_code)
        driver = Driver.objects.create(company=company, **validated_data)
        return driver

    def update(self, instance, validated_data):
        company_code = validated_data.pop("company_code", None)
        if company_code:
            instance.company = Company.objects.get(code=company_code)
        return super().update(instance, validated_data)
