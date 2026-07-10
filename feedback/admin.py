from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('category', 'short_message', 'email', 'device', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('message', 'email', 'device')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    @admin.display(description='message')
    def short_message(self, obj):
        return (obj.message[:70] + '…') if len(obj.message) > 70 else obj.message
