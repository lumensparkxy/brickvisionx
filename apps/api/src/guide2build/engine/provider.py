"""Bounded Gemini Developer API inference through Google ADK, without model tools."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time


DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_THINKING_LEVEL = "medium"
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 120
_MAX_RESPONSE_BYTES = 20_000_000
_MAX_EVENT_BYTES = 32_000_000
_SECRET_PATTERN = re.compile(r"AIza[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{12,}")
_FAILURE_MESSAGES = {
    "authentication_required": "Configure a valid backend GOOGLE_API_KEY for the Gemini Developer API.",
    "rate_limited": "The Gemini Developer API rate limit was reached; the request was not retried.",
    "quota_exceeded": "The Gemini Developer API quota is exhausted; the request was not retried.",
    "invalid_schema": "The engine's structured-output schema was rejected.",
    "unsupported_model": "The selected Gemini model is unavailable for this API key or request.",
    "provider_timeout": "The ADK invocation exceeded its bounded time limit.",
    "invalid_output": "ADK did not return valid output matching the engine schema.",
    "provider_unavailable": "The Gemini Developer API request failed; inspect the sanitized invocation receipt.",
}


class ProviderFailure(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        # ADK 2 emits exceptions as events and preserves a string status field.
        self.status = code
        super().__init__(message)


def child_environment(environ=None):
    """Minimal credential-free environment for the local Chromium renderer."""
    source = os.environ if environ is None else environ
    allowed = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    return {key: source[key] for key in allowed if key in source}


def classify_provider_error(error):
    """Inspect diagnostics locally, but expose only fixed messages and safe codes."""
    if isinstance(error, ProviderFailure):
        return error
    diagnostic = str(error).lower()
    status = str(getattr(error, "code", getattr(error, "status_code", "")))
    if status in _FAILURE_MESSAGES:
        code = status
    elif isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
        code = "provider_timeout"
    elif status in {"401", "403"} or any(term in diagnostic for term in
            ("api_key_invalid", "api key not valid", "unauthenticated", "permission_denied")):
        code = "authentication_required"
    elif status == "429" or any(term in diagnostic for term in ("resource_exhausted", "rate limit")):
        code = "quota_exceeded" if any(term in diagnostic for term in
            ("quota", "billing", "credits", "daily limit")) else "rate_limited"
    elif "quota" in diagnostic:
        code = "quota_exceeded"
    elif status == "404" or any(term in diagnostic for term in
            ("model is not supported", "model not found", "unsupported model", "not supported for generatecontent")):
        code = "unsupported_model"
    elif any(term in diagnostic for term in ("response_json_schema", "response_schema", "invalid_json_schema")):
        code = "invalid_schema"
    elif "llmcallslimit" in type(error).__name__.lower():
        code = "invalid_output"
    else:
        code = "provider_unavailable"
    return ProviderFailure(code, _FAILURE_MESSAGES[code])


def _redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return _SECRET_PATTERN.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {_redact(key, secrets): _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    return value


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode()


class GoogleAdkProvider:
    def __init__(self, model=DEFAULT_MODEL, thinking_level=DEFAULT_THINKING_LEVEL,
                 timeout=DEFAULT_INFERENCE_TIMEOUT_SECONDS):
        if not isinstance(model, str) or not re.fullmatch(r"gemini-[a-zA-Z0-9._-]{1,150}", model):
            raise ValueError("Select a Gemini Developer API model name")
        if thinking_level not in {"low", "medium", "high"}:
            raise ValueError("Unsupported provider thinking level")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Provider timeout must be a finite positive number")
        self.model = model
        self.thinking_level = thinking_level
        self.timeout = timeout

    def call(self, prompt, images, schema, evidence: Path, check=lambda: None):
        from guide2build.core.environment import load_local_environment
        from .store import LeaseLost

        load_local_environment()
        secrets = tuple(value for key in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY")
                        if (value := os.environ.get(key)))
        evidence = Path(evidence)
        evidence.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        runtime = {"provider": "google_adk", "model": self.model, "thinking_level": self.thinking_level,
            "timeout_seconds": self.timeout, "auth": "gemini_developer_api", "vertexai": False,
            "tools_disabled": True, "sdk_attempts": 1, "max_adk_model_calls": 1,
            "provider_fallback": False, "session_storage": "isolated_in_memory"}
        receipt = {**runtime, "status": "started", "model_requests_started": 0,
                   "reported_usage": {}, "completion_or_accuracy_claim": False}

        def write_json(name, value):
            (evidence / name).write_text(json.dumps(_redact(value, secrets), indent=2, ensure_ascii=False))

        write_json("request-runtime.json", runtime)
        (evidence / "events.jsonl").write_text("")

        def on_request():
            receipt["model_requests_started"] += 1

        def on_event(event):
            safe = _redact(event, secrets)
            line = json.dumps(safe, ensure_ascii=False) + "\n"
            path = evidence / "events.jsonl"
            if path.stat().st_size + len(line.encode()) > _MAX_EVENT_BYTES:
                raise ProviderFailure("invalid_output", "ADK event evidence exceeded its bounded size.")
            with path.open("a") as output:
                output.write(line)
            for key, value in safe.get("reported_usage", {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    receipt["reported_usage"][key] = receipt["reported_usage"].get(key, 0) + value

        try:
            check()
            if not isinstance(prompt, str) or len(prompt.encode()) > 1_000_000:
                raise ProviderFailure("invalid_output", "Proposal prompt exceeds its 1 MB input limit.")
            from jsonschema import ValidationError
            from jsonschema.validators import validator_for
            try:
                validator_type = validator_for(schema)
                validator_type.check_schema(schema)
                validator = validator_type(schema)
            except Exception:
                raise ProviderFailure("invalid_schema", _FAILURE_MESSAGES["invalid_schema"]) from None
            prompt = _redact(prompt, secrets)
            (evidence / "prompt.txt").write_text(prompt)
            write_json("schema.json", schema)
            receipt["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
            receipt["schema_sha256"] = hashlib.sha256(_json_bytes(schema)).hexdigest()
            image_inputs = []
            receipt["images"] = []
            for image in images:
                check()
                path = Path(image)
                data = path.read_bytes()
                if len(data) > 20_000_000:
                    raise ProviderFailure("invalid_output", "An input image exceeds the 20 MB input limit.")
                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                    mime_type = "image/png"
                elif data.startswith(b"\xff\xd8\xff"):
                    mime_type = "image/jpeg"
                elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                    mime_type = "image/webp"
                else:
                    raise ProviderFailure("invalid_output", "Only PNG, JPEG and WebP instruction images are accepted.")
                image_inputs.append((data, mime_type))
                receipt["images"].append({"sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data), "mime_type": mime_type})
            api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise ProviderFailure("authentication_required", _FAILURE_MESSAGES["authentication_required"])
            from .adk_runtime import run_adk_request
            raw = asyncio.run(self._bounded_request(run_adk_request(
                api_key=api_key, model=self.model, thinking_level=self.thinking_level, timeout=self.timeout,
                prompt=prompt, images=image_inputs, schema=schema, on_request=on_request, on_event=on_event),
                started=started, check=check))
            if len(raw.encode()) > _MAX_RESPONSE_BYTES:
                raise ProviderFailure("invalid_output", "ADK response exceeded the 20 MB output limit.")
            raw = _redact(raw, secrets)
            (evidence / "response.json").write_text(raw)
            receipt["response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            try:
                value = json.loads(raw)
                validator.validate(value)
                if not isinstance(value, dict):
                    raise ValueError("The engine proposal must be an object")
            except (ValueError, ValidationError):
                raise ProviderFailure("invalid_output", _FAILURE_MESSAGES["invalid_output"]) from None
            receipt["status"] = "completed"
            return value
        except (InterruptedError, KeyboardInterrupt, LeaseLost):
            receipt["status"] = "cancelled"
            receipt["failure"] = {"code": "cancelled", "message": "Invocation cancelled; consumed attempts are retained."}
            raise
        except Exception as error:
            failure = classify_provider_error(error)
            failure = ProviderFailure(failure.code, _redact(str(failure), secrets))
            receipt["status"] = "failed"
            receipt["failure"] = {"code": failure.code, "message": str(failure)}
            raise failure from None
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            write_json("invocation.json", receipt)
            write_json("runtime-result.json", receipt)

    async def _bounded_request(self, request, *, started, check):
        task = asyncio.create_task(request)
        try:
            while True:
                check()
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProviderFailure("provider_timeout", _FAILURE_MESSAGES["provider_timeout"])
                done, _ = await asyncio.wait({task}, timeout=min(.05, remaining))
                if done:
                    check()
                    return task.result()
        finally:
            if not task.done():
                task.cancel()
            # Let ADK close its generator and HTTP connection before returning.
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
