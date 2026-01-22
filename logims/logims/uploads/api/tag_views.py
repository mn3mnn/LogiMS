"""
Tag API views for core module.
"""
import logging
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from logims.uploads.models import Tag
from .serializers import TagSerializer
from logims.contrib.logging_utils import log_model_change

logger = logging.getLogger(__name__)


@extend_schema(tags=["Uploads"])
class TagViewSet(viewsets.ModelViewSet):
    """ViewSet for managing document tags"""

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        """Filter tags based on query parameters"""
        queryset = super().get_queryset()

        # Filter by predefined status
        is_predefined = self.request.query_params.get('is_predefined')
        if is_predefined is not None:
            queryset = queryset.filter(is_predefined=is_predefined.lower() == 'true')

        return queryset

    def perform_create(self, serializer):
        """Create a new tag (custom tags are not predefined by default)"""
        tag = serializer.save(is_predefined=False)

        try:
            logger.info(
                f"Tag created | id={tag.id} | name={tag.name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

        log_model_change(
            action="create",
            model_name="Tag",
            instance_id=tag.id,
            user=self.request.user,
            name=tag.name
        )

    def perform_update(self, serializer):
        """Update a tag"""
        tag = serializer.save()

        try:
            logger.info(
                f"Tag updated | id={tag.id} | name={tag.name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

        log_model_change(
            action="update",
            model_name="Tag",
            instance_id=tag.id,
            user=self.request.user,
            name=tag.name
        )

    def perform_destroy(self, instance):
        """Delete a tag"""
        tag_id = instance.id
        tag_name = instance.name

        try:
            logger.info(
                f"Tag deleted | id={tag_id} | name={tag_name} | "
                f"user={self.request.user.username}"
            )
        except Exception:
            pass

        log_model_change(
            action="delete",
            model_name="Tag",
            instance_id=tag_id,
            user=self.request.user,
            name=tag_name
        )

        instance.delete()
