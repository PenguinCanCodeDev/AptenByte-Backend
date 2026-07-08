import json
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase

User = get_user_model()

STRONG_PW = "sup3r-secret-pw"


def _post(client, path, payload, token=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    return client.post(
        path, data=json.dumps(payload), content_type="application/json", **headers
    )


def _latest_code():
    """Extract the 6-digit code from the most recently sent email."""
    return re.search(r"(\d{6})", mail.outbox[-1].body).group(1)


class RegistrationTests(TestCase):
    def test_register_creates_inactive_user_and_emails_code(self):
        resp = _post(Client(), "/auth/register", {"email": "a@b.com", "password": STRONG_PW})
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn("token", resp.json())  # no token before verification
        self.assertFalse(User.objects.get(username="a@b.com").is_active)
        self.assertEqual(len(mail.outbox), 1)

    def test_duplicate_register_conflicts(self):
        c = Client()
        _post(c, "/auth/register", {"email": "a@b.com", "password": STRONG_PW})
        resp = _post(c, "/auth/register", {"email": "a@b.com", "password": "another-pw-123"})
        self.assertEqual(resp.status_code, 409)

    def test_verify_activates_and_returns_token(self):
        c = Client()
        _post(c, "/auth/register", {"email": "a@b.com", "password": STRONG_PW})
        resp = _post(c, "/auth/verify-email", {"email": "a@b.com", "code": _latest_code()})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())
        self.assertTrue(User.objects.get(username="a@b.com").is_active)

    def test_verify_wrong_code_fails(self):
        c = Client()
        _post(c, "/auth/register", {"email": "a@b.com", "password": STRONG_PW})
        resp = _post(c, "/auth/verify-email", {"email": "a@b.com", "code": "000000"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.get(username="a@b.com").is_active)


class LoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        _post(self.client, "/auth/register", {"email": "a@b.com", "password": STRONG_PW})

    def test_login_before_verification_is_403(self):
        resp = _post(self.client, "/auth/login", {"email": "a@b.com", "password": STRONG_PW})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("code"), "email_not_verified")

    def test_login_after_verification(self):
        _post(self.client, "/auth/verify-email", {"email": "a@b.com", "code": _latest_code()})
        resp = _post(self.client, "/auth/login", {"email": "a@b.com", "password": STRONG_PW})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())

    def test_login_wrong_password_is_401(self):
        _post(self.client, "/auth/verify-email", {"email": "a@b.com", "code": _latest_code()})
        resp = _post(self.client, "/auth/login", {"email": "a@b.com", "password": "nope"})
        self.assertEqual(resp.status_code, 401)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = Client()
        _post(self.client, "/auth/register", {"email": "a@b.com", "password": "old-password-123"})
        _post(self.client, "/auth/verify-email", {"email": "a@b.com", "code": _latest_code()})

    def test_reset_flow_changes_password(self):
        self.assertEqual(_post(self.client, "/auth/password/reset", {"email": "a@b.com"}).status_code, 200)
        confirm = _post(
            self.client,
            "/auth/password/reset/confirm",
            {"email": "a@b.com", "code": _latest_code(), "new_password": "brand-new-pw-456"},
        )
        self.assertEqual(confirm.status_code, 200)
        old = _post(self.client, "/auth/login", {"email": "a@b.com", "password": "old-password-123"})
        self.assertEqual(old.status_code, 401)
        new = _post(self.client, "/auth/login", {"email": "a@b.com", "password": "brand-new-pw-456"})
        self.assertEqual(new.status_code, 200)

    def test_reset_unknown_email_still_200(self):
        # Doesn't reveal whether the account exists.
        resp = _post(self.client, "/auth/password/reset", {"email": "nobody@x.com"})
        self.assertEqual(resp.status_code, 200)


class GoogleTests(TestCase):
    @patch("accounts.views.verify_google_id_token", return_value="g@b.com")
    def test_google_creates_active_user_and_token(self, _mock):
        resp = _post(Client(), "/auth/google", {"id_token": "fake"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())
        self.assertTrue(User.objects.get(username="g@b.com").is_active)

    @patch("accounts.views.verify_google_id_token", return_value=None)
    def test_google_invalid_token_is_401(self, _mock):
        resp = _post(Client(), "/auth/google", {"id_token": "bad"})
        self.assertEqual(resp.status_code, 401)


class ProxyGateTests(TestCase):
    def setUp(self):
        self.client = Client()
        _post(self.client, "/auth/register", {"email": "a@b.com", "password": STRONG_PW})
        self.token = _post(
            self.client, "/auth/verify-email", {"email": "a@b.com", "code": _latest_code()}
        ).json()["token"]

    def test_anonymous_rejected(self):
        for path in ("/v1/chat", "/v1/rewrite"):
            resp = _post(self.client, path, {"messages": [{"role": "user", "content": "Hi"}]})
            self.assertEqual(resp.status_code, 401, path)

    def test_bad_token_rejected(self):
        resp = _post(
            self.client, "/v1/chat", {"messages": [{"role": "user", "content": "Hi"}]}, token="nope"
        )
        self.assertEqual(resp.status_code, 401)

    def test_valid_token_passes_gate(self):
        # Streaming response is returned but not consumed by the test client → no AI call.
        resp = _post(
            self.client, "/v1/chat", {"messages": [{"role": "user", "content": "Hi"}]}, token=self.token
        )
        self.assertEqual(resp.status_code, 200)

    def test_me_returns_email(self):
        resp = self.client.get("/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "a@b.com")
