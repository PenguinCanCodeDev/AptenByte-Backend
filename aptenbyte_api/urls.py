"""URL routing for the AptenByte backend."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from accounts import views as auth_views
from aiproxy.views import chat, rewrite
from releases.views import version_manifest
from waitlist.views import signup


def health(_request):
    return JsonResponse({"service": "aptenbyte-api", "ok": True})


urlpatterns = [
    path("", health),
    path("admin/", admin.site.urls),
    # Update manifest — served at both paths so the app URL can point at either.
    path("version.json", version_manifest),
    path("aptenbyte/version.json", version_manifest),
    # Auth: email/password + Google sign-in. Returns a bearer token for the app.
    path("auth/config", auth_views.config),
    path("auth/register", auth_views.register),
    path("auth/verify-email", auth_views.verify_email),
    path("auth/resend-verification", auth_views.resend_verification),
    path("auth/login", auth_views.login),
    path("auth/google", auth_views.google),
    path("auth/password/reset", auth_views.password_reset),
    path("auth/password/reset/confirm", auth_views.password_reset_confirm),
    path("auth/logout", auth_views.logout),
    path("auth/me", auth_views.me),
    # AI proxy (matches the app's ProxyLLMProvider baseUrl + "/rewrite" / "/chat").
    path("v1/rewrite", rewrite),
    path("v1/chat", chat),
    # Website waitlist signup.
    path("api/waitlist/", signup),
]
