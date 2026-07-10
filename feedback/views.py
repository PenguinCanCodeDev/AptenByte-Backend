import json

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Feedback

VALID_CATEGORIES = {c[0] for c in Feedback.CATEGORY_CHOICES}
MAX_MESSAGE = 4000


@csrf_exempt
@require_POST
def submit(request):
    """Accepts { message, category?, email?, device?, website? } from the site.

    CSRF-exempt because the site posts cross-origin JSON with no session; the honeypot
    ("website" must be empty) plus a length check are the spam guard. email/device are optional.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest('invalid json')

    # Honeypot: real users never fill "website"; bots do. Pretend success so we don't tip them off.
    if (body.get('website') or '').strip():
        return JsonResponse({'ok': True})

    message = (body.get('message') or '').strip()
    if len(message) < 3:
        return JsonResponse({'ok': False, 'error': 'please write a little more'}, status=400)
    message = message[:MAX_MESSAGE]

    category = (body.get('category') or 'suggestion').strip().lower()
    if category not in VALID_CATEGORIES:
        category = 'other'

    email = (body.get('email') or '').strip().lower()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'ok': False, 'error': 'invalid email'}, status=400)

    device = (body.get('device') or '').strip()[:120]

    Feedback.objects.create(
        category=category, message=message, email=email, device=device, source='website'
    )
    return JsonResponse({'ok': True})
