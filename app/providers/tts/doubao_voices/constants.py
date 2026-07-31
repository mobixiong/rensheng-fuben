from __future__ import annotations

import copy
from typing import Any


DOUBAO_TTS_VOICE_DOC_URL = "https://www.volcengine.com/docs/6561/1257544?lang=zh"
DOUBAO_TTS_VOICE_DOC_API = "https://www.volcengine.com/api/doc/getDocDetail?LibraryID=6561&DocumentID=1257544&lang=zh&type="

DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID = "volc.service_type.10029"
DOUBAO_TTS_1_0_RESOURCE_ID = "seed-tts-1.0"
DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID = "seed-tts-1.0-concurr"
DOUBAO_TTS_2_0_RESOURCE_ID = "seed-tts-2.0"

DOUBAO_TTS_1_0_DEFAULT_VOICE_ID = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"
DOUBAO_TTS_2_0_DEFAULT_VOICE_ID = "zh_female_vv_uranus_bigtts"

_CACHE_TTL_SECONDS = 6 * 60 * 60

_VOICE_LIST_TEXT = "音色列表"
_TTS_1_0_TEXT = "豆包语音合成模型1.0"
_TTS_2_0_TEXT = "豆包语音合成模型2.0"
_MULTILINGUAL_TEXT = "多语种"
_REALTIME_TEXT = "端到端实时语音大模型"

_SCENE_HEADER = "场景"
_NAME_HEADER = "音色名称"
_LANGUAGE_HEADER = "语种"
_LANGUAGE_DIALECT_HEADER = "语种/方言"
_CAPABILITIES_HEADER = "支持能力"
_EMOTIONS_HEADER = "支持的情感"
_TAGS_HEADER = "特殊标签"
_COUNTERPART_HEADER = "对应2.0音色"
_MIX_HEADER = "是否支持MIX"
_INFERENCE_MODE_HEADER = "推荐推理模式"
_NOTES_HEADER = "备注"

_FIELD_ALIASES = {
    _SCENE_HEADER: "scene",
    _NAME_HEADER: "name",
    "voice_type": "id",
    _LANGUAGE_HEADER: "language",
    _LANGUAGE_DIALECT_HEADER: "language",
    _CAPABILITIES_HEADER: "capabilities",
    _EMOTIONS_HEADER: "emotions",
    _TAGS_HEADER: "tags",
    _COUNTERPART_HEADER: "counterpart_2_0",
    _MIX_HEADER: "supports_mix",
    _INFERENCE_MODE_HEADER: "recommended_inference_mode",
    _NOTES_HEADER: "notes",
}

_GROUP_DEFINITIONS = {
    "doubao-tts-2.0": {
        "id": "doubao-tts-2.0",
        "model": "doubao-tts-2.0",
        "resource_ids": [DOUBAO_TTS_2_0_RESOURCE_ID],
        "tts_compatible": True,
    },
    "doubao-tts-2.0-multilingual": {
        "id": "doubao-tts-2.0-multilingual",
        "model": "doubao-tts-2.0",
        "resource_ids": [DOUBAO_TTS_2_0_RESOURCE_ID],
        "tts_compatible": True,
    },
    "doubao-realtime-s2s-sc-2.0": {
        "id": "doubao-realtime-s2s-sc-2.0",
        "model": "doubao-realtime-s2s-sc-2.0",
        "resource_ids": [],
        "tts_compatible": False,
    },
    "doubao-tts-1.0": {
        "id": "doubao-tts-1.0",
        "model": "doubao-tts-1.0",
        "resource_ids": [
            DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
            DOUBAO_TTS_1_0_RESOURCE_ID,
            DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID,
        ],
        "tts_compatible": True,
    },
}

DOUBAO_TTS_RESOURCE_MODELS = [
    {
        "value": DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID} (legacy 1.0)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_2_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_2_0_RESOURCE_ID} (2.0)",
        "voice_groups": ["doubao-tts-2.0", "doubao-tts-2.0-multilingual"],
        "default_voice_id": DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_1_0_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_1_0_RESOURCE_ID} (1.0)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
    {
        "value": DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID,
        "label": f"{DOUBAO_TTS_1_0_CONCURR_RESOURCE_ID} (1.0 concurrent)",
        "voice_groups": ["doubao-tts-1.0"],
        "default_voice_id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
        "selectable": True,
    },
]

_FALLBACK_GROUPS = [
    {
        **_GROUP_DEFINITIONS["doubao-tts-1.0"],
        "title": "Doubao TTS 1.0",
        "voices": [
            {
                "id": DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
                "name": "Beijing Xiaoye",
                "scene": "multi emotion",
                "language": "Chinese",
            }
        ],
    },
    {
        **_GROUP_DEFINITIONS["doubao-tts-2.0"],
        "title": "Doubao TTS 2.0",
        "voices": [
            {
                "id": DOUBAO_TTS_2_0_DEFAULT_VOICE_ID,
                "name": "Vivi 2.0",
                "scene": "general",
                "language": "Chinese",
            },
            {
                "id": "zh_female_jiaochuannv_uranus_bigtts",
                "name": "Jiaochuan Female 2.0",
                "scene": "general",
                "language": "Chinese",
            },
        ],
    },
]
