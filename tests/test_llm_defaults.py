import pytest

from app.image_adapter import ImageConfig, ImageError, _openai_image_response
from app.llm_adapter import LLMConfig, LLMError, _chat_text


def test_text_config_defaults_and_missing_key_message(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    cfg = LLMConfig.from_payload({})

    assert cfg.base_url == "http://43.131.249.187:3000/v1"
    assert cfg.model == "gpt-5.5"
    with pytest.raises(LLMError, match="密钥未填写，密钥是群号"):
        _chat_text("system", "user", cfg)


def test_image_config_defaults_and_missing_key_message(monkeypatch):
    monkeypatch.delenv("IMAGE_BASE_URL", raising=False)
    monkeypatch.delenv("IMAGE_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)

    cfg = ImageConfig.from_payload({})

    assert cfg.base_url == "http://43.131.249.187:3000/v1"
    assert cfg.model == "gpt-image-2"
    with pytest.raises(ImageError, match="密钥未填写，密钥是群号"):
        _openai_image_response("test", cfg)
