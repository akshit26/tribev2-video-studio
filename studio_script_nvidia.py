"""NVIDIA NIM writer: server-only credentials and content-only streamed previews."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from studio_script_hf import HostedWriterError

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
NAME = "NVIDIA Nemotron 3 Ultra"


def nvidia_token():
    token = os.environ.get("NVIDIA_API_KEY", "").strip()
    if token:
        return token
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "NVIDIA_API_KEY":
                return value.strip().strip("\"'")
    except OSError:
        pass
    return ""


def validate_configuration(brief):
    if not nvidia_token():
        raise ValueError("Set NVIDIA_API_KEY in the server environment or .env to use Nemotron.")


def chat_completion(token, model, system, prompt, max_tokens, temperature, preview=None):
    body = {"model": model, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": temperature, "top_p": .95, "max_tokens": min(8192, max(4096, max_tokens + 1024)),
        "chat_template_kwargs": {"enable_thinking": True}, "stream": True}
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "text/event-stream"}, method="POST")
    content, usage, finished = "", {}, False
    deadline = time.monotonic() + 240
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise HostedWriterError("NVIDIA has not returned a completed response. Saved drafts are retained; retry manually.")
            for line in response:
                size += len(line)
                if time.monotonic() > deadline or size > 2_000_000:
                    raise HostedWriterError("NVIDIA response exceeded its time or size limit. Saved drafts are retained.")
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("error"):
                    raise HostedWriterError("NVIDIA could not complete this request. Saved drafts are retained; retry manually.")
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                # Never save or display reasoning_content, even in checkpoints.
                piece = delta.get("content")
                if isinstance(piece, str):
                    content += piece
                    if preview:
                        preview(content)
                reason = choice.get("finish_reason")
                if reason == "length":
                    raise ValueError("NVIDIA output reached its token limit; return shorter JSON fields.")
                if reason in {"content_filter", "error"}:
                    raise HostedWriterError("NVIDIA could not complete the requested content. Saved drafts are retained.")
                if reason == "stop":
                    finished = True
    except urllib.error.HTTPError as exc:
        messages = {401: "NVIDIA API key was rejected. Update NVIDIA_API_KEY on the server.",
                    402: "NVIDIA account credits are unavailable. Use Local or check your NVIDIA account.",
                    403: "NVIDIA account does not have access to this model.",
                    404: "Nemotron is not available at the NVIDIA endpoint.",
                    429: "NVIDIA rate limit reached. Retry later or use Local."}
        raise HostedWriterError(messages.get(exc.code, f"NVIDIA inference unavailable (HTTP {exc.code}). Saved drafts are retained.")) from None
    except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError, IndexError):
        raise HostedWriterError("NVIDIA connection failed or returned an unreadable stream. Saved drafts are retained; retry manually.") from None
    if not finished:
        raise HostedWriterError("NVIDIA stream ended before completion. Saved drafts are retained; retry manually.")
    from studio_review_parts import decoded_json
    parsed = decoded_json(content)
    if parsed is None:
        raise ValueError("NVIDIA must return a JSON object without commentary.")
    return parsed, usage


def run_nvidia_writer(output, request, progress):
    from studio_script_hf import run_hf_writer
    return run_hf_writer(output, request, progress, provider=sys.modules[__name__])
