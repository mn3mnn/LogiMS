"""
Django admin configuration for trips models.
"""
from django.contrib import admin
from .models import TripRecord


@admin.register(TripRecord)
class TripRecordAdmin(admin.ModelAdmin):
    list_display = ['trip_uuid', 'driver_first_name', 'driver_last_name', 'trip_status', 'fare_amount', 'created_at']
    list_filter = ['trip_status', 'created_at', 'file_upload__metadata__company']
    search_fields = ['trip_uuid', 'driver_first_name', 'driver_last_name', 'driver_uuid']
    readonly_fields = ['calculation_version', 'calculated_at']
