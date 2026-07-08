"""Transactional emails (verification + password reset). Sent via whatever
EMAIL_BACKEND is configured — console in dev, Brevo SMTP in production.
"""

from django.conf import settings
from django.core.mail import send_mail

from .models import VerificationCode


def send_code(user, code, purpose):
    """Email a one-time [code] to [user] for the given purpose."""
    if purpose == VerificationCode.PURPOSE_VERIFY:
        subject = "Verify your AptenByte email"
        body = (
            f"Welcome to AptenByte!\n\n"
            f"Your verification code is: {code}\n\n"
            f"It expires in 15 minutes."
        )
    else:
        subject = "Reset your AptenByte password"
        body = (
            f"We received a request to reset your AptenByte password.\n\n"
            f"Your reset code is: {code}\n\n"
            f"It expires in 15 minutes. If you didn't request this, you can ignore this email."
        )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
