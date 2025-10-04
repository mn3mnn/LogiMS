from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from logims.users.api.views import UserViewSet
from logims.drivers.api.views import (
    DriverViewSet,
    DriverContractViewSet,
    DriverLicenseViewSet,
    DriverNationalIDViewSet,
    DriverVehicleLicenseViewSet,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("drivers", DriverViewSet, basename="driver")
router.register(r"contracts", DriverContractViewSet, basename="contract")
router.register(r"licenses", DriverLicenseViewSet, basename="license")
router.register(r"national-ids", DriverNationalIDViewSet, basename="national-id")
router.register(r"vehicle-licenses", DriverVehicleLicenseViewSet, basename="vehicle-license")


app_name = "api"
urlpatterns = router.urls
