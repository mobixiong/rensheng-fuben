export const $ = (id) => document.getElementById(id);

export function createUi() {
  const els = {
    editor: $("jsonEditor"),
    status: $("status"),
    result: $("result"),
    preview: $("preview"),
    openVideo: $("openVideo"),
    editJianying: $("editJianying"),
    renderProgress: $("renderProgress"),
    renderProgressBar: $("renderProgressBar"),
    renderProgressText: $("renderProgressText"),
    renderProgressPercent: $("renderProgressPercent"),
    autoBrief: $("autoBrief"),
    autoCopyPreset: $("autoCopyPreset"),
    autoStoryboardGranularity: $("autoStoryboardGranularity"),
    autoImageSize: $("autoImageSize"),
    autoIntroTemplate: $("autoIntroTemplate"),
    autoTtsPreset: $("autoTtsPreset"),
    autoOptimizeImagePrompts: $("autoOptimizeImagePrompts"),
    autoInfiniteImageRetry: $("autoInfiniteImageRetry"),
    autoRenderAfterImages: $("autoRenderAfterImages"),
    autoPipelineStatus: $("autoPipelineStatus"),
    autoPipelineCurrent: $("autoPipelineCurrent"),
    autoPipelinePercent: $("autoPipelinePercent"),
    autoPipelineProgressBar: $("autoPipelineProgressBar"),
    autoPipelineSteps: $("autoPipelineSteps"),
    autoPipelineResult: $("autoPipelineResult"),
    introPreviewModal: $("introPreviewModal"),
    introPreviewBackdrop: $("introPreviewBackdrop"),
    introPreviewGrid: $("introPreviewGrid"),
    jsonMeta: $("jsonMeta"),
    shotGrid: $("shotGrid"),
    selectedShotLabel: $("selectedShotLabel"),
    copyPromptPreset: $("copyPromptPreset"),
    copyPrompt: $("copyPrompt"),
    copyOutput: $("copyOutput"),
    copyPromptMeta: $("copyPromptMeta"),
    copyMeta: $("copyMeta"),
    storyboardGranularity: $("storyboardGranularity"),
    copyToStoryPrompt: $("copyToStoryPrompt"),
    copyToStoryPromptMeta: $("copyToStoryPromptMeta"),
    imageStylePreset: $("imageStylePreset"),
    imagePrompt: $("imagePrompt"),
    imagePromptMeta: $("imagePromptMeta"),
    improveImagePrompt: $("improveImagePrompt"),
    improveImagePromptMeta: $("improveImagePromptMeta"),
    settingsDrawer: $("settingsDrawer"),
    settingsBackdrop: $("settingsBackdrop"),
    textConnectionResult: $("textConnectionResult"),
    imageConnectionResult: $("imageConnectionResult"),
    projectLabel: $("projectLabel"),
    projectSaveMeta: $("projectSaveMeta"),
    projectPicker: $("projectPicker"),
    projectGrid: $("projectGrid"),
    assetCollectionName: $("assetCollectionName"),
    assetCollectionDescription: $("assetCollectionDescription"),
    createAssetCollection: $("createAssetCollection"),
    assetCollectionPicker: $("assetCollectionPicker"),
    assetCollectionMeta: $("assetCollectionMeta"),
    assetUploadFile: $("assetUploadFile"),
    assetName: $("assetName"),
    assetType: $("assetType"),
    assetDescription: $("assetDescription"),
    assetTags: $("assetTags"),
    uploadReferenceAsset: $("uploadReferenceAsset"),
    assetGrid: $("assetGrid"),
    projectReferenceCollection: $("projectReferenceCollection"),
    autoReferenceEnabled: $("autoReferenceEnabled"),
    themeCopyPreset: $("themeCopyPreset"),
    themeBrief: $("themeBrief"),
    themeIdeaCandidates: $("themeIdeaCandidates"),
    themeIdeaPrompt: $("themeIdeaPrompt"),
    themeIdeaPromptMeta: $("themeIdeaPromptMeta"),
    themeIntro: $("themeIntro"),
    themeIntroMeta: $("themeIntroMeta"),
    themeIntroMirror: $("themeIntroMirror"),
    themeRevision: $("themeRevision"),
    topic: $("topic"),
    topicMirror: $("topicMirror"),
    textProvider: $("textProvider"),
    baseUrl: $("baseUrl"),
    model: $("model"),
    apiKey: $("apiKey"),
    imageProvider: $("imageProvider"),
    imageBaseUrl: $("imageBaseUrl"),
    imageModel: $("imageModel"),
    imageApiKey: $("imageApiKey"),
    imageSize: $("imageSize"),
    introTemplate: $("introTemplate"),
    introImageSeconds: $("introImageSeconds"),
    ttsPreset: $("ttsPreset"),
    bgmSelect: $("bgmSelect"),
    bgmUploadFile: $("bgmUploadFile"),
    introSfxSelect: $("introSfxSelect"),
    introSfxUploadFile: $("introSfxUploadFile"),
    ttsProvider: $("ttsProvider"),
    ttsBaseUrl: $("ttsBaseUrl"),
    ttsApiKey: $("ttsApiKey"),
    ttsGroupId: $("ttsGroupId"),
    ttsModel: $("ttsModel"),
    ttsVoiceId: $("ttsVoiceId"),
    ttsSpeed: $("ttsSpeed"),
    ttsEmotion: $("ttsEmotion"),
    ttsLanguageBoost: $("ttsLanguageBoost"),
    ttsPreviewResult: $("ttsPreviewResult"),
    ttsPreviewAudio: $("ttsPreviewAudio"),
    voice: $("voice"),
    rate: $("rate"),
  };

  function setStatus(text, kind = "") {
    els.status.textContent = text;
    els.status.className = `status-pill ${kind}`.trim();
  }

  function setBusy(busy) {
    for (const id of [
      "loadExample",
      "startAutoPipeline",
      "cancelAutoPipeline",
      "generateTheme",
      "generateThemeIdeas",
      "rerollThemeIdeas",
      "rerollTheme",
      "reviseTheme",
      "goCopyFromTheme",
      "themeCopyPreset",
      "generate",
      "generateCopy",
      "buildStoryboard",
      "generateImages",
      "redrawSelected",
      "validate",
      "render",
      "exportJianying",
      "editJianying",
      "previewIntroTemplates",
      "refreshGallery",
      "copyPromptPreset",
      "resetCopyPrompt",
      "resetCopyToStoryPrompt",
      "imageStylePreset",
      "resetImagePrompt",
      "resetImproveImagePrompt",
      "resetThemeIdeaPrompt",
      "testTextConnection",
      "testImageConnection",
      "saveProject",
      "newProject",
      "projectPicker",
      "createAssetCollection",
      "assetCollectionPicker",
      "assetUploadFile",
      "assetName",
      "assetType",
      "assetDescription",
      "assetTags",
      "uploadReferenceAsset",
      "projectReferenceCollection",
      "autoReferenceEnabled",
      "introTemplate",
      "introImageSeconds",
      "ttsPreset",
      "bgmSelect",
      "bgmUploadFile",
      "uploadBgm",
      "introSfxSelect",
      "introSfxUploadFile",
      "uploadIntroSfx",
      "ttsProvider",
      "ttsBaseUrl",
      "ttsApiKey",
      "ttsGroupId",
      "ttsModel",
      "ttsVoiceId",
      "ttsSpeed",
      "ttsEmotion",
      "ttsLanguageBoost",
      "previewTts",
    ]) {
      const el = $(id);
      if (el) el.disabled = busy;
    }
  }

  function setTestResult(el, text, kind = "") {
    if (!el) return;
    el.textContent = text;
    el.className = `test-result ${kind}`.trim();
  }

  function setProjectMeta(label, detail = "") {
    if (els.projectLabel) els.projectLabel.textContent = label || "未保存项目";
    if (els.projectSaveMeta) els.projectSaveMeta.textContent = detail || "自动保存开启";
  }

  function openSettings() {
    if (!els.settingsBackdrop || !els.settingsDrawer) {
      setTab("settings");
      return;
    }
    els.settingsBackdrop.hidden = false;
    els.settingsDrawer.classList.add("open");
    els.settingsDrawer.setAttribute("aria-hidden", "false");
  }

  function closeSettings() {
    if (!els.settingsBackdrop || !els.settingsDrawer) return;
    els.settingsDrawer.classList.remove("open");
    els.settingsDrawer.setAttribute("aria-hidden", "true");
    els.settingsBackdrop.hidden = true;
  }

  function setTab(tab) {
    for (const button of document.querySelectorAll(".tab-button")) {
      button.classList.toggle("active", button.dataset.tab === tab);
      button.setAttribute("aria-selected", String(button.dataset.tab === tab));
    }
    for (const panel of document.querySelectorAll(".tab-view")) {
      panel.classList.toggle("active", panel.id === `tab-${tab}`);
    }
  }

  return {
    els,
    setStatus,
    setBusy,
    setTestResult,
    setProjectMeta,
    openSettings,
    closeSettings,
    setTab,
  };
}
