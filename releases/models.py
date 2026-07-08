from django.db import models


class Release(models.Model):
    """One published AptenByte build. The app polls the current one to offer updates."""

    version_code = models.PositiveIntegerField(
        unique=True, help_text="Must match the app's build.gradle versionCode."
    )
    version_name = models.CharField(max_length=64, help_text='e.g. "1.0.0-beta.2".')
    url = models.URLField(help_text="Where the user downloads the APK / release.")
    notes = models.TextField(blank=True, help_text="What's-new text shown in the app.")
    is_current = models.BooleanField(
        default=True, help_text="Advertise this build as the latest available."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_code"]

    def __str__(self):
        return f"{self.version_name} ({self.version_code})"
