from rest_framework import serializers

from logims.companies.models import Company
from ..models import Driver, DriverNationalID, DriverContract, DriverLicense, DriverVehicleLicense


class DriverContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverContract
        fields = ["id", "file", "notes", "issue_date", "expiry_date", "contract_number"]

class DriverLicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverLicense
        fields = ["id", "file", "notes", "issue_date", "expiry_date", "license_number", "license_type"]

class DriverNationalIDSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverNationalID
        fields = ["id", "file", "notes", "issue_date", "expiry_date"]

class DriverVehicleLicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverVehicleLicense
        fields = ["id", "file", "notes", "issue_date", "expiry_date", "license_number", "license_plate", "license_type", "vehicle_type"]


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
            "id", "first_name", "last_name", "uuid", "phone_number",
            "is_active", "company_code", "company_name",
            "contracts", "license", "national_id_doc", "vehicle_license",
            "created_at", "updated_at",
        ]


class DriverCreateUpdateSerializer(serializers.ModelSerializer):
    company_code = serializers.CharField(write_only=True)
    contracts = DriverContractSerializer(many=True, write_only=True, required=False)
    license = DriverLicenseSerializer(write_only=True, required=False)
    national_id_doc = DriverNationalIDSerializer(write_only=True, required=False)
    vehicle_license = DriverVehicleLicenseSerializer(write_only=True, required=False)

    class Meta:
        model = Driver
        fields = [
            "first_name", "last_name", "uuid", "phone_number",
            "is_active", "company_code",
            "contracts", "license", "national_id_doc", "vehicle_license",
        ]

    def create(self, validated_data):
        company_code = validated_data.pop("company_code")
        company = Company.objects.get(code=company_code)

        contracts_data = validated_data.pop("contracts", [])
        license_data = validated_data.pop("license", None)
        nid_data = validated_data.pop("national_id_doc", None)
        vlicense_data = validated_data.pop("vehicle_license", None)

        driver = Driver.objects.create(company=company, **validated_data)

        for contract in contracts_data:
            DriverContract.objects.create(driver=driver, **contract)

        if license_data:
            DriverLicense.objects.create(driver=driver, **license_data)

        if nid_data:
            DriverNationalID.objects.create(driver=driver, **nid_data)

        if vlicense_data:
            DriverVehicleLicense.objects.create(driver=driver, **vlicense_data)

        return driver
