"""
Enhanced filters for unified FileUpload API.
"""
from django_filters import rest_framework as filters
from django.db.models import Q

from logims.uploads.models import FileUpload, FileType, ProcessingStatus


class FileUploadFilterSet(filters.FilterSet):
    """
    Enhanced filters for FileUpload list with optimized queries using annotations.
    """

    # Direct filters
    file_type = filters.MultipleChoiceFilter(
        choices=FileType.choices,
        help_text="Filter by one or more file types"
    )
    status = filters.MultipleChoiceFilter(
        choices=ProcessingStatus.choices,
        help_text="Filter by one or more processing statuses"
    )

    # Date range filters (using annotations)
    from_date = filters.DateFilter(
        method='filter_date_range',
        help_text="Filter uploads with from_date >= value"
    )
    to_date = filters.DateFilter(
        method='filter_date_range',
        help_text="Filter uploads with to_date <= value"
    )

    # Company filters (using annotations)
    company = filters.NumberFilter(
        method='filter_company',
        help_text="Filter by company ID"
    )
    company_code = filters.CharFilter(
        method='filter_company_code',
        help_text="Filter by company code"
    )

    # Date range for created_at
    created_after = filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateFilter(field_name='created_at', lookup_expr='lte')

    # Status combinations
    is_processed = filters.BooleanFilter(
        method='filter_is_processed',
        help_text="Filter by whether file has been processed (completed or failed)"
    )
    is_pending = filters.BooleanFilter(
        method='filter_is_pending',
        help_text="Filter by pending status (pending or processing)"
    )

    class Meta:
        model = FileUpload
        fields = {
            "id": ["exact", "in"],
            "created_at": ["exact", "gte", "lte"],
        }

    def filter_date_range(self, queryset, name, value):
        """
        Filter by period overlap using metadata.
        """
        start = self.data.get('from_date')
        end = self.data.get('to_date')

        if start and end:
            # Filter where period overlaps: from_date <= end AND to_date >= start
            return queryset.filter(
                Q(metadata__from_date__lte=end) & Q(metadata__to_date__gte=start)
            )

        if start and not end:
            # Filter where to_date >= start
            return queryset.filter(metadata__to_date__gte=start)

        if end and not start:
            # Filter where from_date <= end
            return queryset.filter(metadata__from_date__lte=end)

        return queryset

    def filter_company(self, queryset, name, value):
        """Filter by company using direct field path"""
        return queryset.filter(metadata__company_id=value)

    def filter_company_code(self, queryset, name, value):
        """Filter by company code using direct field path"""
        return queryset.filter(metadata__company__code=value)

    def filter_is_processed(self, queryset, name, value):
        """Filter by whether file has been processed"""
        if value:
            return queryset.filter(status__in=[ProcessingStatus.COMPLETED, ProcessingStatus.FAILED])
        else:
            return queryset.exclude(status__in=[ProcessingStatus.COMPLETED, ProcessingStatus.FAILED])

    def filter_is_pending(self, queryset, name, value):
        """Filter by pending status"""
        if value:
            return queryset.filter(status__in=[ProcessingStatus.PENDING, ProcessingStatus.PROCESSING])
        else:
            return queryset.exclude(status__in=[ProcessingStatus.PENDING, ProcessingStatus.PROCESSING])

    @property
    def qs(self):
        """
        Override queryset to optimize queries with select_related.
        Uses unified metadata model with select_related for better performance.
        """
        queryset = super().qs

        # Use select_related for metadata to avoid N+1 queries
        queryset = queryset.select_related('metadata', 'metadata__company')

        return queryset
