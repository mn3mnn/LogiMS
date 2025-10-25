from django_filters import rest_framework as filters
from django.db.models import Q
from ..models import FileUpload, PaymentRecord


class FileUploadFilterSet(filters.FilterSet):
    """Filters for FileUpload list with date range support."""

    # Period-overlap filters (both map to same method)
    from_date = filters.DateFilter(method="filter_period")
    to_date = filters.DateFilter(method="filter_period")
    company_code = filters.CharFilter(field_name="company__code", lookup_expr="exact")

    class Meta:
        model = FileUpload
        fields = {
            "id": ["exact"],
            "company": ["exact"],
            "file_type": ["exact"],
            "status": ["exact"],
            # from_date/to_date added above as custom params
        }

    def filter_period(self, queryset, name, value):
        start = self.data.get('from_date')
        end = self.data.get('to_date')

        # Both bounds provided: overlap if [from_date, to_date] intersects [start, end]
        if start and end:
            return queryset.filter(
                Q(from_date__lte=end) & Q(to_date__gte=start)
            )

        # Only start provided: items that end on/after start
        if start and not end:
            return queryset.filter(to_date__gte=start)

        # Only end provided: items that start on/before end
        if end and not start:
            return queryset.filter(from_date__lte=end)

        return queryset


class PaymentRecordFilterSet(filters.FilterSet):
    """Filters for PaymentRecord with company and file upload date range."""

    from_date = filters.DateFilter(field_name="file_upload__from_date", lookup_expr="gte")
    # Period-overlap filters applied to related FileUpload
    from_date = filters.DateFilter(method="filter_period_records")
    to_date = filters.DateFilter(method="filter_period_records")
    company = filters.NumberFilter(field_name="file_upload__company")
    company_code = filters.CharFilter(field_name="file_upload__company__code", lookup_expr="exact")

    class Meta:
        model = PaymentRecord
        fields = {
            "driver_uuid": ["exact"],
            # company/from_date/to_date are defined above
        }

    def filter_period_records(self, queryset, name, value):
        start = self.data.get('from_date')
        end = self.data.get('to_date')

        if start and end:
            return queryset.filter(
                Q(file_upload__from_date__lte=end) & Q(file_upload__to_date__gte=start)
            )

        if start and not end:
            return queryset.filter(file_upload__to_date__gte=start)

        if end and not start:
            return queryset.filter(file_upload__from_date__lte=end)

        return queryset


