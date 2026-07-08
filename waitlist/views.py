import json

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Signup


@csrf_exempt
@require_POST
def signup(request):
    """Accepts { "email": "...", "website": "" } and stores the email on the waitlist.

    CSRF-exempt because the site posts cross-origin JSON with no session; the honeypot
    ("website" must be empty) plus email validation are the spam guard.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest('invalid json')

    # Honeypot: real users never fill "website"; bots do. Pretend success so we don't tip them off.
    if (body.get('website') or '').strip():
        return JsonResponse({'ok': True})

    email = (body.get('email') or '').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'ok': False, 'error': 'invalid email'}, status=400)

    Signup.objects.get_or_create(email=email, defaults={'source': 'website'})
    return JsonResponse({'ok': True})
