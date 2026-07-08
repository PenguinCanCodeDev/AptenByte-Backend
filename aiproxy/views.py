import json

from django.http import HttpResponseBadRequest, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.auth import require_user

from .providers import stream_completion

# The keyboard's ProxyLLMProvider builds a system+user turn for /rewrite and sends the raw message
# list for /chat, then reads Server-Sent Events where each `data:` is {"text": "<delta>"} and the
# stream ends with `data: [DONE]`.


def _sse(messages):
    try:
        for delta in stream_completion(messages):
            yield f"data: {json.dumps({'text': delta})}\n\n"
    except Exception as exc:  # surface a single error event, then close cleanly
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
    yield "data: [DONE]\n\n"


def _stream_response(messages):
    resp = StreamingHttpResponse(_sse(messages), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"  # disable proxy buffering (nginx) so chunks flush live
    return resp


@csrf_exempt
@require_POST
@require_user
def rewrite(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")
    text = body.get("text", "")
    system = body.get("systemPrompt", "")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]
    return _stream_response(messages)


@csrf_exempt
@require_POST
@require_user
def chat(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")
    messages = body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return HttpResponseBadRequest("messages must be a non-empty list")
    # Only keep the fields the providers use.
    cleaned = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
        if isinstance(m, dict)
    ]
    return _stream_response(cleaned)
