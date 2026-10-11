import json
import re
from datetime import datetime, timezone as dt_timezone

from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import CrashReport

MAX_BODY = 32 * 1024
MAX_STACK = 12000
FINGERPRINT_RE = re.compile(r'^[0-9a-f]{8,32}$')
# Stack lines are "Class.name" or "    at frame(File.kt:12)" — anything else is dropped, so a
# misbehaving client can't smuggle free text (e.g. typed content) into the database.
STACK_LINE_RE = re.compile(r'^(Caused by: )?[\w$.]+$|^    at [\w$.<>\-]+\([\w$.\- ]*(:\d+)?\)$')


@csrf_exempt
@require_POST
def submit(request):
    """Accepts a crash report from the app:
    { fingerprint, exception, stack, thread, app_version, android, device, at }.

    Unauthenticated by design (crashes can happen before sign-in); bounded by size and strict
    validation of every field.
    """
    if len(request.body) > MAX_BODY:
        return JsonResponse({'ok': False, 'error': 'too large'}, status=413)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest('invalid json')
    if not isinstance(body, dict):
        return HttpResponseBadRequest('invalid json')

    fingerprint = str(body.get('fingerprint') or '').strip().lower()
    exception = str(body.get('exception') or '').strip()
    if not FINGERPRINT_RE.match(fingerprint) or not re.match(r'^[\w$.]{1,200}$', exception):
        return JsonResponse({'ok': False, 'error': 'invalid report'}, status=400)

    stack_lines = [l for l in str(body.get('stack') or '').splitlines() if STACK_LINE_RE.match(l)]
    stack = '\n'.join(stack_lines)[:MAX_STACK]

    crashed_at = None
    at = body.get('at')
    if isinstance(at, (int, float)) and at > 0:
        try:
            crashed_at = datetime.fromtimestamp(at / 1000, tz=dt_timezone.utc)
        except (OverflowError, OSError, ValueError):
            crashed_at = None

    def short(key, n):
        return re.sub(r'[^\w .()\-+/]', '', str(body.get(key) or ''))[:n]

    CrashReport.objects.create(
        fingerprint=fingerprint,
        exception=exception,
        stack=stack,
        thread='main' if body.get('thread') == 'main' else 'background',
        app_version=short('app_version', 40),
        android=short('android', 40),
        device=short('device', 120),
        crashed_at=crashed_at,
    )
    return JsonResponse({'ok': True})
