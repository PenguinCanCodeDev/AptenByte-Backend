import time
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from waitlist.models import Signup

from .models import Release


def version_manifest(request):
    """
    The update manifest the app's UpdateChecker fetches. Shape:
        { "versionCode": 2, "versionName": "1.0.0-beta.2", "url": "...", "notes": "..." }
    Returns versionCode 0 when nothing is published (the app then shows no update).
    """
    rel = Release.objects.filter(is_current=True).first() or Release.objects.first()
    data = {
        "versionCode": rel.version_code if rel else 0,
        "versionName": rel.version_name if rel else "",
        "url": rel.url if rel else "",
        "notes": rel.notes if rel else "",
    }
    resp = JsonResponse(data)
    resp["Cache-Control"] = "public, max-age=300"
    return resp


# GitHub download counts are cached briefly so the dashboard doesn't hit the API
# (unauthenticated: 60 req/hr) on every load.
_GH_CACHE = {"at": 0.0, "data": None}
_GH_TTL = 300  # seconds


def _github_downloads():
    now = time.time()
    cached = _GH_CACHE["data"]
    if cached is not None and now - _GH_CACHE["at"] < _GH_TTL:
        return cached
    result = {"total": 0, "by_release": [], "error": None}
    headers = {"Accept": "application/vnd.github+json"}
    # Optional: a token lifts the 60/hr unauthenticated limit to 5000/hr.
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{settings.RELEASES_REPO}/releases",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            for rel in r.json():
                count = sum(a.get("download_count", 0) for a in rel.get("assets", []))
                result["by_release"].append({"tag": rel.get("tag_name"), "count": count})
                result["total"] += count
        else:
            result["error"] = f"github {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:120]
    # Cache good data; on error keep serving the last good data if we have it.
    if result["error"] is None or cached is None:
        _GH_CACHE["at"], _GH_CACHE["data"] = now, result
    return _GH_CACHE["data"]


def stats(request):
    """Private admin dashboard data: APK downloads + signed-in users + waitlist.

    Gated by ADMIN_STATS_TOKEN, sent as ``Authorization: Bearer <token>`` (or the
    ``X-Admin-Token`` header). Returns 503 until the token is configured.
    """
    token = settings.ADMIN_STATS_TOKEN
    if not token:
        return JsonResponse({"error": "stats not configured"}, status=503)
    header = request.META.get("HTTP_AUTHORIZATION", "")
    provided = header[7:].strip() if header.startswith("Bearer ") else request.META.get("HTTP_X_ADMIN_TOKEN", "")
    if not provided or not constant_time_compare(provided, token):
        return JsonResponse({"error": "unauthorized"}, status=401)

    User = get_user_model()
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    users = {
        "total": User.objects.count(),
        "verified": User.objects.filter(is_active=True).count(),
        # Google sign-in accounts have an unusable password (Django stores "!...").
        "google": User.objects.filter(password__startswith="!").count(),
        "new_7d": User.objects.filter(date_joined__gte=week_ago).count(),
    }
    waitlist = {
        "total": Signup.objects.count(),
        "new_7d": Signup.objects.filter(created_at__gte=week_ago).count(),
    }
    resp = JsonResponse({
        "downloads": _github_downloads(),
        "users": users,
        "waitlist": waitlist,
        "generated_at": now.isoformat(),
    })
    resp["Cache-Control"] = "no-store"
    return resp
