"""
Filters for trip records.
"""
from django_filters import rest_framework as filters
from django.db.models import Q
from ..models import TripRecord


class TripRecordFilterSet(filters.FilterSet):
    """Filters for TripRecord with company and file upload date range."""

    from_date = filters.DateFilter(method="filter_period_records")
    to_date = filters.DateFilter(method="filter_period_records")
    company = filters.NumberFilter(field_name="file_upload__metadata__company")
    company_code = filters.CharFilter(field_name="file_upload__metadata__company__code", lookup_expr="exact")
    driver_id = filters.NumberFilter(field_name="driver_id_at_calculation", lookup_expr="exact")
    supervisor_id = filters.NumberFilter(field_name="supervisor_id_at_calculation", lookup_expr="exact")
    file_upload = filters.NumberFilter(field_name="file_upload", lookup_expr="exact")

    class Meta:
        model = TripRecord
        fields = {
            "driver_uuid": ["exact"],
            "trip_status": ["exact"],
            "service_type": ["exact"],
        }

    def filter_period_records(self, queryset, name, value):
        """Filter by period overlap using metadata"""
        start = self.data.get('from_date')
        end = self.data.get('to_date')

        if start and end:
            return queryset.filter(
                Q(file_upload__metadata__from_date__lte=end) &
                Q(file_upload__metadata__to_date__gte=start)
            )

        if start and not end:
            return queryset.filter(file_upload__metadata__to_date__gte=start)

        if end and not start:
            return queryset.filter(file_upload__metadata__from_date__lte=end)

        return queryset
