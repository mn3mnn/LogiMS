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
)

from logims.companies.api.views import CompanyViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("drivers", DriverViewSet, basename="driver")
router.register(r"contracts", DriverContractViewSet, basename="contract")
router.register(r"licenses", DriverLicenseViewSet, basename="license")
router.register(r"national-ids", DriverNationalIDViewSet, basename="national-id")
router.register(r"vehicle-licenses", DriverVehicleLicenseViewSet, basename="vehicle-license")
router.register(r"companies", CompanyViewSet, basename="companies")


app_name = "api"
urlpatterns = [
    *router.urls,
    path("auth/logout/", LogoutView.as_view(), name="logout")
]
