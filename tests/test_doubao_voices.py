from app.doubao_voices import (
    DOUBAO_TTS_1_0_DEFAULT_VOICE_ID,
    DOUBAO_TTS_2_0_RESOURCE_ID,
    DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID,
    parse_doubao_voice_groups,
)


SAMPLE_DOC = """
##  **"豆包语音合成模型2.0" 音色列表**

|**场景** |**音色名称** |**voice_type** |**语种/方言** |**支持能力** |**特殊标签** |
|---|---|---|---|---|---|
|通用场景 |Vivi 2.0 |zh_female_vv_uranus_bigtts |中文 |指令遵循 | |
|通用场景 |娇喘女声 2.0 |zh_female_jiaochuannv_uranus_bigtts |中文 |指令遵循 |抖音同款 |

##  **"豆包语音合成模型2.0" 多语种音色列表**

|**场景** |**音色名称** |**voice_type** |**语种/方言** |**推荐推理模式** |**支持能力** |**备注** |
|---|---|---|---|---|---|---|
|多语种,阿拉伯语 |Dina |ar_female_dina_uranus_bigtts |阿拉伯语 |QA |情感变化、指令遵循 | |

## "端到端实时语音大模型 S2S\\-O版本和SC\\-2.0版本 "音色列表

|**场景** |**音色名称** |**voice_type** |**语种** |
|---|---|---|---|
|S2S\\-Omni |vivi |zh_female_vv_jupiter_bigtts |中文 |
|SC 2.0版本 |傲娇女友 |saturn_zh_female_aojiaonvyou_tob |中文 |

##  **"豆包语音合成模型1.0" 音色列表**

|**场景** |**音色名称** |**voice_type** |**语种** |**支持的情感** |**特殊标签** |**对应2.0音色** |**是否支持MIX** |
|---|---|---|---|---|---|---|---|
|多情感 |冷酷哥哥（多情感） |zh_male_lengkugege_emo_v2_mars_bigtts |中文 |中性 | | |否 |
||北京小爷（多情感） |zh_male_beijingxiaoye_emo_v2_mars_bigtts |中文 |中性 | | |否 |
"""


def test_parse_doubao_voice_groups_keeps_model_boundaries():
    groups = {group["id"]: group for group in parse_doubao_voice_groups(SAMPLE_DOC)}

    assert set(groups) == {
        "doubao-tts-2.0",
        "doubao-tts-2.0-multilingual",
        "doubao-realtime-s2s-sc-2.0",
        "doubao-tts-1.0",
    }
    assert groups["doubao-tts-2.0"]["resource_ids"] == [DOUBAO_TTS_2_0_RESOURCE_ID]
    assert DOUBAO_TTS_LEGACY_1_0_RESOURCE_ID in groups["doubao-tts-1.0"]["resource_ids"]

    tts_2_voice_ids = {voice["id"] for voice in groups["doubao-tts-2.0"]["voices"]}
    tts_1_voice_ids = {voice["id"] for voice in groups["doubao-tts-1.0"]["voices"]}
    assert "zh_female_jiaochuannv_uranus_bigtts" in tts_2_voice_ids
    assert DOUBAO_TTS_1_0_DEFAULT_VOICE_ID in tts_1_voice_ids
    assert "zh_female_jiaochuannv_uranus_bigtts" not in tts_1_voice_ids


def test_parse_doubao_voice_groups_preserves_blank_scene_rows():
    groups = {group["id"]: group for group in parse_doubao_voice_groups(SAMPLE_DOC)}
    default_voice = next(
        voice for voice in groups["doubao-tts-1.0"]["voices"] if voice["id"] == DOUBAO_TTS_1_0_DEFAULT_VOICE_ID
    )

    assert default_voice["scene"] == "多情感"
    assert default_voice["supports_mix"] is False
