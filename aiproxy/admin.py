from django.contrib import admin

from .models import ProviderHealth


@admin.register(ProviderHealth)
class ProviderHealthAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "priority",
        "success_count",
        "failure_count",
        "last_success_at",
        "last_failure_at",
        "last_error",
    )
    ordering = ("priority", "name")
    readonly_fields = ("last_success_at", "last_failure_at", "success_count", "failure_count")
