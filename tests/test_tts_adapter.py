import io

from app.tts_adapter import DOUBAO_TTS_RESOURCE_ID, DOUBAO_TTS_SPEAKER, TtsConfig, _iter_json_objects_from_stream


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
