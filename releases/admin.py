from django.contrib import admin

from .models import Release


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = ("version_name", "version_code", "is_current", "created_at")
    list_editable = ("is_current",)
    search_fields = ("version_name",)
