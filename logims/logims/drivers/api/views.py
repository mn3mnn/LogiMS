import csv
from io import StringIO
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework import viewsets, filters
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.utils import timezone
from django.db.models import Q

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
from ..enums import DriverDocumentsStatus


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
        OpenApiParameter(
            name="doc_status", description="Filter by driver documents status", required=False,
            enum=[status.value for status in DriverDocumentsStatus], type=str, location=OpenApiParameter.QUERY,
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

        doc_status = self.request.query_params.get("doc_status")

        if doc_status == DriverDocumentsStatus.MISSING_DOCS.value:
            qs = qs.filter(
                Q(license__isnull=True) |
                Q(vehicle_license__isnull=True) |
                Q(national_id_doc__isnull=True) |
                Q(contracts__isnull=True)
            ).distinct()

        elif doc_status == DriverDocumentsStatus.EXPIRED_DOCS.value:
            qs = qs.filter(
                Q(license__expiry_date__lt=timezone.now().date()) |
                Q(vehicle_license__expiry_date__lt=timezone.now().date()) |
                Q(national_id_doc__expiry_date__lt=timezone.now().date()) |
                Q(contracts__expiry_date__lt=timezone.now().date())
            ).distinct()

        return qs

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return DriverCreateUpdateSerializer
        return DriverSerializer

    @extend_schema(
        description="Export drivers as CSV."
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_drivers(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        # Prepare CSV data
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "ID", "First Name", "Last Name", "Phone", "NID", "Company",
            "License Expiry", "Vehicle License Expiry", "National ID Expiry",
            "Contracts Count"
        ])

        for driver in queryset:
            writer.writerow([
                driver.id,
                driver.first_name,
                driver.last_name,
                driver.phone_number,
                driver.nid or "",
                driver.company.name if driver.company else "",
                driver.license.expiry_date if getattr(driver, "license", None) else "",
                driver.vehicle_license.expiry_date if getattr(driver, "vehicle_license", None) else "",
                driver.national_id_doc.expiry_date if getattr(driver, "national_id_doc", None) else "",
                driver.contracts.count(),
            ])

        # Create HTTP response
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="drivers_export_{timezone.now().date()}.csv"'
        return response

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



