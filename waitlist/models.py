from django.db import models


class Signup(models.Model):
    """A waitlist email captured from the website."""

    email = models.EmailField(unique=True)
    source = models.CharField(max_length=64, blank=True, default='website')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email
