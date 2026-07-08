"""Dev helper: seed a release and smoke-test the endpoints. Run: python dev_smoke.py"""
import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aptenbyte_api.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402

from releases.models import Release  # noqa: E402

Release.objects.update_or_create(
    version_code=2,
    defaults=dict(
        version_name="1.0.0-beta.2",
        url="https://penguinscancode.com/aptenbyte/download",
        notes="See the What's new card in the app.",
        is_current=True,
    ),
)

c = Client()
r = c.get("/aptenbyte/version.json")
print("GET /aptenbyte/version.json ->", r.status_code, r.content.decode())

gem = len(settings.AI_KEYS.get("gemini", []))
opr = len(settings.AI_KEYS.get("openrouter", []))
print(f"AI keys loaded -> gemini: {gem}, openrouter: {opr}")

if gem or opr:
    payload = {"text": "yo whats up, u free later?", "systemPrompt": "Rewrite politely and clearly. Return only the rewritten text."}
    r = c.post("/v1/rewrite", data=json.dumps(payload), content_type="application/json")
    buf = ""
    for chunk in r.streaming_content:
        buf += chunk.decode()
        if len(buf) > 400:
            break
    print("POST /v1/rewrite sample ->")
    print(buf[:500])
else:
    print("No AI keys in .env — skipping the proxy call.")
