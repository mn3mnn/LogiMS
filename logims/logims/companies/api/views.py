from rest_framework import viewsets, filters
from drf_spectacular.utils import extend_schema
from ..models import Company
from .serializers import CompanySerializer


@extend_schema(tags=["Companies"])
class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for listing or retrieving companies.
    """
    queryset = Company.objects.all().order_by("name")
    serializer_class = CompanySerializer
    filter_backends = []

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(is_active=True)
        return qs
