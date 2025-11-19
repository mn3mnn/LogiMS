from django.contrib import admin
from .models import (
    Driver,
    DriverNationalID,
    DriverContract,
    DriverLicense,
    DriverVehicleLicense,
)


class DriverNationalIDInline(admin.StackedInline):
    model = DriverNationalID
    extra = 0


class DriverLicenseInline(admin.StackedInline):
    model = DriverLicense
    extra = 0


class DriverVehicleLicenseInline(admin.StackedInline):
    model = DriverVehicleLicense
    extra = 0


class DriverContractInline(admin.TabularInline):
    model = DriverContract
    extra = 1


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "company",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "company")
    search_fields = ("first_name", "last_name", "email", "phone_number", "uuid")
    readonly_fields = ("created_at", "updated_at")
    inlines = [
        DriverNationalIDInline,
        DriverLicenseInline,
        DriverVehicleLicenseInline,
        DriverContractInline,
    ]


@admin.register(DriverNationalID)
class DriverNationalIDAdmin(admin.ModelAdmin):
    list_display = ("id", "driver", "issue_date", "expiry_date", "is_active", "uploaded_at")
    search_fields = ("driver__first_name", "driver__last_name")
    list_filter = ("is_active",)


@admin.register(DriverContract)
class DriverContractAdmin(admin.ModelAdmin):
    list_display = ("id", "driver", "contract_number", "issue_date", "expiry_date", "is_active")
    search_fields = ("driver__first_name", "driver__last_name", "contract_number")
    list_filter = ("is_active",)


@admin.register(DriverLicense)
class DriverLicenseAdmin(admin.ModelAdmin):
    list_display = ("id", "driver", "license_number", "license_type", "expiry_date", "is_active")
    search_fields = ("driver__first_name", "driver__last_name", "license_number")
    list_filter = ("license_type", "is_active")


@admin.register(DriverVehicleLicense)
class DriverVehicleLicenseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver",
        "license_number",
        "license_plate",
        "vehicle_type",
        "expiry_date",
        "is_active",
    )
    search_fields = ("driver__first_name", "driver__last_name", "license_number", "license_plate")
    list_filter = ("vehicle_type", "is_active")
