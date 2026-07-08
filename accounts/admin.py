from django.contrib import admin

from .models import AuthToken, VerificationCode


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "last_used_at")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("key", "created_at", "last_used_at")


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "attempts", "created_at", "expires_at")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("code_hash", "created_at", "expires_at")
