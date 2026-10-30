"""Verifica que el adaptador real del SDK de Anthropic arma y lee bien las respuestas."""

import json

import anthropic
try:
    import httpx2 as httpx  # el SDK de Anthropic 2.x usa httpx2
except ImportError:  # versiones anteriores del SDK usan httpx
    import httpx

from jarvis.llm import AnthropicLLM

FAKE_RESPONSE = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
    "stop_reason": "tool_use", "stop_sequence": None,
    "usage": {"input_tokens": 321, "output_tokens": 12},
    "content": [
        {"type": "text", "text": "Reviso tu día."},
        {"type": "tool_use", "id": "toolu_1", "name": "resumen_dia", "input": {"fecha": "2026-10-27"}},
    ],
}


def test_adaptador_normaliza_tool_use():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json=FAKE_RESPONSE)

    client = anthropic.Anthropic(api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    llm = AnthropicLLM("sk-test", client=client)
    resp = llm.complete(
        model="claude-sonnet-5-5", system="Eres Jarvis", max_tokens=100,
        messages=[{"role": "user", "content": "¿qué tengo hoy?"}],
        tools=[{"name": "resumen_dia", "description": "d", "input_schema": {"type": "object", "properties": {}}}],
    )

    assert sent["system"] == "Eres Jarvis" and sent["tools"][0]["name"] == "resumen_dia"
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls == [{"type": "tool_use", "id": "toolu_1", "name": "resumen_dia", "input": {"fecha": "2026-10-27"}}]
    assert resp.text == "Reviso tu día."
    assert (resp.input_tokens, resp.output_tokens) == (321, 12)
