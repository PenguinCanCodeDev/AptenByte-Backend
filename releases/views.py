from django.http import JsonResponse

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
