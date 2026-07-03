from typing import Any

from fastapi import APIRouter, HTTPException

from .image_jobs import cancel_image_job, create_image_job, get_image_job, list_project_jobs
from .image_adapter import ImageConfig, ImageError, generate_one_story_image, generate_story_images, test_image_connection
from .llm_adapter import (
    LLMConfig,
    LLMError,
    generate_story,
    generate_story_from_copy,
    generate_text,
    generate_theme_ideas,
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
    ImageJobCreateRequest,
    ImageRegenerateRequest,
    ImproveImagePromptRequest,
    TextConnectionRequest,
    ThemePlanRequest,
    ThemeIdeasRequest,
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


@router.post("/api/text/generate-theme-ideas")
def text_generate_theme_ideas(req: ThemeIdeasRequest) -> dict[str, Any]:
    try:
        return generate_theme_ideas(
            req.brief,
            LLMConfig.from_payload(req.model_dump()),
            req.system_prompt,
            count=req.count,
            instruction=req.instruction,
        )
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
        return generate_story_from_copy(
            req.topic,
            req.copy_text,
            LLMConfig.from_payload(req.model_dump()),
            req.system_prompt,
            req.topic_intro,
            req.storyboard_granularity,
        )
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


@router.post("/api/image/jobs")
def image_job_create(req: ImageJobCreateRequest) -> dict[str, Any]:
    try:
        job = create_image_job(
            req.story,
            ImageConfig.from_payload(req.model_dump()),
            fixed_prompt=req.fixed_prompt,
            mode=req.mode,
            shot_indexes=req.shot_indexes,
            concurrency=req.concurrency,
            project_id=req.project_id,
            reference_collection_id=req.reference_collection_id,
            auto_reference_enabled=req.auto_reference_enabled,
            reference_llm_cfg=LLMConfig(
                provider=req.reference_provider,
                base_url=req.reference_base_url,
                api_key=req.reference_api_key,
                model=req.reference_model,
                temperature=req.reference_temperature,
            ),
        )
        return {"job": job}
    except ImageError as exc:
        raise image_error_response(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/image/jobs")
def image_jobs_list(project_id: str, active_only: bool = False) -> dict[str, Any]:
    try:
        return {"jobs": list_project_jobs(project_id, active_only=active_only)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/image/jobs/{project_id}/{job_id}")
def image_job_get(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        return {"job": get_image_job(project_id, job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Image job not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/image/jobs/{project_id}/{job_id}/cancel")
def image_job_cancel(project_id: str, job_id: str) -> dict[str, Any]:
    try:
        return {"job": cancel_image_job(project_id, job_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Image job not found: {exc}") from exc
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
