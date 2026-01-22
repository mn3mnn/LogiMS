"""
Serializers for payroll API.
"""
from rest_framework import serializers
from ..models import PaymentRecord


class PaymentRecordSerializer(serializers.ModelSerializer):
    """Serializer for payment records"""

    driver_name = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    driver_id = serializers.SerializerMethodField()
    from_date = serializers.SerializerMethodField()
    to_date = serializers.SerializerMethodField()

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

    def get_company_name(self, obj):
        """Get company name from metadata - optimized to avoid N+1 queries"""
        # Use select_related from queryset - metadata should already be loaded
        if hasattr(obj, 'file_upload') and obj.file_upload:
            metadata = getattr(obj.file_upload, 'metadata', None)
            if metadata and hasattr(metadata, 'company') and metadata.company:
                return metadata.company.name
        return None

    def get_driver_id(self, obj):
        """
        Resolve internal Driver id - handles deleted/re-added drivers.

        Priority:
        1. Current driver FK (if exists) - most reliable
        2. Current driver by UUID (from annotation) - handles deleted/re-added case
        3. driver_id_at_calculation - historical snapshot (may be stale if driver was deleted/re-added)
        """
        # First check if driver FK is loaded and exists (most reliable)
        if hasattr(obj, 'driver') and obj.driver:
            return obj.driver.id

        # Check annotated current driver_id by UUID (handles deleted/re-added drivers)
        # This annotation is added in get_queryset() to avoid N+1 queries
        if hasattr(obj, 'current_driver_id_by_uuid') and obj.current_driver_id_by_uuid:
            return obj.current_driver_id_by_uuid

        # Fall back to calculation snapshot (historical reference, may be stale)
        if obj.driver_id_at_calculation:
            return obj.driver_id_at_calculation

        return None

    def get_from_date(self, obj):
        """Get from_date from metadata - optimized to avoid N+1 queries"""
        if hasattr(obj, 'file_upload') and obj.file_upload:
            metadata = getattr(obj.file_upload, 'metadata', None)
            if metadata:
                return metadata.from_date
        return None

    def get_to_date(self, obj):
        """Get to_date from metadata - optimized to avoid N+1 queries"""
        if hasattr(obj, 'file_upload') and obj.file_upload:
            metadata = getattr(obj.file_upload, 'metadata', None)
            if metadata:
                return metadata.to_date
        return None


class PaymentRecordAggregatedSerializer(serializers.Serializer):
    """Serializer for aggregated payment records"""

    driver_id = serializers.IntegerField(allow_null=True, required=False)
    driver_uuid = serializers.CharField(allow_blank=True, required=False)
    driver_first_name = serializers.CharField(allow_blank=True, required=False)
    driver_last_name = serializers.CharField(allow_blank=True, required=False)
    driver_name = serializers.CharField(allow_blank=True, required=False)
    supervisor_id_at_calculation = serializers.IntegerField(allow_null=True, required=False)
    supervisor_name_at_calculation = serializers.CharField(allow_blank=True, required=False)
    driver_count = serializers.IntegerField(allow_null=True, required=False)
    company_id = serializers.IntegerField(allow_null=True, required=False)
    company_name = serializers.CharField(allow_blank=True, required=False)
    company_code = serializers.CharField(allow_blank=True, required=False)
    file_upload = serializers.IntegerField(allow_null=True, required=False)
    from_date = serializers.DateField(allow_null=True, required=False)
    to_date = serializers.DateField(allow_null=True, required=False)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    tips = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, required=False)
    total_deductions = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    agency_share_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    insurance_deduction = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_net_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    payouts = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True, required=False)
    record_count = serializers.IntegerField()
