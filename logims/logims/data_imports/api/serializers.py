from rest_framework import serializers
from django.core.files.uploadedfile import UploadedFile
from ..models import FileUpload, PaymentRecord, TripRecord
from logims.drivers.models import Driver
from logims.drivers.models import Driver
from ..processors.factory import ProcessorFactory


class FileUploadSerializer(serializers.ModelSerializer):
    """Serializer for file upload operations"""

    file = serializers.FileField(required=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)

    class Meta:
        model = FileUpload
        fields = [
            'id', 'company', 'company_name', 'file_type', 'file_type_display',
            'file', 'from_date', 'to_date', 'status', 'status_display',
            'processing_started_at', 'processing_completed_at', 'error_message',
            'processed_records_count', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'company_name', 'status', 'status_display', 'file_type_display',
            'processing_started_at', 'processing_completed_at', 'error_message',
            'processed_records_count', 'created_by', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """Validate file upload data"""
        # Check if processor is available for this company
        if not ProcessorFactory.is_processor_available(data['company'].code):
            raise serializers.ValidationError(
                f"No processor available for company '{data['company'].name}'"
            )

        # Validate date range
        if data['from_date'] > data['to_date']:
            raise serializers.ValidationError(
                "From date cannot be later than to date"
            )

        # Validate file extension
        file = data.get('file')
        if file and not file.name.lower().endswith(('.xlsx', '.xls', '.csv')):
            raise serializers.ValidationError(
                "File must be an Excel or CSV file (.xlsx, .xls, or .csv)"
            )

        return data


class FileUploadListSerializer(serializers.ModelSerializer):
    """Simplified serializer for file upload listing"""

    company_name = serializers.CharField(source='company.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = [
            'id', 'company', 'company_name', 'file_type', 'file_type_display',
            'file_name', 'file_url', 'from_date', 'to_date', 'status', 'status_display',
            'processed_records_count', 'created_at'
        ]

    def get_file_name(self, obj):
        """Get just the filename without path"""
        if obj.file:
            return obj.file.name.split('/')[-1]
        return None

    def get_file_url(self, obj):
        """Absolute or relative URL to the uploaded file"""
        try:
            request = self.context.get('request')
        except Exception:
            request = None
        if obj.file:
            url = obj.file.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None


class PaymentRecordSerializer(serializers.ModelSerializer):
    """Serializer for payment records"""

    driver_name = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='file_upload.company.name', read_only=True)
    driver_id = serializers.SerializerMethodField()
    from_date = serializers.DateField(source='file_upload.from_date', read_only=True)
    to_date = serializers.DateField(source='file_upload.to_date', read_only=True)

    class Meta:
        model = PaymentRecord
        fields = [
            'id', 'file_upload', 'company_name', 'driver_uuid', 'driver_id', 'driver_name',
            'driver_first_name', 'driver_last_name', 'from_date', 'to_date',
            'total_revenue', 'net_fare', 'promotions', 'refunds_and_fees', 'payouts', 'bank_transfer',
            'cash_collected', 'fare_tax', 'tips', 'taxes', 'other_revenue',
            'total_deductions', 'tax_deduction', 'agency_share_deduction',
            'insurance_deduction', 'final_net_earnings',
            'calculation_version', 'calculated_at', 'applied_tax_rate',
            'applied_agency_share_rate', 'applied_insurance_amount',
            'driver_id_at_calculation', 'supervisor_id_at_calculation', 'supervisor_name_at_calculation',
            'created_at'
        ]

    def get_driver_name(self, obj):
        """Get full driver name"""
        return f"{obj.driver_first_name} {obj.driver_last_name}"

    def get_driver_id(self, obj):
        """Resolve internal Driver id by driver FK or driver_uuid if available."""
        # Use driver FK if available (more efficient)
        if obj.driver:
            return obj.driver.id
        # Fallback to lookup by UUID
        if not obj.driver_uuid:
            return None
        driver = Driver.objects.filter(uuid=obj.driver_uuid).only('id').first()
        return driver.id if driver else None


