"""
Server-side AI providers for the AptenByte proxy. Holds the keys so the app can use AI without
BYOK. Streams text deltas; tries Gemini first, then OpenRouter (rotating keys/models) as fallback.
"""

import json

import requests
from django.conf import settings

GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 60


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


def gemini_stream(messages, keys, model):
    payload = {"contents": _to_gemini_contents(messages)}
    url = GEMINI_STREAM_URL.format(model=model)
    last_err = None
    for key in keys:
        try:
            with requests.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                stream=True,
                timeout=TIMEOUT,
            ) as r:
                if r.status_code != 200:
                    last_err = f"gemini {r.status_code}"
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
                        yield text
                return
        except requests.RequestException as exc:
            last_err = str(exc)
            continue
    raise RuntimeError(last_err or "gemini: no usable keys")


def openrouter_stream(messages, keys, models):
    last_err = None
    for key in keys:
        for model in models:
            try:
                with requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://penguinscancode.com",
                        "X-Title": "AptenByte",
                    },
                    json={"model": model, "messages": messages, "stream": True},
                    stream=True,
                    timeout=TIMEOUT,
                ) as r:
                    if r.status_code != 200:
                        last_err = f"openrouter {r.status_code} ({model})"
                        continue
                    produced = False
                    for line in r.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            return
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
                continue
    raise RuntimeError(last_err or "openrouter: no usable keys")


def stream_completion(messages):
    """Yields text deltas for [messages], Gemini first then OpenRouter. Raises if nothing works."""
    keys = settings.AI_KEYS
    produced = False
    if keys.get("gemini"):
        try:
            for delta in gemini_stream(messages, keys["gemini"], settings.GEMINI_MODEL):
                produced = True
                yield delta
            return
        except Exception:
            if produced:
                return  # already streamed something — don't restart on another provider
    if keys.get("openrouter"):
        yield from openrouter_stream(messages, keys["openrouter"], settings.OPENROUTER_MODELS)
        return
    if not produced:
        raise RuntimeError("No AI keys are configured on the server")
