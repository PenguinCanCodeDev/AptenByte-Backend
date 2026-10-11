import json

from django.test import TestCase

from .models import CrashReport

STACK = (
    "java.lang.IllegalStateException\n"
    "    at com.penguinscancode.aptenbyte.ime.KeyboardView.onTouchEvent(KeyboardView.kt:612)\n"
    "    at android.view.View.dispatchTouchEvent(View.java:15000)\n"
    "Caused by: java.lang.NullPointerException\n"
    "    at com.penguinscancode.aptenbyte.ime.SwipeDecoder.decode(SwipeDecoder.kt:80)\n"
)


class CrashSubmitTests(TestCase):
    def post(self, body):
        return self.client.post('/api/crash/', data=json.dumps(body), content_type='application/json')

    def report(self, **over):
        body = {
            'fingerprint': 'a1b2c3d4e5f60718', 'exception': 'java.lang.NullPointerException',
            'stack': STACK, 'thread': 'main', 'app_version': '1.0.0-beta.3',
            'android': '14 (API 34)', 'device': 'samsung SM-A137F', 'at': 1760000000000,
        }
        body.update(over)
        return body

    def test_accepts_valid_report(self):
        r = self.post(self.report())
        self.assertEqual(r.status_code, 200)
        c = CrashReport.objects.get()
        self.assertEqual(c.thread, 'main')
        self.assertIn('SwipeDecoder.decode', c.stack)
        self.assertIsNotNone(c.crashed_at)

    def test_free_text_is_stripped_from_stack(self):
        # A client must not be able to store typed text: non-frame lines are dropped.
        r = self.post(self.report(stack=STACK + "my password is hunter2\nhi john how are you\n"))
        self.assertEqual(r.status_code, 200)
        stack = CrashReport.objects.get().stack
        self.assertNotIn('hunter2', stack)
        self.assertNotIn('john', stack)

    def test_rejects_bad_fields(self):
        self.assertEqual(self.post(self.report(fingerprint='not hex!')).status_code, 400)
        self.assertEqual(self.post(self.report(exception='has spaces in it')).status_code, 400)
        self.assertEqual(self.client.post('/api/crash/', data='nope', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/api/crash/').status_code, 405)
        self.assertEqual(CrashReport.objects.count(), 0)

    def test_dashboard_stats_include_crashes(self):
        from unittest.mock import patch

        from django.test import override_settings
        self.post(self.report())
        self.post(self.report())
        self.post(self.report(fingerprint='ffff0000ffff0000', exception='java.lang.OutOfMemoryError'))
        with override_settings(ADMIN_STATS_TOKEN='t'), \
                patch('releases.views._github_downloads', return_value={'total': 0, 'by_release': [], 'error': None}):
            r = self.client.get('/api/stats/', HTTP_AUTHORIZATION='Bearer t')
        self.assertEqual(r.status_code, 200)
        crashes = r.json()['crashes']
        self.assertEqual(crashes['total'], 3)
        self.assertEqual(crashes['top'][0]['count'], 2)
        self.assertIn('KeyboardView.onTouchEvent', crashes['top'][0]['where'])

    def test_rejects_oversized(self):
        r = self.post(self.report(stack='x' * 40000))
        self.assertEqual(r.status_code, 413)
