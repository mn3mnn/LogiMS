from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter
from django.urls import path

from logims.users.api.views import UserViewSet, LogoutView
from logims.drivers.api.views import (
    DriverViewSet,
    DriverContractViewSet,
    DriverLicenseViewSet,
    DriverNationalIDViewSet,
    DriverVehicleLicenseViewSet,
    SupervisorViewSet,
)

from logims.companies.api.views import CompanyViewSet
from logims.uploads.api.views import FileUploadViewSet
from logims.uploads.api.tag_views import TagViewSet
from logims.payroll.api.views import PaymentRecordViewSet
from logims.trips.api.views import TripRecordViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("drivers", DriverViewSet, basename="driver")
router.register(r"supervisors", SupervisorViewSet, basename="supervisor")
router.register(r"contracts", DriverContractViewSet, basename="contract")
router.register(r"licenses", DriverLicenseViewSet, basename="license")
router.register(r"national-ids", DriverNationalIDViewSet, basename="national-id")
router.register(r"vehicle-licenses", DriverVehicleLicenseViewSet, basename="vehicle-license")
router.register(r"companies", CompanyViewSet, basename="companies")

router.register(r"uploads", FileUploadViewSet, basename="file-upload")
router.register(r"tags", TagViewSet, basename="tag")
router.register(r"payroll/records", PaymentRecordViewSet, basename="payment-record")
router.register(r"trips/records", TripRecordViewSet, basename="trip-record")


app_name = "api"
urlpatterns = [
    *router.urls,
    path("auth/logout/", LogoutView.as_view(), name="logout")
]
