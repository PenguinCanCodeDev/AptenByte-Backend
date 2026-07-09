"""Bearer-token authentication for the API: a decorator to gate views and a
helper to verify Google ID tokens sent by the mobile app.
"""

from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from .models import AuthToken, ClientInfo


def _bearer_key(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return None


def _record_app_version(user, version):
    """Upsert the user's last-seen app version (from the X-App-Version header)."""
    version = (version or "").strip()[:40]
    if not version:
        return
    try:
        ClientInfo.objects.update_or_create(user=user, defaults={"app_version": version})
    except Exception:
        pass  # bookkeeping must never break an authenticated request


def require_user(view):
    """Reject the request with 401 unless it carries a valid bearer token.

    On success, sets ``request.auth_user`` and ``request.auth_token``.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        key = _bearer_key(request)
        token = (
            AuthToken.objects.select_related("user").filter(key=key).first()
            if key
            else None
        )
        if token is None or not token.user.is_active:
            return JsonResponse({"error": "authentication required"}, status=401)
        AuthToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        request.auth_user = token.user
        request.auth_token = token
        _record_app_version(token.user, request.META.get("HTTP_X_APP_VERSION", ""))
        return view(request, *args, **kwargs)

    return wrapper


def verify_google_id_token(id_token_str):
    """Return the verified, lowercased email for a Google ID token, else None.

    Verifies Google's signature/issuer/expiry, then checks the token's audience
    is one of our configured OAuth client IDs (Android / iOS / web).
    """
    if not id_token_str:
        return None

    # Imported lazily so the rest of the app runs without google-auth installed.
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        info = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request()
        )
    except Exception:
        return None

    if info.get("aud") not in settings.GOOGLE_OAUTH_CLIENT_IDS:
        return None
    if not info.get("email") or not info.get("email_verified"):
        return None
    return info["email"].lower()
