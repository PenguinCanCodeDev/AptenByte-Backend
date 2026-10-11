from django.contrib import admin

from .models import CrashReport


@admin.register(CrashReport)
class CrashReportAdmin(admin.ModelAdmin):
    list_display = ('exception', 'fingerprint', 'app_version', 'device', 'thread', 'created_at')
    list_filter = ('app_version', 'thread', 'created_at')
    search_fields = ('exception', 'fingerprint', 'stack', 'device')
    readonly_fields = [f.name for f in CrashReport._meta.fields]
    ordering = ('-created_at',)
