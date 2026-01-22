"""
Mixins for FileUpload ViewSet custom actions.
"""
import logging
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema

from ..models import FileUpload, FileType, ProcessingStatus

logger = logging.getLogger(__name__)


class FileUploadStatsMixin:
    """Mixin for file upload statistics actions"""

    @extend_schema(
        summary="Get file upload statistics",
        description="Returns counts by status and file type"
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Basic stats: counts by status and file_type"""
        logger.debug(f"File upload stats requested | user={request.user.username}")

        qs = self.filter_queryset(self.get_queryset())
        by_status = qs.values('status').annotate(count=Count('id')).order_by()
        by_type = qs.values('file_type').annotate(count=Count('id')).order_by()

        return Response({
            'by_status': list(by_status),
            'by_type': list(by_type),
            'total': qs.count(),
        })
