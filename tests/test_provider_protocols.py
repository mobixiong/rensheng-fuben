import io
import json
from pathlib import Path

import pytest

from app.image_adapter import ImageConfig, ImageError, generate_image
from app.image_adapter import test_image_connection as check_image_connection
from app.llm_adapter import LLMConfig, LLMError, _provider_text


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_text_openai_provider_request_shape(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({
            "choices": [{"message": {"content": "OK"}}],
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text = _provider_text(
        "system",
        "user",
        LLMConfig(provider="openai", base_url="https://api.openai.com/v1", api_key="sk-test", model="gpt-5.5", temperature=0.2),
    )
    assert text == "OK"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["content"] == "user"


def test_text_anthropic_provider_request_shape(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({
            "content": [{"type": "text", "text": "CLAUDE"}],
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text = _provider_text(
        "system",
        "user",
        LLMConfig(provider="anthropic", base_url="https://api.anthropic.com", api_key="ant-key", model="claude-sonnet-4-5", temperature=0.1),
    )
    assert text == "CLAUDE"
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "ant-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["system"] == "system"
    assert captured["body"]["messages"] == [{"role": "user", "content": "user"}]


def test_text_gemini_provider_request_shape(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "GEMINI"}]}}],
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text = _provider_text(
        "system",
        "user",
        LLMConfig(provider="gemini", base_url="https://generativelanguage.googleapis.com/v1beta", api_key="gem-key", model="gemini-2.0-flash", temperature=0.3),
    )
    assert text == "GEMINI"
    assert "models/gemini-2.0-flash:generateContent" in captured["url"]
    assert "key=gem-key" in captured["url"]
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "system"
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "user"


def test_image_gemini_provider_writes_file(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({
            "predictions": [{"bytesBase64Encoded": "aGVsbG8="}],
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = tmp_path / "out.png"
    generate_image(
        "a blue dot",
        ImageConfig(
            provider="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="gem-key",
            model="imagen-3.0-generate-002",
            size="9:16",
        ),
        out,
    )
    assert out.read_bytes() == b"hello"
    assert "models/imagen-3.0-generate-002:predict" in captured["url"]
    assert "key=gem-key" in captured["url"]
    assert captured["body"]["instances"][0]["prompt"] == "a blue dot"
    assert captured["body"]["parameters"]["aspectRatio"] == "9:16"


def test_image_anthropic_provider_rejected():
    with pytest.raises(ImageError, match="Anthropic"):
        check_image_connection(ImageConfig(provider="anthropic", api_key="x", base_url="https://api.anthropic.com", model="claude"))
