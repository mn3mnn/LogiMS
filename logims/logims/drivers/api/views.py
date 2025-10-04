from rest_framework import viewsets, filters
from drf_spectacular.utils import extend_schema, OpenApiParameter
from ..models import (
    Driver,
    DriverContract,
    DriverLicense,
    DriverNationalID,
    DriverVehicleLicense,
)
from .serializers import (
    DriverSerializer,
    DriverCreateUpdateSerializer,
    DriverContractSerializer,
    DriverLicenseSerializer,
    DriverNationalIDSerializer,
    DriverVehicleLicenseSerializer,
)

@extend_schema(
    parameters=[
        OpenApiParameter(
            name="company_code", description="Filter drivers by company code", required=False,
            type=str, location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="search", description="Search drivers by name, phone number, national ID number, or uuid", required=False,
            type=str, location=OpenApiParameter.QUERY,
        ),
    ]
)
class DriverViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "first_name",
        "last_name",
        "phone_number",
        "nid",
        "uuid",
    ]

    def get_queryset(self):
        qs = (
            Driver.objects
            .select_related("company", "license", "vehicle_license", "national_id_doc")
            .prefetch_related("contracts")
        )
        company_code = self.request.query_params.get("company_code")
        if company_code:
            qs = qs.filter(company__code=company_code)
        return qs

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return DriverCreateUpdateSerializer
        return DriverSerializer


class BaseDocumentViewSet(viewsets.ModelViewSet):
    """
    Base viewset for all driver document endpoints.
    Provides filtering by driver_id and company_code.
    """

    filter_params = [
        OpenApiParameter(
            name="driver_id", description="Filter by driver ID",
            required=False, type=int, location=OpenApiParameter.QUERY,
        ),
        OpenApiParameter(
            name="company_code", description="Filter by company code",
            required=False, type=str, location=OpenApiParameter.QUERY,
        ),
    ]

    @extend_schema(parameters=filter_params)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = self.queryset.select_related("driver__company")

        driver_id = self.request.query_params.get("driver_id")
        company_code = self.request.query_params.get("company_code")

        if driver_id:
            qs = qs.filter(driver__id=driver_id)
        if company_code:
            qs = qs.filter(driver__company__code=company_code)

        return qs


class DriverContractViewSet(BaseDocumentViewSet):
    queryset = DriverContract.objects.all()
    serializer_class = DriverContractSerializer


class DriverLicenseViewSet(BaseDocumentViewSet):
    queryset = DriverLicense.objects.all()
    serializer_class = DriverLicenseSerializer


class DriverVehicleLicenseViewSet(BaseDocumentViewSet):
    queryset = DriverVehicleLicense.objects.all()
    serializer_class = DriverVehicleLicenseSerializer


class DriverNationalIDViewSet(BaseDocumentViewSet):
    queryset = DriverNationalID.objects.all()
    serializer_class = DriverNationalIDSerializer



