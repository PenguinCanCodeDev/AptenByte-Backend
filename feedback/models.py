from django.db import models


class Feedback(models.Model):
    """A piece of beta feedback / a suggestion submitted from the website."""

    CATEGORY_CHOICES = [
        ('suggestion', 'Suggestion'),
        ('bug', 'Bug'),
        ('praise', 'Praise'),
        ('other', 'Other'),
    ]

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='suggestion')
    message = models.TextField()
    email = models.EmailField(blank=True, default='')       # optional: so we can follow up
    device = models.CharField(max_length=120, blank=True, default='')  # optional: phone / Android version
    source = models.CharField(max_length=64, blank=True, default='website')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'feedback'

    def __str__(self):
        return f'{self.category}: {self.message[:40]}'
