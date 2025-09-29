from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, OpenApiParameter
from ..models import (
    Driver,
)
from .serializers import (
    DriverSerializer,
    DriverCreateUpdateSerializer,
)

@extend_schema(
    parameters=[
        OpenApiParameter(
            name="company_code", description="Filter drivers by company code", required=False,
            type=str, location=OpenApiParameter.QUERY,
        ),
    ]
)
class DriverViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = (
            Driver.objects
            .select_related("company", "license", "vehicle_license")  # joins instead of N+1 queries
            .prefetch_related("contracts")  # loads contracts in 1 query
        )

        company_code = self.request.query_params.get("company_code")
        if company_code:
            qs = qs.filter(company__code=company_code)

        return qs

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return DriverCreateUpdateSerializer
        return DriverSerializer