class TripRecordSerializer(serializers.ModelSerializer):
    """Serializer for trip records"""

    driver_name = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='file_upload.company.name', read_only=True)
    driver_id = serializers.SerializerMethodField()
    from_date = serializers.DateField(source='file_upload.from_date', read_only=True)
    to_date = serializers.DateField(source='file_upload.to_date', read_only=True)

    class Meta:
        model = TripRecord
        fields = [
            'id', 'file_upload', 'company_name', 'trip_uuid', 'driver_uuid', 'driver_id',
            'driver_name', 'driver_first_name', 'driver_last_name', 'from_date', 'to_date',
            'vehicle_uuid', 'license_plate', 'service_type', 'order_time', 'arrival_time',
            'pickup_address', 'destination_address', 'trip_distance', 'trip_status',
            'order_submitted_time', 'trip_start_time', 'vehicle_location_at_assignment',
            'fare_amount', 'trip_duration_minutes',
            'calculation_version', 'calculated_at', 'driver_id_at_calculation',
            'supervisor_id_at_calculation', 'supervisor_name_at_calculation',
            'created_at'
        ]

    def get_driver_name(self, obj):
        """Get full driver name"""
        return f"{obj.driver_first_name} {obj.driver_last_name}"

    def get_driver_id(self, obj):
        """Resolve internal Driver id by driver FK or driver_uuid if available."""
        # Use driver FK if available (more efficient)
        if obj.driver:
            return obj.driver.id
        # Fallback to lookup by UUID
        if not obj.driver_uuid:
            return None
        driver = Driver.objects.filter(uuid=obj.driver_uuid).only('id').first()
        return driver.id if driver else None


class PaymentRecordAggregatedSerializer(serializers.Serializer):
    """Serializer for aggregated payment records with flexible grouping"""

    # Driver fields (optional, present when grouped by driver)
    driver_id = serializers.IntegerField(allow_null=True, required=False)
    driver_uuid = serializers.CharField(allow_blank=True, required=False)
    driver_first_name = serializers.CharField(allow_blank=True, required=False)
    driver_last_name = serializers.CharField(allow_blank=True, required=False)
    driver_name = serializers.CharField(allow_blank=True, required=False)

    # Supervisor fields (optional, present when grouped by supervisor)
    supervisor_id_at_calculation = serializers.IntegerField(allow_null=True, required=False)
    supervisor_name_at_calculation = serializers.CharField(allow_blank=True, required=False)
    driver_count = serializers.IntegerField(allow_null=True, required=False)  # For supervisor-level

    # Company fields (optional, present when grouped by company)
    company_id = serializers.IntegerField(allow_null=True, required=False)
    company_name = serializers.CharField(allow_blank=True, required=False)
    company_code = serializers.CharField(allow_blank=True, required=False)

    # Period fields (optional, present when grouped by period)
    file_upload = serializers.IntegerField(allow_null=True, required=False)
    from_date = serializers.DateField(allow_null=True, required=False)
    to_date = serializers.DateField(allow_null=True, required=False)

    # Aggregated values
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_deductions = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    agency_share_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    insurance_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_net_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    payouts = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, required=False)
    record_count = serializers.IntegerField()


class TripRecordAggregatedSerializer(serializers.Serializer):
    """Serializer for aggregated trip records with flexible grouping"""

    # Driver fields (optional, present when grouped by driver)
    driver_id = serializers.IntegerField(allow_null=True, required=False)
    driver_uuid = serializers.CharField(allow_blank=True, required=False)
    driver_first_name = serializers.CharField(allow_blank=True, required=False)
    driver_last_name = serializers.CharField(allow_blank=True, required=False)
    driver_name = serializers.CharField(allow_blank=True, required=False)

    # Supervisor fields (optional, present when grouped by supervisor)
    supervisor_id_at_calculation = serializers.IntegerField(allow_null=True, required=False)
    supervisor_name_at_calculation = serializers.CharField(allow_blank=True, required=False)
    driver_count = serializers.IntegerField(allow_null=True, required=False)  # For supervisor-level

    # Company fields (optional, present when grouped by company)
    company_id = serializers.IntegerField(allow_null=True, required=False)
    company_name = serializers.CharField(allow_blank=True, required=False)
    company_code = serializers.CharField(allow_blank=True, required=False)

    # Period fields (optional, present when grouped by period)
    file_upload = serializers.IntegerField(allow_null=True, required=False)
    from_date = serializers.DateField(allow_null=True, required=False)
    to_date = serializers.DateField(allow_null=True, required=False)

    # Status field (optional, present when grouped by status)
    trip_status = serializers.CharField(allow_null=True, required=False)

    # Aggregated values
    total_fare = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_distance = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)
    trip_count = serializers.IntegerField()
    avg_duration = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)


class FileUploadDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for file upload with related records"""

    company_name = serializers.CharField(source='company.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_name = serializers.SerializerMethodField()
    payment_records = PaymentRecordSerializer(many=True, read_only=True)
    trip_records = TripRecordSerializer(many=True, read_only=True)

    class Meta:
        model = FileUpload
        fields = [
            'id', 'company', 'company_name', 'file_type', 'file_type_display',
            'file', 'file_name', 'from_date', 'to_date', 'status', 'status_display',
            'processing_started_at', 'processing_completed_at', 'error_message',
            'processed_records_count', 'created_by', 'created_at', 'updated_at',
            'payment_records', 'trip_records'
        ]

    def get_file_name(self, obj):
        """Get just the filename without path"""
        if obj.file:
            return obj.file.name.split('/')[-1]
        return None
