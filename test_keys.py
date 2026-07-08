"""
Quick health-check for API keys.

Sends a simple "Hi" message to:
  - 2 Gemini keys  (model: gemini-2.0-flash)
  - 1 OpenRouter key (model: meta-llama/llama-3.3-70b-instruct:free,
    with automatic fallback to other free models if rate-limited)

Usage:
  1. Copy .env.example to .env and fill in your keys.
  2. pip install requests python-dotenv
  3. python test_keys.py
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = "gemini-2.0-flash"

# Tried in order: the first one is your requested model; the rest are
# alternate free models used as fallbacks if the previous one is
# rate-limited (HTTP 429) upstream.
OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]
PROMPT = "Hi"
TIMEOUT = 30


def test_gemini(label: str, api_key: str) -> None:
    print(f"\n=== {label} (Gemini / {GEMINI_MODEL}) ===")
    if not api_key:
        print("  SKIPPED: no key set in .env")
        return

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {"contents": [{"parts": [{"text": PROMPT}]}]}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"  FAILED: request error: {exc}")
        return

    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code}")
        print(f"  Body: {resp.text[:500]}")
        return

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        print(f"  WORKING (200) but could not parse reply: {exc}")
        print(f"  Body: {resp.text[:500]}")
        return

    print("  WORKING")
    print(f"  Reply: {text.strip()}")


def test_openrouter(label: str, api_key: str) -> None:
    print(f"\n=== {label} (OpenRouter) ===")
    if not api_key:
        print("  SKIPPED: no key set in .env")
        return

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Walk the model list trying to get a reply. A 200 confirms the key works.
    # 401/403 is a genuine key/auth problem, so we stop and report it.
    # Anything else (429 rate-limit, 404/400 model unavailable, 5xx upstream)
    # is a per-model issue, not a key issue, so we fall back to the next model.
    for index, model in enumerate(OPENROUTER_MODELS, start=1):
        prefix = "Trying" if index == 1 else "Falling back to"
        print(f"  {prefix}: {model}")

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            print(f"    request error: {exc}, trying next model...")
            continue

        if resp.status_code in (401, 403):
            print(f"    FAILED: HTTP {resp.status_code} (key/auth problem)")
            print(f"    Body: {resp.text[:500]}")
            return

        if resp.status_code != 200:
            reason = "rate-limited" if resp.status_code == 429 else "unavailable"
            print(f"    HTTP {resp.status_code} ({reason}), trying next model...")
            continue

        try:
            text = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            print(f"    WORKING (200) but could not parse reply: {exc}")
            print(f"    Body: {resp.text[:500]}")
            return

        print(f"    WORKING (model: {model})")
        print(f"    Reply: {text.strip()}")
        return

    print("  FAILED: every free model was unavailable/rate-limited. Try again later.")


def main() -> None:
    test_gemini("Gemini key #1", os.getenv("GEMINI_API_KEY_1"))
    test_gemini("Gemini key #2", os.getenv("GEMINI_API_KEY_2"))
    test_openrouter("OpenRouter key #1", os.getenv("OPENROUTER_API_KEY"))
    test_openrouter("OpenRouter key #2", os.getenv("OPENROUTER_API_KEY_2"))
    print()


if __name__ == "__main__":
    sys.exit(main())
