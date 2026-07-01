from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1)
    topic_intro: str = ""
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8
    system_prompt: str | None = None


class CopyToStoryRequest(GenerateRequest):
    copy_text: str = Field(min_length=1)


class ThemePlanRequest(BaseModel):
    brief: str = Field(min_length=1)
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    system_prompt: str | None = None


class ThemeReviseRequest(ThemePlanRequest):
    topic: str = Field(min_length=1)
    intro: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class TextConnectionRequest(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0


class ImageGenerateRequest(BaseModel):
    story: dict[str, Any]
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "9:16"
    fixed_prompt: str | None = None


class ImageRegenerateRequest(ImageGenerateRequest):
    shot_index: int = Field(ge=0)


class ImageConnectionRequest(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    size: str = "9:16"


class ImproveImagePromptRequest(BaseModel):
    story: dict[str, Any]
    shot_index: int = Field(ge=0)
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.4


class RenderRequest(BaseModel):
    story: dict[str, Any]
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+12%"
    tts_provider: str = ""
    tts_base_url: str = ""
    tts_api_key: str = ""
    tts_group_id: str = ""
    tts_model: str = "speech-2.8-hd"
    tts_voice_id: str = "male-qn-qingse"
    tts_speed: float = 1.0
    tts_volume: float = 1.0
    tts_pitch: int = 0
    tts_emotion: str = ""
    tts_language_boost: str = "Chinese"
    project_id: str | None = None
    cleanup_intermediate: bool = True
    intro_template: str = "none"
    intro_image_seconds: float = 0.3
    tts_preset: str = "custom"
    bgm_id: str = "none"
    intro_sfx_id: str = "default"


class IntroPreviewRequest(BaseModel):
    story: dict[str, Any]
    project_id: str | None = None
    templates: list[str] | None = None
    duration: float = 3.0
    image_seconds: float = 0.3


class ProjectActivateRequest(BaseModel):
    project_id: str = Field(min_length=1)
