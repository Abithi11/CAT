"""LM Studio client: model selection, strategy negotiation, and the documented
reasoning-model bug where json_schema output lands in reasoning_content.

Runs against a stub OpenAI-compatible server (httpx MockTransport) — no network,
no LM Studio required.
"""

import json

import httpx
import pytest

import services.llm as llm_mod
from agent.investigator import AgentVerdict
from services.llm import LLMUnavailable, _extract_json, structured_completion

VALID = {
    "verdict": "unassigned_usage",
    "confidence": 0.9,
    "summary": "All usage untraceable.",
    "key_evidence": ["100% ghost days"],
    "recommended_action": "Audit custody records.",
}


@pytest.fixture(autouse=True)
def _clear_caches():
    llm_mod._model_cache = None
    llm_mod._strategy_cache = None
    yield
    llm_mod._model_cache = None
    llm_mod._strategy_cache = None


def _stub(handler, models=None):
    """Patch services.llm._client with a MockTransport-backed client."""
    models = models or [{"id": "test-chat-model"}]

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": models})
        return handler(json.loads(request.content))

    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(route),
                                 base_url="http://stub.local/v1")

    llm_mod._client = factory


class TestExtractJson:
    def test_plain(self):
        assert json.loads(_extract_json('{"a": 1}')) == {"a": 1}

    def test_markdown_fenced(self):
        assert json.loads(_extract_json('```json\n{"a": 1}\n```')) == {"a": 1}

    def test_think_block_stripped(self):
        raw = '<think>let me consider {not json}</think>\n{"a": 1}'
        assert json.loads(_extract_json(raw)) == {"a": 1}

    def test_prose_around_object(self):
        raw = 'Here is my answer:\n{"a": 1, "b": "x"}\nHope that helps!'
        assert json.loads(_extract_json(raw)) == {"a": 1, "b": "x"}

    def test_braces_inside_strings(self):
        raw = '{"msg": "use {curly} braces", "n": 2}'
        assert json.loads(_extract_json(raw))["msg"] == "use {curly} braces"


class TestModelSelection:
    async def test_skips_embedding_models(self):
        seen = {}

        def handler(payload):
            seen["model"] = payload["model"]
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(VALID)}}]})

        _stub(handler, models=[
            {"id": "text-embedding-nomic-embed-text-v1.5"},
            {"id": "nvidia/nemotron-3-nano-4b"},
        ])
        await structured_completion("sys", "user", AgentVerdict)
        assert seen["model"] == "nvidia/nemotron-3-nano-4b"

    async def test_no_chat_model_raises(self):
        _stub(lambda p: httpx.Response(200, json={}),
              models=[{"id": "text-embedding-3-small"}])
        with pytest.raises(LLMUnavailable, match="no chat model"):
            await structured_completion("sys", "user", AgentVerdict)


class TestStrategyNegotiation:
    async def test_json_schema_path(self):
        calls = []

        def handler(payload):
            calls.append(payload)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(VALID)}}]})

        _stub(handler)
        result = await structured_completion("sys", "user", AgentVerdict)
        assert result.verdict == "unassigned_usage"
        assert calls[0]["response_format"]["type"] == "json_schema"
        assert len(calls) == 1

    async def test_reasoning_content_recovered_without_extra_request(self):
        """The documented LM Studio bug: schema constrains the reasoning stream,
        content is empty and the real JSON sits in reasoning_content."""
        calls = []

        def handler(payload):
            calls.append(payload)
            return httpx.Response(200, json={"choices": [{"message": {
                "content": "",
                "reasoning_content": f"Thinking it through...\n{json.dumps(VALID)}",
            }}]})

        _stub(handler)
        result = await structured_completion("sys", "user", AgentVerdict)
        assert result.verdict == "unassigned_usage"
        assert len(calls) == 1, "must not spend a second request when recovery works"

    async def test_falls_back_to_prompt_strategy_on_empty_content(self):
        calls = []

        def handler(payload):
            calls.append(payload)
            if "response_format" in payload:
                return httpx.Response(200, json={
                    "choices": [{"message": {"content": ""}}]})
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(VALID)}}]})

        _stub(handler)
        result = await structured_completion("sys", "user", AgentVerdict)
        assert result.confidence == pytest.approx(0.9)
        assert "response_format" not in calls[-1]
        # the schema must be spelled out in the prompt for the fallback
        assert "verdict" in calls[-1]["messages"][0]["content"]
        assert llm_mod._strategy_cache == "prompt"

    async def test_retries_once_with_validation_feedback(self):
        calls = []

        def handler(payload):
            calls.append(payload)
            if len(calls) == 1:
                return httpx.Response(200, json={"choices": [{"message": {
                    "content": json.dumps({"verdict": "not_a_valid_enum_value"})}}]})
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(VALID)}}]})

        _stub(handler)
        result = await structured_completion("sys", "user", AgentVerdict)
        assert result.verdict == "unassigned_usage"
        assert len(calls) == 2
        assert "failed validation" in calls[1]["messages"][-1]["content"]

    async def test_all_strategies_failing_raises(self):
        _stub(lambda p: httpx.Response(200, json={
            "choices": [{"message": {"content": "not json at all"}}]}))
        with pytest.raises(LLMUnavailable, match="No usable structured reply"):
            await structured_completion("sys", "user", AgentVerdict)

    async def test_transport_error_raises_unavailable(self):
        def factory():
            def boom(request):
                raise httpx.ConnectError("connection refused")
            return httpx.AsyncClient(transport=httpx.MockTransport(boom),
                                     base_url="http://stub.local/v1")

        llm_mod._client = factory
        with pytest.raises(LLMUnavailable, match="unreachable"):
            await structured_completion("sys", "user", AgentVerdict)

    async def test_server_error_payload_raises(self):
        _stub(lambda p: httpx.Response(200, json={
            "error": "'response_format.type' must be 'json_schema' or 'text'"}))
        with pytest.raises(LLMUnavailable):
            await structured_completion("sys", "user", AgentVerdict)
