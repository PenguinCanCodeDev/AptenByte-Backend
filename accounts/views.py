"""Auth endpoints for the mobile app: email/password (with verification +
password reset) and Google sign-in.

All return JSON. On success the response includes a bearer ``token`` the app
stores and sends as ``Authorization: Bearer <token>`` on later requests.
Verification/reset use 6-digit codes emailed to the user (see emails.py).
"""

import json

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .auth import require_user, verify_google_id_token
from .emails import send_code
from .models import AuthToken, VerificationCode

User = get_user_model()


def config(request):
    """Public sign-in config the app fetches at launch.

    Returns the Google *Web* client id the app uses as the server client id for
    Credential Manager (its ID token audience). Served from the server so it can
    be set/rotated without shipping a new APK. ``google_web_client_id`` is empty
    until GOOGLE_OAUTH_CLIENT_IDS is configured, which the app reads as "Google
    sign-in not available yet" (BYOK still works).
    """
    ids = settings.GOOGLE_OAUTH_CLIENT_IDS
    web_id = ids[0] if ids else ""
    return JsonResponse({
        "google_web_client_id": web_id,
        "google_sign_in_enabled": bool(web_id),
    })


def _json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return None


def _token_response(user, status=200):
    token = AuthToken.issue(user)
    return JsonResponse({"token": token.key, "email": user.email}, status=status)


@csrf_exempt
@require_POST
def register(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return JsonResponse({"error": "email and password are required"}, status=400)
    # We key the account on email (stored as username so the default User works).
    if User.objects.filter(username=email).exists():
        return JsonResponse({"error": "an account with this email already exists"}, status=409)
    try:
        validate_password(password)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages}, status=400)
    # Inactive until the email is verified; no usable token is issued yet.
    user = User.objects.create_user(username=email, email=email, password=password, is_active=False)
    _, code = VerificationCode.issue(user, VerificationCode.PURPOSE_VERIFY)
    send_code(user, code, VerificationCode.PURPOSE_VERIFY)
    return JsonResponse({"detail": "verification code sent", "email": email}, status=201)


@csrf_exempt
@require_POST
def verify_email(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    code = data.get("code") or ""
    user = User.objects.filter(username=email).first()
    if user is None or not VerificationCode.redeem(user, VerificationCode.PURPOSE_VERIFY, code):
        return JsonResponse({"error": "invalid or expired code"}, status=400)
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    return _token_response(user)


@csrf_exempt
@require_POST
def resend_verification(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    user = User.objects.filter(username=email, is_active=False).first()
    if user is not None:
        _, code = VerificationCode.issue(user, VerificationCode.PURPOSE_VERIFY)
        send_code(user, code, VerificationCode.PURPOSE_VERIFY)
    # Don't reveal whether the account exists / is unverified.
    return JsonResponse({"detail": "if the account exists and is unverified, a code was sent"})


@csrf_exempt
@require_POST
def login(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = authenticate(username=email, password=password)
    if user is None:
        # Distinguish "unverified" (correct password, inactive) from bad credentials.
        existing = User.objects.filter(username=email).first()
        if existing and not existing.is_active and existing.check_password(password):
            return JsonResponse(
                {"error": "email not verified", "code": "email_not_verified"}, status=403
            )
        return JsonResponse({"error": "invalid email or password"}, status=401)
    return _token_response(user)


@csrf_exempt
@require_POST
def google(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = verify_google_id_token(data.get("id_token") or "")
    if email is None:
        return JsonResponse({"error": "invalid Google token"}, status=401)
    # Google already verified the email, so the account is active immediately.
    user, created = User.objects.get_or_create(username=email, defaults={"email": email})
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return _token_response(user)


@csrf_exempt
@require_POST
def password_reset(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    user = User.objects.filter(username=email).first()
    if user is not None:
        _, code = VerificationCode.issue(user, VerificationCode.PURPOSE_RESET)
        send_code(user, code, VerificationCode.PURPOSE_RESET)
    # Always 200 so we don't reveal which emails have accounts.
    return JsonResponse({"detail": "if the account exists, a reset code was sent"})


@csrf_exempt
@require_POST
def password_reset_confirm(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"error": "invalid json"}, status=400)
    email = (data.get("email") or "").strip().lower()
    code = data.get("code") or ""
    new_password = data.get("new_password") or ""
    user = User.objects.filter(username=email).first()
    if user is None or not VerificationCode.redeem(user, VerificationCode.PURPOSE_RESET, code):
        return JsonResponse({"error": "invalid or expired code"}, status=400)
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages}, status=400)
    user.set_password(new_password)
    # A successful reset proves email ownership, so activate if still unverified.
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
    # Revoke all existing tokens on a password reset.
    AuthToken.objects.filter(user=user).delete()
    return _token_response(user)


@csrf_exempt
@require_POST
@require_user
def logout(request):
    """Revoke the token used for this request."""
    request.auth_token.delete()
    return JsonResponse({"ok": True})


@require_user
def me(request):
    user = request.auth_user
    return JsonResponse(
        {
            "email": user.email,
            "date_joined": user.date_joined.isoformat(),
        }
    )
