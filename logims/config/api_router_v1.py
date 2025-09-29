from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from logims.users.api.views import UserViewSet
from logims.drivers.api.views import (
    DriverViewSet,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("drivers", DriverViewSet, basename="driver")

app_name = "api"
urlpatterns = router.urls
