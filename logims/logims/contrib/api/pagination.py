"""
Shared pagination classes for DRF viewsets.
"""
from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class used across all record viewsets."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
