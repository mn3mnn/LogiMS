import logging
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from drf_spectacular.utils import extend_schema

from logims.users.models import User

from .serializers import UserSerializer
from logims.contrib.logging_utils import log_user_action, log_model_change

logger = logging.getLogger(__name__)


@extend_schema(tags=["Users"])
class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "username"

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, int)
        return self.queryset.filter(id=self.request.user.id)

    def perform_update(self, serializer):
        """Log user profile update."""
        user = serializer.save()
        # Utility function is already safe via @_safe_log decorator
        log_model_change(
            action="update",
            model_name="User",
            instance_id=user.id,
            user=self.request.user,
            username=user.username
        )
        # Direct logger call needs protection
        try:
            logger.info(
                f"User profile updated | id={user.id} | username={user.username}"
            )
        except Exception:
            pass

    @action(detail=False)
    def me(self, request):
        # Safe logging
        try:
            logger.debug(f"User profile accessed | user={request.user.username}")
        except Exception:
            pass
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


@extend_schema(tags=["Authentication"])
class LogoutView(APIView):
    """
    Logout endpoint — invalidates the user's authentication token.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        username = request.user.username
        user_id = request.user.id

        # Delete the token to force re-authentication
        try:
            request.user.auth_token.delete()

            # Utility function is already safe via @_safe_log decorator
            log_user_action(
                action="logout",
                user=request.user,
                success=True
            )
            # Direct logger call needs protection
            try:
                logger.info(f"User logged out | user={username} | id={user_id}")
            except Exception:
                pass

        except (AttributeError, Token.DoesNotExist):
            # Safe logging
            try:
                logger.warning(
                    f"Logout failed - token not found | user={username} | id={user_id}"
                )
            except Exception:
                pass
            return Response({"detail": "Token not found or already deleted."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)

