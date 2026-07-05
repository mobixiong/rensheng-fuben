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
    storyboard_granularity: str = "balanced"


class ThemePlanRequest(BaseModel):
    brief: str = Field(min_length=1)
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    system_prompt: str | None = None


class ThemeIdeasRequest(BaseModel):
    brief: str = ""
    provider: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.8
    system_prompt: str | None = None
    count: int = Field(default=6, ge=1, le=12)
    instruction: str = ""


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


class ImageJobCreateRequest(ImageGenerateRequest):
    project_id: str = ""
    mode: str = "generate_missing"
    shot_indexes: list[int] | None = None
    concurrency: int = Field(default=100, ge=1, le=100)
    reference_collection_id: str = ""
    auto_reference_enabled: bool = False
    reference_provider: str = "openai"
    reference_base_url: str = ""
    reference_api_key: str = ""
    reference_model: str = ""
    reference_temperature: float = 0


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
    system_prompt: str | None = None


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
    force_render: bool = False
    intro_template: str = "none"
    intro_image_seconds: float = 0.3
    image_size: str = "9:16"
    tts_preset: str = "custom"
    bgm_id: str = "none"
    intro_sfx_id: str = "default"


class JianyingDraftRequest(RenderRequest):
    draft_name: str = ""
    replace_draft: bool = False


class JianyingOpenRequest(BaseModel):
    draft_dir: str = Field(min_length=1)


class TtsPreviewRequest(BaseModel):
    text: str = "今天体验的人生副本，是一次新的开始。"
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


class IntroPreviewRequest(BaseModel):
    story: dict[str, Any]
    project_id: str | None = None
    templates: list[str] | None = None
    duration: float = 3.0
    image_seconds: float = 0.3
    image_size: str = "9:16"


class AutoPipelineRequest(BaseModel):
    project_id: str = ""
    brief: str = ""
    copy_preset: str = "random"
    image_size: str = "9:16"
    reference_collection_id: str = ""
    auto_reference_enabled: bool = False
    intro_template: str = "none"
    intro_image_seconds: float = 0.3
    tts_preset: str = "custom"
    voice: str = "zh-CN-YunxiNeural"
    rate: str = "+12%"
    tts_speed: float = 1.0
    tts_emotion: str = ""
    tts_language_boost: str = "Chinese"
    bgm_id: str = "none"
    intro_sfx_id: str = "default"
    auto_optimize_image_prompts: bool = True
    render_after_images: bool = True
    auto_infinite_image_retry: bool = False
    image_concurrency: int = Field(default=100, ge=1, le=100)
    storyboard_granularity: str = "balanced"
    theme_idea_prompt: str = ""
    copy_prompt: str = ""
    copy_to_story_prompt: str = ""
    image_prompt: str = ""
    improve_image_prompt: str = ""
    text_config: dict[str, Any] = Field(default_factory=dict)
    image_config: dict[str, Any] = Field(default_factory=dict)
    tts_config: dict[str, Any] = Field(default_factory=dict)


class ProjectActivateRequest(BaseModel):
    project_id: str = Field(min_length=1)


class ProjectDeleteRequest(BaseModel):
    project_id: str = Field(min_length=1)


class ReferenceCollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
