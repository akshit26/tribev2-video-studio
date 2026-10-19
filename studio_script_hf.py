"""Optional HF-hosted script writing; credentials never enter saved briefs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://router.huggingface.co/v1/chat/completions"
MODELS = {
    "deepseek-ai/DeepSeek-V4.1-Flash": "DeepSeek V4.1 Flash",
    "deepseek-ai/DeepSeek-V3.2": "DeepSeek V3.2",
    "Qwen/Qwen3-235B-A22B-Instruct-2507": "Qwen3 235B Instruct",
}
DEFAULT_MODEL = next(iter(MODELS))
MAX_CALLS = 24


class HostedWriterError(RuntimeError):
    """Transport/quota failures must not trigger paid automatic retries."""


def hf_token():
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        return token
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "HF_TOKEN":
                token = value.strip().strip("\"'")
                if token:
                    return token
    from huggingface_hub import get_token
    return get_token()


def configuration():
    from studio_script_local import local_configuration
    return {"default_backend": "local", "token_configured": bool(hf_token()),
            "models": [{"id": key, "name": name} for key, name in MODELS.items()],
            "local_models": local_configuration(),
            "pricing_note": "HF hosted inference uses account credits and is not unlimited free. Local generation stays free. Hosted calls require explicit credit-use opt-in.",
            "pricing_url": "https://huggingface.co/docs/inference-providers/pricing"}


def validate_configuration(brief):
    if brief.get("writer_backend", "local") != "huggingface":
        return
    if brief.get("hf_credits_allowed") is not True:
        raise ValueError("Hosted generation is disabled. Keep Local for free use, or explicitly allow Hugging Face credit usage.")
    if brief.get("hf_model") not in MODELS:
        raise ValueError("Choose a supported Hugging Face writer model.")
    if not hf_token():
        raise ValueError("Set HF_TOKEN in the server environment or .env, or sign in with hf auth login. The token needs Inference Providers permission.")


def chat_completion(token, model, system, prompt, max_tokens, temperature):
    body = {"model": model + ":cheapest", "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": min(max_tokens, 2400), "temperature": temperature,
        "response_format": {"type": "json_object"}, "stream": False}
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        messages = {
            400: "HF rejected the model request or JSON output settings. Choose another hosted model.",
            401: "HF token was rejected. Update HF_TOKEN on the server.",
            402: "HF credits are unavailable or exhausted. Switch to Local for free generation; no credits were purchased.",
            403: "HF token needs Make calls to Inference Providers permission and access to this model.",
            404: "This model is not currently served through the HF router. Choose another model.",
            429: "HF rate limit reached. Retry later or use Local.",
        }
        raise HostedWriterError(messages.get(exc.code, f"HF inference unavailable (HTTP {exc.code}). Saved work is retained.")) from None
    except (OSError, TimeoutError, ValueError):
        raise HostedWriterError("HF connection timed out or returned an unreadable response. Saved work is retained; retry manually to avoid duplicate billed requests.") from None
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if choice.get("finish_reason") == "length":
            raise ValueError("Hosted output reached its token limit; return shorter JSON fields.")
        from studio_review_parts import decoded_json
        parsed = decoded_json(content)
        if parsed is None:
            raise ValueError("Hosted model must return a JSON object, without commentary.")
        return parsed, data.get("usage", {})
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError("HF returned no usable script response.") from None


def run_hf_writer(output, request, progress):
    from studio_pipeline import _write_json
    from studio_review_cache import CompletionCache
    from studio_script_writer import SYSTEM, WRITER_VERSION, library, run_writer
    brief = request["brief"]
    validate_configuration(brief)
    model, token = brief["hf_model"], hf_token()
    signature = hashlib.sha256(json.dumps(["hf-writer-v1", model, SYSTEM, WRITER_VERSION, library()], sort_keys=True).encode()).hexdigest()
    path = output / "hf_writer_checkpoint.json"
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        checkpoint = {}
    cache = CompletionCache(checkpoint, signature)
    stats = {"backend": "huggingface", "model": model, "calls_this_run": 0, "cache_hits": 0, "usage": []}
    fraction = 0

    def report(value, stage):
        nonlocal fraction
        fraction = value
        progress(1 + 98*value, stage)

    def complete(prompt, tokens, label):
        prompt_hash = hashlib.sha256((prompt + str(tokens)).encode()).hexdigest()
        cached = cache.get(label, prompt_hash)
        if cached:
            stats["cache_hits"] += 1
            return cached["result"]
        if stats["calls_this_run"] >= MAX_CALLS:
            raise HostedWriterError("Hosted request limit reached for this run. Saved drafts are retained; retry or switch to Local.")
        progress(1 + 98*fraction, f"{MODELS[model]}: {label}")
        stats["calls_this_run"] += 1
        creative = label.startswith(("Hook options", "Draft")) and "repair" not in label
        temperature = .85 if creative and label.startswith("Hook options") else .7 if creative else 0
        result, usage = chat_completion(token, model, SYSTEM, prompt, tokens, temperature)
        stats["usage"].append(usage)
        cache.remember(label, prompt_hash, result)
        _write_json(path, cache.snapshot())
        _write_json(output / "hf_writer_usage.json", stats)
        return result

    try:
        run_writer(output, complete, report)
    finally:
        _write_json(output / "hf_writer_usage.json", stats)
