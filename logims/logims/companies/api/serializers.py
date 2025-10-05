from rest_framework import serializers
from ..models import Company


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "code", "name", "is_active", "logo", "created_at", "updated_at"]

