from django.contrib import admin
from .models import Company

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "logo", "created_at")
    search_fields = ("code", "name")
    ordering = ("code",)
