"""
Server-side AI providers for the AptenByte proxy. Holds the keys so the app can
use AI without BYOK. Streams text deltas.

Providers are tried in an adaptive, persisted order (see ``ProviderHealth``): the
one that works keeps its place; one that fails (error / 429 / empty reply) is
demoted to the bottom, so the NEXT request doesn't start with a dead provider.
Each provider also rotates through its own list of models/keys on failure. A
short output-guard is appended to the system prompt so even a weak free model
returns clean, usable text.
"""

import json

import requests
from django.conf import settings
from django.db.models import F, Max
from django.utils import timezone

GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
TIMEOUT = 60

# Order used the very first time, before any success/failure has been recorded.
DEFAULT_ORDER = ["gemini", "openrouter", "nvidia"]

# Appended to the system turn so even a weak/free model returns only the answer.
_OUTPUT_GUARD = (
    "Important: reply with ONLY the requested text. No preamble, no explanation, "
    "no labels, no surrounding quotes, and no markdown code fences. If you are "
    "unsure, still return your best single plain-text answer."
)


# ── prompt hardening ─────────────────────────────────────────────────────────
def _reinforce(messages):
    """Return a copy of [messages] with the output-guard added to the system turn."""
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            m["content"] = (m.get("content", "").rstrip() + "\n\n" + _OUTPUT_GUARD).strip()
            return out
    out.insert(0, {"role": "system", "content": _OUTPUT_GUARD})
    return out


# ── Gemini ───────────────────────────────────────────────────────────────────
def _to_gemini_contents(messages):
    """Fold system messages into the first user turn; map roles to user/model."""
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    contents = []
    for m in messages:
        if m.get("role") == "system":
            continue
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    if system:
        for c in contents:
            if c["role"] == "user":
                c["parts"][0]["text"] = f"{system}\n\n{c['parts'][0]['text']}"
                break
        else:
            contents.insert(0, {"role": "user", "parts": [{"text": system}]})
    return contents


def gemini_stream(messages, keys, models):
    payload = {"contents": _to_gemini_contents(messages)}
    last_err = None
    for key in keys:
        for model in models:
            produced = False
            try:
                with requests.post(
                    GEMINI_STREAM_URL.format(model=model),
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                    stream=True,
                    timeout=TIMEOUT,
                ) as r:
                    if r.status_code != 200:
                        last_err = f"gemini {r.status_code} ({model})"
                        continue
                    for line in r.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if not data:
                            continue
                        try:
                            obj = json.loads(data)
                            text = obj["candidates"][0]["content"]["parts"][0]["text"]
                        except Exception:
                            continue
                        if text:
                            produced = True
                            yield text
                    if produced:
                        return
            except requests.RequestException as exc:
                last_err = str(exc)
                if produced:
                    return
                continue
    raise RuntimeError(last_err or "gemini: no usable keys")


# ── OpenAI-compatible providers (OpenRouter, NVIDIA) ──────────────────────────
def _openai_compatible_stream(url, messages, keys, models, extra_headers=None):
    last_err = None
    for key in keys:
        for model in models:
            produced = False
            try:
                with requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        **(extra_headers or {}),
                    },
                    json={"model": model, "messages": messages, "stream": True},
                    stream=True,
                    timeout=TIMEOUT,
                ) as r:
                    if r.status_code != 200:
                        last_err = f"{r.status_code} ({model})"
                        continue
                    for line in r.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"].get("content")
                        except Exception:
                            continue
                        if delta:
                            produced = True
                            yield delta
                    if produced:
                        return
            except requests.RequestException as exc:
                last_err = str(exc)
                if produced:
                    return
                continue
    raise RuntimeError(last_err or "no usable keys/models")


def openrouter_stream(messages, keys, models):
    yield from _openai_compatible_stream(
        OPENROUTER_URL,
        messages,
        keys,
        models,
        {"HTTP-Referer": "https://penguinscancode.com", "X-Title": "AptenByte"},
    )


def nvidia_stream(messages, keys, models):
    yield from _openai_compatible_stream(NVIDIA_URL, messages, keys, models)


# ── adaptive, persisted provider rotation ─────────────────────────────────────
def _provider_specs():
    """Configured providers → their streamer callable (only those with keys)."""
    keys = settings.AI_KEYS
    specs = {
        "gemini": lambda msgs: gemini_stream(msgs, keys.get("gemini", []), settings.GEMINI_MODELS),
        "openrouter": lambda msgs: openrouter_stream(
            msgs, keys.get("openrouter", []), settings.OPENROUTER_MODELS
        ),
        "nvidia": lambda msgs: nvidia_stream(msgs, keys.get("nvidia", []), settings.NVIDIA_MODELS),
    }
    return {name: fn for name, fn in specs.items() if keys.get(name)}


def _ordered_names(configured):
    """Return [configured] provider names in persisted priority order, creating rows."""
    from .models import ProviderHealth

    rows = {p.name: p for p in ProviderHealth.objects.filter(name__in=configured)}
    missing = [n for n in configured if n not in rows]
    if missing:
        base = ProviderHealth.objects.aggregate(m=Max("priority"))["m"]
        base = -1 if base is None else base
        for i, name in enumerate(sorted(missing, key=DEFAULT_ORDER.index), start=1):
            rows[name] = ProviderHealth.objects.create(name=name, priority=base + i)
    return sorted(configured, key=lambda n: (rows[n].priority, n))


def _demote(name, err):
    """Move [name] to the bottom of the order and record the failure (persisted)."""
    from .models import ProviderHealth

    top = ProviderHealth.objects.aggregate(m=Max("priority"))["m"] or 0
    ProviderHealth.objects.filter(name=name).update(
        priority=top + 1,
        last_failure_at=timezone.now(),
        failure_count=F("failure_count") + 1,
        last_error=(err or "")[:200],
    )


def _mark_success(name):
    from .models import ProviderHealth

    ProviderHealth.objects.filter(name=name).update(
        last_success_at=timezone.now(),
        success_count=F("success_count") + 1,
        last_error="",
    )


def stream_completion(messages):
    """Yield text deltas, trying providers in adaptive, persisted order.

    On success the provider keeps its place; on failure it is demoted to the
    bottom and the next provider is tried, so later requests skip a dead one.
    Raises only if every configured provider fails.
    """
    specs = _provider_specs()
    if not specs:
        raise RuntimeError("No AI keys are configured on the server")
    messages = _reinforce(messages)
    last_err = None
    for name in _ordered_names(list(specs.keys())):
        produced = False
        try:
            for delta in specs[name](messages):
                produced = True
                yield delta
        except Exception as exc:
            last_err = f"{name}: {exc}"
            if produced:
                # Already streamed usable output before dropping — count it a win.
                _mark_success(name)
                return
            _demote(name, str(exc))
            continue
        if produced:
            _mark_success(name)
            return
        last_err = f"{name}: empty response"
        _demote(name, "empty response")
    raise RuntimeError(last_err or "all AI providers failed")
