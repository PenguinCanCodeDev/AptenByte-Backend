from django.db import models


class CrashReport(models.Model):
    """One app crash sent by the Android app's CrashReporter.

    Contains only the exception class names + stack frames (never exception messages or typed
    text), the app/Android version and the phone model. Reports with the same `fingerprint` are
    the same bug; the dashboard groups by it.
    """

    fingerprint = models.CharField(max_length=32, db_index=True)
    exception = models.CharField(max_length=200)
    stack = models.TextField()
    thread = models.CharField(max_length=20, blank=True, default='')
    app_version = models.CharField(max_length=40, blank=True, default='')
    android = models.CharField(max_length=40, blank=True, default='')
    device = models.CharField(max_length=120, blank=True, default='')
    crashed_at = models.DateTimeField(null=True, blank=True)  # when it happened on the phone
    created_at = models.DateTimeField(auto_now_add=True)       # when it reached the server

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.exception} ({self.app_version})'
