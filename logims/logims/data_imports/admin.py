from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import FileUpload, PaymentRecord, TripRecord, TaxConfiguration


@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ['company', 'name', 'tax_rate', 'is_active', 'created_at']
    list_filter = ['company', 'is_active', 'created_at']
    search_fields = ['company__name', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'name', 'tax_rate', 'is_active')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('company')


@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'company', 'file_type', 'file_name', 'from_date', 'to_date',
        'status_badge', 'processed_records_count', 'created_by', 'created_at'
    ]
    list_filter = ['company', 'file_type', 'status', 'created_at']
    search_fields = ['company__name', 'file__name', 'created_by__username']
    readonly_fields = [
        'id', 'status', 'processing_started_at', 'processing_completed_at',
        'processed_records_count', 'created_at', 'updated_at'
    ]
    help_text = "Files are automatically processed after upload. Processing starts immediately when a file is uploaded via API or admin panel. Duplicate payment records (same company, period, driver) will be updated instead of creating new ones."
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'company', 'file_type', 'file', 'from_date', 'to_date')
        }),
        ('Processing Status', {
            'fields': (
                'status', 'processing_started_at', 'processing_completed_at',
                'processed_records_count', 'error_message'
            )
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )

    def file_name(self, obj):
        """Display just the filename"""
        if obj.file:
            return obj.file.name.split('/')[-1]
        return '-'
    file_name.short_description = 'File Name'

    def save_model(self, request, obj, form, change):
        """Override save to trigger automatic processing for new uploads"""
        # Call the parent save method first
        super().save_model(request, obj, form, change)

        # Only trigger processing for new uploads (not updates)
        if not change:
            # Set the created_by field if not already set
            if not obj.created_by:
                obj.created_by = request.user
                obj.save(update_fields=['created_by'])

            # Trigger automatic processing
            from logims.data_imports.processors.factory import ProcessorFactory
            from logims.data_imports.tasks import process_excel_file

            if ProcessorFactory.is_processor_available(obj.company.code):
                # Start processing asynchronously
                process_excel_file.delay(obj.id)
            else:
                # Mark as failed if no processor is available
                obj.mark_processing_failed(
                    f"No processor available for company '{obj.company.name}'"
                )

    def status_badge(self, obj):
        """Display status as a colored badge"""
        colors = {
            'pending': 'orange',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('company', 'created_by')


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'company_name', 'driver_name', 'driver_uuid', 'uniqueness_key',
        'total_revenue', 'payouts', 'total_deductions', 'final_net_earnings', 'created_at'
    ]
    list_filter = ['file_upload__company', 'file_upload__from_date', 'created_at']
    search_fields = [
        'driver_first_name', 'driver_last_name', 'driver_uuid',
        'file_upload__company__name'
    ]
    readonly_fields = ['id', 'total_deductions', 'tax_deduction', 'agency_share_deduction', 'insurance_deduction', 'final_net_earnings', 'created_at', 'updated_at']

    fieldsets = (
        ('Driver Information', {
            'fields': ('driver_uuid', 'driver_first_name', 'driver_last_name')
        }),
        ('Revenue Data', {
            'fields': (
                'total_revenue', 'net_fare', 'promotions', 'refunds_and_fees',
                'payouts', 'bank_transfer', 'cash_collected'
            )
        }),
        ('Taxes and Tips', {
            'fields': ('fare_tax', 'tips', 'taxes', 'other_revenue')
        }),
        ('Calculated Fields', {
            'fields': ('final_net_earnings',)
        }),
        ('Deductions', {
            'fields': ('total_deductions', 'tax_deduction', 'agency_share_deduction', 'insurance_deduction')
        }),
        ('Metadata', {
            'fields': ('file_upload', 'created_at', 'updated_at')
        }),
    )

    def company_name(self, obj):
        """Display company name"""
        return obj.file_upload.company.name
    company_name.short_description = 'Company'

    def driver_name(self, obj):
        """Display full driver name"""
        return f"{obj.driver_first_name} {obj.driver_last_name}"
    driver_name.short_description = 'Driver'

    def uniqueness_key(self, obj):
        """Display uniqueness key for this payment record"""
        return obj.get_uniqueness_key()
    uniqueness_key.short_description = 'Uniqueness Key'

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('file_upload__company')


@admin.register(TripRecord)
class TripRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'company_name', 'trip_uuid', 'driver_name', 'driver_uuid',
        'trip_status', 'fare_amount', 'trip_distance', 'order_time', 'created_at'
    ]
    list_filter = [
        'file_upload__company', 'trip_status', 'service_type',
        'file_upload__from_date', 'created_at'
    ]
    search_fields = [
        'trip_uuid', 'driver_first_name', 'driver_last_name', 'driver_uuid',
        'pickup_address', 'destination_address', 'file_upload__company__name'
    ]
    readonly_fields = [
        'id', 'trip_duration_minutes', 'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Trip Information', {
            'fields': ('trip_uuid', 'driver_uuid', 'driver_first_name', 'driver_last_name')
        }),
        ('Vehicle Information', {
            'fields': ('vehicle_uuid', 'license_plate', 'service_type')
        }),
        ('Timing', {
            'fields': (
                'order_time', 'arrival_time', 'order_submitted_time',
                'trip_start_time', 'trip_duration_minutes'
            )
        }),
        ('Location', {
            'fields': (
                'pickup_address', 'destination_address',
                'vehicle_location_at_assignment'
            )
        }),
        ('Trip Details', {
            'fields': ('trip_distance', 'trip_status', 'fare_amount')
        }),
        ('Metadata', {
            'fields': ('file_upload', 'id', 'created_at', 'updated_at')
        }),
    )

    def company_name(self, obj):
        """Display company name"""
        return obj.file_upload.company.name
    company_name.short_description = 'Company'

    def driver_name(self, obj):
        """Display full driver name"""
        return f"{obj.driver_first_name} {obj.driver_last_name}"
    driver_name.short_description = 'Driver'

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('file_upload__company')
