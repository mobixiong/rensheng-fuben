import { createConnectionWorkflow } from "./workflow-connection.js";
import { createCopyWorkflow } from "./workflow-copy.js";
import { createImageWorkflow } from "./workflow-image.js";
import { createMediaWorkflow } from "./workflow-media.js";
import { createRenderWorkflow } from "./workflow-render.js";
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
    ...createConnectionWorkflow(context),
    ...createThemeWorkflow(context),
    ...createCopyWorkflow(context),
    ...createImageWorkflow(context),
    ...createMediaWorkflow(context),
    ...createRenderWorkflow(context),
  };
}
