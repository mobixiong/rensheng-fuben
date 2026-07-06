import io
import json

from app.doubao_voices import DOUBAO_TTS_2_0_DEFAULT_VOICE_ID
from app.tts_adapter import DOUBAO_TTS_RESOURCE_ID, DOUBAO_TTS_SPEAKER, TtsConfig, _doubao_tts, _iter_json_objects_from_stream


def test_doubao_config_ignores_minimax_schema_defaults():
    cfg = TtsConfig.from_payload({
        "tts_provider": "doubao",
        "tts_model": "speech-2.8-hd",
        "tts_voice_id": "male-qn-qingse",
    })

    assert cfg.provider == "doubao"
    assert cfg.model == DOUBAO_TTS_RESOURCE_ID
    assert cfg.voice_id == DOUBAO_TTS_SPEAKER


def test_volcengine_alias_maps_to_doubao():
    cfg = TtsConfig.from_payload({"tts_provider": "volcengine"})

    assert cfg.provider == "doubao"


def test_iter_json_objects_from_stream_handles_concatenated_json():
    stream = io.BytesIO(b'{"code":0,"data":"abc"}\n{"code":20000000,"data":null}')

    assert list(_iter_json_objects_from_stream(stream)) == [
        {"code": 0, "data": "abc"},
        {"code": 20000000, "data": None},
    ]


def test_doubao_tts_serializes_additions_as_string(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self._chunks = [b'{"code":0,"data":"QQ=="}']

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size=-1):
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    _doubao_tts(
        "试听文本",
        tmp_path / "preview.mp3",
        TtsConfig(provider="doubao", api_key="key", model="volc.service_type.10029", voice_id="speaker", pitch=2),
    )

    additions = captured["payload"]["req_params"]["additions"]
    assert isinstance(additions, str)
    assert json.loads(additions) == {
        "disable_markdown_filter": True,
        "enable_language_detector": True,
        "enable_latex_tn": True,
        "disable_default_bit_rate": True,
        "max_length_to_filter_parenthesis": 0,
        "cache_config": {"text_type": 1, "use_cache": True},
        "post_process": {"pitch": 2},
    }


def test_doubao_tts_sends_default_additions_as_string(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def __init__(self):
            self._chunks = [b'{"code":0,"data":"QQ=="}']

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size=-1):
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    _doubao_tts(
        "试听文本",
        tmp_path / "preview.mp3",
        TtsConfig(provider="doubao", api_key="key", model="volc.service_type.10029", voice_id="speaker"),
    )

    additions = captured["payload"]["req_params"]["additions"]
    assert isinstance(additions, str)
    assert json.loads(additions) == {
        "disable_markdown_filter": True,
        "enable_language_detector": True,
        "enable_latex_tn": True,
        "disable_default_bit_rate": True,
        "max_length_to_filter_parenthesis": 0,
        "cache_config": {"text_type": 1, "use_cache": True},
    }


def test_doubao_config_keeps_seed_resource_ids():
    cfg = TtsConfig.from_payload({
        "tts_provider": "doubao",
        "tts_model": "seed-tts-2.0",
    })

    assert cfg.model == "seed-tts-2.0"
    assert cfg.voice_id == DOUBAO_TTS_2_0_DEFAULT_VOICE_ID
