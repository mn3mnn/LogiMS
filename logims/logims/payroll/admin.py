"""
Django admin configuration for payroll models.
"""
from django.contrib import admin
from .models import PaymentRecord, TaxConfiguration


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'driver_first_name', 'driver_last_name', 'total_revenue', 'final_net_earnings', 'created_at']
    list_filter = ['created_at', 'file_upload__metadata__company']
    search_fields = ['driver_first_name', 'driver_last_name', 'driver_uuid']
    readonly_fields = ['calculation_version', 'calculated_at']


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ['company', 'name', 'tax_rate', 'is_active', 'created_at']
    list_filter = ['company', 'is_active']
    search_fields = ['company__name', 'name']
