import { createAutoPipelineWorkflow } from "./workflow-auto-pipeline.js?v=20260703_auto_loop";
import { createConnectionWorkflow } from "./workflow-connection.js?v=20260706_tts_preview";
import { createCopyWorkflow } from "./workflow-copy.js";
import { createImageWorkflow } from "./workflow-image.js?v=20260702_image_poll_fix";
import { createMediaWorkflow } from "./workflow-media.js?v=20260703_intro_preview_ratio";
import { createRenderWorkflow } from "./workflow-render.js?v=20260705_doubao_tts";
import { createThemeWorkflow } from "./workflow-theme.js";
import { DEFAULT_IMAGE_SIZE } from "./constants.js";

export function createWorkflow({ els, ui, api, settings, storyView, projectStore, state, setActiveTab }) {
  function currentStoryImageSize() {
    return els.imageSize?.value?.trim() || DEFAULT_IMAGE_SIZE;
  }

  function withCurrentImageSize(story) {
    return storyView.withImageSize(story, currentStoryImageSize());
  }

  const context = {
    els,
    ui,
    api,
    settings,
    storyView,
    projectStore,
    state,
    setActiveTab,
    withCurrentImageSize,
  };

  return {
    ...createAutoPipelineWorkflow(context),
    ...createConnectionWorkflow(context),
    ...createThemeWorkflow(context),
    ...createCopyWorkflow(context),
    ...createImageWorkflow(context),
    ...createMediaWorkflow(context),
    ...createRenderWorkflow(context),
  };
}
