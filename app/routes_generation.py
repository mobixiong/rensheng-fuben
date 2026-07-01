from typing import Any

from fastapi import APIRouter, HTTPException

from .image_adapter import ImageConfig, ImageError, generate_one_story_image, generate_story_images, test_image_connection
from .llm_adapter import (
    LLMConfig,
    LLMError,
    generate_story,
    generate_story_from_copy,
    generate_text,
    generate_topic_plan,
    improve_image_prompt,
    revise_topic_plan,
    test_text_connection,
)
from .schemas import (
    CopyToStoryRequest,
    GenerateRequest,
    ImageConnectionRequest,
    ImageGenerateRequest,
    ImageRegenerateRequest,
    ImproveImagePromptRequest,
    TextConnectionRequest,
    ThemePlanRequest,
    ThemeReviseRequest,
)


router = APIRouter()


def image_error_response(exc: ImageError) -> HTTPException:
    return HTTPException(status_code=400, detail=exc.to_detail())


@router.post("/api/text/generate-copy")
def text_generate_copy(req: GenerateRequest) -> dict[str, str]:
    try:
        text = generate_text(req.topic, LLMConfig.from_payload(req.model_dump()), req.system_prompt, req.topic_intro)
        return {"topic": req.topic, "topic_intro": req.topic_intro, "text": text}
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/text/generate-theme")
def text_generate_theme(req: ThemePlanRequest) -> dict[str, str]:
    try:
        return generate_topic_plan(req.brief, LLMConfig.from_payload(req.model_dump()), req.system_prompt)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/text/revise-theme")
def text_revise_theme(req: ThemeReviseRequest) -> dict[str, str]:
    try:
        return revise_topic_plan(
            req.brief,
            req.topic,
            req.intro,
            req.instruction,
            LLMConfig.from_payload(req.model_dump()),
            req.system_prompt,
        )
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/settings/test-text")
def settings_test_text(req: TextConnectionRequest) -> dict[str, Any]:
    try:
        return test_text_connection(LLMConfig.from_payload(req.model_dump()))
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/settings/test-image")
def settings_test_image(req: ImageConnectionRequest) -> dict[str, Any]:
    try:
        return test_image_connection(ImageConfig.from_payload(req.model_dump()))
    except ImageError as exc:
        raise image_error_response(exc) from exc


@router.post("/api/text/copy-to-story")
def text_copy_to_story(req: CopyToStoryRequest) -> dict[str, Any]:
    try:
        return generate_story_from_copy(req.topic, req.copy_text, LLMConfig.from_payload(req.model_dump()), req.system_prompt, req.topic_intro)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/text/improve-image-prompt")
def text_improve_image_prompt(req: ImproveImagePromptRequest) -> dict[str, Any]:
    try:
        return improve_image_prompt(req.story, req.shot_index, LLMConfig.from_payload(req.model_dump()), req.system_prompt)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/text/generate")
def text_generate(req: GenerateRequest) -> dict[str, Any]:
    try:
        return generate_story(req.topic, LLMConfig.from_payload(req.model_dump()), req.system_prompt, req.topic_intro)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/llm/generate")
def llm_generate(req: GenerateRequest) -> dict[str, Any]:
    return text_generate(req)


@router.post("/api/image/generate-story")
def image_generate_story(req: ImageGenerateRequest) -> dict[str, Any]:
    try:
        return generate_story_images(req.story, ImageConfig.from_payload(req.model_dump()), req.fixed_prompt)
    except ImageError as exc:
        raise image_error_response(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/image/regenerate-shot")
def image_regenerate_shot(req: ImageRegenerateRequest) -> dict[str, Any]:
    try:
        return generate_one_story_image(req.story, req.shot_index, ImageConfig.from_payload(req.model_dump()), req.fixed_prompt)
    except ImageError as exc:
        raise image_error_response(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
