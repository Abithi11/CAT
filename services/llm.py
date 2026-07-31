"""LM Studio structured-output client (OpenAI-compatible endpoint via HTTPX).

The LLM never touches the database: callers gather context themselves, pass it
as text, and get back a Pydantic-validated object. Any transport or validation
failure raises LLMUnavailable so callers can fall back to deterministic logic.

Two response strategies, negotiated automatically and then cached per process:

- ``json_schema`` — LM Studio's grammar-constrained mode. Correct when it works,
  but reasoning models (nemotron, qwen-thinking, deepseek-r1 …) return an EMPTY
  content field under it: the grammar applies to the visible channel while the
  model spends its budget in the reasoning channel.
- ``prompt`` — schema pasted into the system prompt, plain text back, parsed
  defensively. Slower to get right but works on every model.

The first call probes ``json_schema`` and silently downgrades on empty content,
so a mixed fleet of local models all work without configuration.
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, ValidationError

from models.config import settings

logger = logging.getLogger(__name__)

_model_cache: str | None = None
_strategy_cache: str | None = None  # "json_schema" | "prompt"

_THINK_BLOCK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


class LLMUnavailable(Exception):
    pass


async def probe() -> dict:
    """Startup reachability check — logs loudly so a misconfigured LLM_BASE_URL
    is obvious before the demo rather than during it."""
    try:
        async with _client() as client:
            model = await _resolve_model(client)
        logger.info("LM Studio reachable at %s (model: %s)", settings.llm_base_url, model)
        return {"reachable": True, "base_url": settings.llm_base_url, "model": model}
    except Exception as e:
        logger.warning(
            "LM Studio NOT reachable at %s (%s) — the investigator agent will use "
            "its rule-based fallback. Inside Docker, mDNS '.local' names do not "
            "resolve: set LLM_BASE_URL to an IP, or to "
            "http://host.docker.internal:1234/v1 if LM Studio runs on the Docker host.",
            settings.llm_base_url, e)
        return {"reachable": False, "base_url": settings.llm_base_url, "error": str(e)}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.llm_base_url,
        timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=5.0),
        headers={"Authorization": "Bearer lm-studio"},
    )


async def _resolve_model(client: httpx.AsyncClient) -> str:
    global _model_cache
    if settings.llm_model:
        return settings.llm_model
    if _model_cache:
        return _model_cache
    resp = await client.get("/models")
    resp.raise_for_status()
    data = resp.json().get("data", [])
    # LM Studio also lists loaded embedding/reranker models, which cannot serve
    # chat completions — skip them rather than trusting list order.
    chat_models = [
        m["id"] for m in data
        if not any(tag in m["id"].lower() for tag in ("embed", "rerank", "whisper"))
    ]
    if not chat_models:
        raise LLMUnavailable(
            f"LM Studio has no chat model loaded (saw: {[m['id'] for m in data]})")
    _model_cache = chat_models[0]
    logger.info("LM Studio model auto-detected: %s", _model_cache)
    return _model_cache


def _extract_json(content: str) -> str:
    """Pull a JSON object out of a model reply.

    Handles reasoning tags, markdown fences, and prose wrapped around the
    object by scanning for the first balanced ``{...}`` (string-aware, so
    braces inside values don't confuse it).
    """
    content = _THINK_BLOCK.sub("", content or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3]
        content = content.strip()

    start = content.find("{")
    if start == -1:
        return content

    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(content[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
    return content[start:]


def _schema_prompt(schema: type[BaseModel]) -> str:
    js = schema.model_json_schema()
    fields = []
    for name, spec in js.get("properties", {}).items():
        if "enum" in spec:
            desc = "one of " + " | ".join(json.dumps(v) for v in spec["enum"])
        elif spec.get("type") == "array":
            desc = f"array of {spec.get('items', {}).get('type', 'string')}"
        elif spec.get("type") == "number":
            lo, hi = spec.get("minimum"), spec.get("maximum")
            desc = "number" + (f" between {lo} and {hi}" if lo is not None else "")
        else:
            desc = spec.get("type", "string")
        fields.append(f'  "{name}": {desc}')
    return (
        "Reply with a single JSON object and nothing else — no prose, no code "
        "fences, no repetition of the input. It must have exactly these keys:\n"
        "{\n" + ",\n".join(fields) + "\n}"
    )


async def _post(client: httpx.AsyncClient, model: str, messages: list[dict],
                temperature: float, max_tokens: int,
                response_format: dict | None) -> tuple[str, str]:
    """POST a chat completion. Returns (content, reasoning_content)."""
    payload = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    resp = await client.post("/chat/completions", json=payload)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise LLMUnavailable(f"LM Studio error: {body['error']}")
    message = body["choices"][0]["message"]
    return message.get("content") or "", message.get("reasoning_content") or ""


async def structured_completion(
    system: str,
    user: str,
    schema: type[BaseModel],
    *,
    temperature: float = 0.1,
    max_tokens: int = 3000,
) -> BaseModel:
    """Chat completion whose reply is validated against `schema`.

    Negotiates the working response strategy for the loaded model, retries once
    with validation feedback, then raises LLMUnavailable.
    """
    global _strategy_cache
    try:
        async with _client() as client:
            model = await _resolve_model(client)

            strategies = [_strategy_cache] if _strategy_cache else ["json_schema", "prompt"]
            last_error = "no attempt made"

            for strategy in strategies:
                if strategy == "json_schema":
                    sys_prompt = system
                    fmt = {"type": "json_schema", "json_schema": {
                        "name": schema.__name__, "strict": True,
                        "schema": schema.model_json_schema()}}
                else:
                    sys_prompt = f"{system}\n\n{_schema_prompt(schema)}"
                    fmt = None

                messages = [{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user}]

                for _ in range(2):
                    content, reasoning = await _post(
                        client, model, messages, temperature, max_tokens, fmt)
                    if not content.strip():
                        # Known LM Studio bug (lmstudio-bug-tracker #1773/#1698/#1602):
                        # on reasoning models the schema constraint is applied to the
                        # reasoning stream, so the valid JSON lands in
                        # reasoning_content and content comes back empty. Recover it
                        # from there before paying for another round trip.
                        if reasoning.strip():
                            try:
                                result = schema.model_validate_json(_extract_json(reasoning))
                                logger.info("Recovered structured reply from "
                                            "reasoning_content (LM Studio reasoning-model bug)")
                                return result
                            except ValidationError:
                                pass
                        last_error = f"{strategy}: empty content"
                        logger.info("LM Studio returned empty content under %s; "
                                    "falling back to prompt-injected schema", strategy)
                        break
                    candidate = _extract_json(content)
                    try:
                        result = schema.model_validate_json(candidate)
                        if _strategy_cache != strategy:
                            _strategy_cache = strategy
                            logger.info("LM Studio structured-output strategy: %s", strategy)
                        return result
                    except ValidationError as ve:
                        last_error = f"{strategy}: {ve}"
                        messages.append({"role": "assistant", "content": content[:2000]})
                        messages.append({
                            "role": "user",
                            "content": f"That reply failed validation: {ve}. "
                                       f"{_schema_prompt(schema)}",
                        })

            raise LLMUnavailable(f"No usable structured reply ({last_error})")
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"LM Studio unreachable at {settings.llm_base_url}: {e}") from e
