from django.db import models


class ProviderHealth(models.Model):
    """Adaptive, persisted ordering for the AI providers.

    Providers are tried in ascending ``priority``. When one fails (network
    error, rate limit / 429, or an empty reply) it is demoted to the bottom and
    that new order is saved, so the *next* request starts with whatever is
    working now instead of always hammering the same (possibly dead) provider
    first. A provider that succeeds keeps its spot, so a healthy one naturally
    stays near the top.
    """

    name = models.CharField(max_length=32, unique=True)
    priority = models.IntegerField(default=0)  # lower = tried first
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return f"{self.name} (p{self.priority})"


class DailyUsage(models.Model):
    """One row per day counting AI proxy requests, for the dashboard usage stats."""

    date = models.DateField(unique=True)
    rewrites = models.PositiveIntegerField(default=0)
    chats = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]

    @property
    def total(self):
        return self.rewrites + self.chats

    def __str__(self):
        return f"{self.date}: {self.total}"
