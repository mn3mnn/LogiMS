import csv
import logging
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
    Supervisor,
)
from .serializers import (
    DriverSerializer,
    DriverCreateUpdateSerializer,
    DriverContractSerializer,
    DriverLicenseSerializer,
    DriverNationalIDSerializer,
    DriverVehicleLicenseSerializer,
    SupervisorSerializer,
)
from ..enums import DriverDocumentsStatus
from logims.contrib.logging_utils import log_api_call, log_model_change, log_error

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Drivers"],
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
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "nid",
        "uuid",
        "supervisor__name",
    ]
    ordering_fields = ["first_name", "last_name", "created_at", "updated_at", "insurance", "supervisor__percentage"]
    ordering = ["updated_at"]  # default ordering

    def get_queryset(self):
        qs = (
            Driver.objects
            .select_related("company", "license", "vehicle_license", "national_id_doc", "supervisor")
            .prefetch_related("contracts")
        )
        company_code = self.request.query_params.get("company_code")
        doc_status = self.request.query_params.get("doc_status")

        filters_applied = []

        if company_code:
            qs = qs.filter(company__code=company_code)
            filters_applied.append(f"company_code={company_code}")

        if doc_status == DriverDocumentsStatus.MISSING.value:
            qs = qs.filter(
                Q(license__isnull=True) |
                Q(vehicle_license__isnull=True) |
                Q(national_id_doc__isnull=True) |
                Q(contracts__isnull=True)
            ).distinct()
            filters_applied.append("doc_status=MISSING")

        elif doc_status == DriverDocumentsStatus.EXPIRED.value:
            qs = qs.filter(
                Q(license__expiry_date__lt=timezone.now().date()) |
                Q(vehicle_license__expiry_date__lt=timezone.now().date()) |
                Q(national_id_doc__expiry_date__lt=timezone.now().date()) |
                Q(contracts__expiry_date__lt=timezone.now().date())
            ).distinct()
            filters_applied.append("doc_status=EXPIRED")

        elif doc_status == DriverDocumentsStatus.VALID.value:
            # Valid documents: all required docs exist and none are expired
            today = timezone.now().date()
            qs = qs.filter(
                # All required documents exist
                license__isnull=False,
                vehicle_license__isnull=False,
                national_id_doc__isnull=False,
                contracts__isnull=False,
                # None are expired
                license__expiry_date__gte=today,
                vehicle_license__expiry_date__gte=today,
                national_id_doc__expiry_date__gte=today,
            ).exclude(
                # Exclude if any contracts are expired
                contracts__expiry_date__lt=today
            ).distinct()
            filters_applied.append("doc_status=VALID")

        if filters_applied:
            try:
                logger.debug(
                    f"Driver queryset filters applied | user={self.request.user.username} | "
                    f"filters=[{', '.join(filters_applied)}]"
                )
            except Exception:
                pass  # Don't break queryset if logging fails

        return qs

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return DriverCreateUpdateSerializer
        return DriverSerializer

    def perform_create(self, serializer):
        """Log driver creation."""
        driver = serializer.save()
        # Utility function is already safe via @_safe_log decorator
        log_model_change(
            action="create",
            model_name="Driver",
            instance_id=driver.id,
            user=self.request.user,
            first_name=driver.first_name,
            last_name=driver.last_name,
            company=driver.company.name if driver.company else None
        )
        # Direct logger call needs protection
        try:
            logger.info(
                f"Driver created | id={driver.id} | name={driver.first_name} {driver.last_name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

    def perform_update(self, serializer):
        """Log driver update."""
        driver = serializer.save()
        # Utility function is already safe via @_safe_log decorator
        log_model_change(
            action="update",
            model_name="Driver",
            instance_id=driver.id,
            user=self.request.user,
            first_name=driver.first_name,
            last_name=driver.last_name
        )
        # Direct logger call needs protection
        try:
            logger.info(
                f"Driver updated | id={driver.id} | name={driver.first_name} {driver.last_name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

    def perform_destroy(self, instance):
        """Log driver deletion."""
        driver_id = instance.id
        driver_name = f"{instance.first_name} {instance.last_name}"

        # Utility function is already safe via @_safe_log decorator
        log_model_change(
            action="delete",
            model_name="Driver",
            instance_id=driver_id,
            user=self.request.user,
            name=driver_name
        )
        # Direct logger call needs protection
        try:
            logger.warning(
                f"Driver deleted | id={driver_id} | name={driver_name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

        instance.delete()

    @extend_schema(
        description="Export drivers as CSV."
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_drivers(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            driver_count = queryset.count()

            # Safe logging
            try:
                logger.info(
                    f"Driver export started | user={request.user.username} | count={driver_count}"
                )
            except Exception:
                pass

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

            # Safe logging
            try:
                logger.info(
                    f"Driver export completed | user={request.user.username} | count={driver_count}"
                )
            except Exception:
                pass

            # Create HTTP response
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="drivers_export_{timezone.now().date()}.csv"'
            return response

        except Exception as e:
            # Utility function is already safe via @_safe_log decorator
            log_error(e, context="Driver export failed", user=request.user.username)
            raise

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

    @extend_schema(tags=["Drivers"], parameters=filter_params)
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


@extend_schema(tags=["Drivers"])
class SupervisorViewSet(viewsets.ModelViewSet):
    queryset = Supervisor.objects.all()
    serializer_class = SupervisorSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]

    @extend_schema(
        description="Export supervisors as CSV."
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_supervisors(self, request):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            supervisor_count = queryset.count()

            # Safe logging
            try:
                logger.info(
                    f"Supervisor export started | user={request.user.username} | count={supervisor_count}"
                )
            except Exception:
                pass

            # Prepare CSV data
            buffer = StringIO()
            writer = csv.writer(buffer)
            writer.writerow([
                "ID", "Name", "Phone", "Percentage", "Created At", "Updated At"
            ])

            for supervisor in queryset:
                writer.writerow([
                    supervisor.id,
                    supervisor.name,
                    supervisor.phone,
                    supervisor.percentage,
                    supervisor.created_at.strftime("%Y-%m-%d %H:%M:%S") if supervisor.created_at else "",
                    supervisor.updated_at.strftime("%Y-%m-%d %H:%M:%S") if supervisor.updated_at else "",
                ])

            # Safe logging
            try:
                logger.info(
                    f"Supervisor export completed | user={request.user.username} | count={supervisor_count}"
                )
            except Exception:
                pass

            # Create HTTP response
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="supervisors_export_{timezone.now().date()}.csv"'
            return response

        except Exception as e:
            log_error(e, context="Supervisor export failed", user=request.user.username)
            raise



