import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac


class ClientInfo(models.Model):
    """Last app version seen for a user, so the dashboard can show which app
    versions are in use. Updated from the ``X-App-Version`` header on API calls.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_info",
    )
    app_version = models.CharField(max_length=40, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} · {self.app_version}"


class AuthToken(models.Model):
    """A bearer token the mobile app sends on API calls, tied to a user.

    The app stores the key after login/registration and sends it as
    ``Authorization: Bearer <key>`` on every request to a gated endpoint.
    """

    key = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, user):
        """Create and return a fresh token for [user]."""
        return cls.objects.create(user=user, key=secrets.token_urlsafe(32))

    def __str__(self):
        return f"{self.user} · {self.key[:8]}…"


def _hash_code(code):
    """Keyed hash of a one-time code (uses SECRET_KEY), so a DB leak can't reveal codes."""
    return salted_hmac("accounts.VerificationCode", code, algorithm="sha256").hexdigest()


class VerificationCode(models.Model):
    """A short-lived 6-digit code emailed for email verification or password reset.

    Only the hash is stored. Codes expire and are single-use, with a per-code
    attempt cap to block brute-forcing.
    """

    PURPOSE_VERIFY = "verify_email"
    PURPOSE_RESET = "reset_password"
    PURPOSES = [
        (PURPOSE_VERIFY, "Verify email"),
        (PURPOSE_RESET, "Reset password"),
    ]

    TTL = timedelta(minutes=15)
    MAX_ATTEMPTS = 5

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_codes",
    )
    purpose = models.CharField(max_length=20, choices=PURPOSES)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, user, purpose):
        """Invalidate prior codes, then create a new one. Returns (obj, plaintext_code)."""
        cls.objects.filter(user=user, purpose=purpose).delete()
        code = f"{secrets.randbelow(1_000_000):06d}"
        obj = cls.objects.create(
            user=user,
            purpose=purpose,
            code_hash=_hash_code(code),
            expires_at=timezone.now() + cls.TTL,
        )
        return obj, code

    @classmethod
    def redeem(cls, user, purpose, code):
        """True iff [code] is the current, unexpired, non-exhausted code. Consumes it on success."""
        obj = cls.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
        if obj is None:
            return False
        if obj.expires_at < timezone.now() or obj.attempts >= cls.MAX_ATTEMPTS:
            obj.delete()
            return False
        cls.objects.filter(pk=obj.pk).update(attempts=obj.attempts + 1)
        if constant_time_compare(obj.code_hash, _hash_code(code or "")):
            obj.delete()
            return True
        return False
