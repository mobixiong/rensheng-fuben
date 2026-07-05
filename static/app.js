import * as api from "./js/api.js";
import { $ , createUi } from "./js/ui.js";
import { createSettings } from "./js/settings.js?v=20260706_tts_preview";
import { createStoryView } from "./js/story-view.js";
import { createProjectStore } from "./js/project-store.js?v=20260706_jianying_edit";
import { createReferenceAssets } from "./js/reference-assets.js";
import { createWorkflow } from "./js/workflow.js?v=20260706_jianying_edit";
import { createThemeWorkflow } from "./js/workflow-theme.js?v=20260702_theme_direction_fix";

const ui = createUi();
const { els } = ui;

const state = {
  activeTab: "theme",
  selectedShots: new Set(),
  saveTimer: 0,
  restoringProject: false,
  currentProjectId: "",
  imageGenerationActive: false,
  activeImageJobs: new Map(),
  imageJobPollers: new Map(),
  imageJobPollingToken: 0,
  activeAutoPipelineJob: null,
  autoPipelineContinuous: false,
  autoPipelineLoopRunning: false,
  autoPipelinePlaybackToken: 0,
  projectSaveQueue: Promise.resolve(),
  referenceCollectionId: "",
  autoReferenceEnabled: false,
};

let projectStore;
let shotClickTimer = 0;

const layoutKeys = {
  sidebar: "lifeCopy.sidebarCollapsed",
  topbar: "lifeCopy.topbarExpanded",
  imagePrompt: "lifeCopy.imagePromptExpanded",
};

function on(target, type, handler, options) {
  const element = typeof target === "string" ? $(target) : target;
  element?.addEventListener(type, handler, options);
  return element;
}

function onEach(ids, type, handler, options) {
  for (const id of ids) on(id, type, handler, options);
}

function readLayoutFlag(key, fallback = false) {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

function writeLayoutFlag(key, value) {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // Local storage can be unavailable in restricted browser modes.
  }
}

function setSidebarCollapsed(collapsed, persist = true) {
  document.querySelector(".app-frame")?.classList.toggle("sidebar-collapsed", collapsed);
  $("sidebarToggle")?.setAttribute("aria-pressed", String(collapsed));
  $("sidebarToggle")?.setAttribute("aria-label", collapsed ? "展开侧边栏" : "收起侧边栏");
  if (persist) writeLayoutFlag(layoutKeys.sidebar, collapsed);
}

function setTopbarExpanded(expanded, persist = true) {
  const topbar = $("projectTopbar");
  topbar?.classList.toggle("is-expanded", expanded);
  topbar?.classList.toggle("is-collapsed", !expanded);
  $("topbarToggle")?.setAttribute("aria-expanded", String(expanded));
  if (persist) writeLayoutFlag(layoutKeys.topbar, expanded);
}

function setImagePromptExpanded(expanded, persist = true) {
  const panel = $("imagePromptPanel");
  $("tab-image")?.classList.toggle("image-prompt-collapsed", !expanded);
  panel?.classList.toggle("is-collapsed", !expanded);
  panel?.setAttribute("aria-hidden", String(!expanded));
  const button = $("toggleImagePrompt");
  if (button) {
    button.setAttribute("aria-expanded", String(expanded));
    button.textContent = expanded ? "收起提示词" : "图片提示词";
  }
  if (persist) writeLayoutFlag(layoutKeys.imagePrompt, expanded);
}

function restoreLayoutPrefs() {
  setSidebarCollapsed(readLayoutFlag(layoutKeys.sidebar), false);
  setTopbarExpanded(readLayoutFlag(layoutKeys.topbar), false);
  setImagePromptExpanded(readLayoutFlag(layoutKeys.imagePrompt, false), false);
}

function updatePreviewAspect() {
  const panel = els.preview?.closest(".preview-panel");
  if (!panel) return;
  panel.classList.remove("landscape", "portrait", "square");
  const width = Number(els.preview.videoWidth || 0);
  const height = Number(els.preview.videoHeight || 0);
  if (!width || !height) return;
  const diff = Math.abs(width - height) / Math.max(width, height);
  if (diff < 0.08) {
    panel.classList.add("square");
  } else if (width > height) {
    panel.classList.add("landscape");
  } else {
    panel.classList.add("portrait");
  }
}

function selectedShotIndexes() {
  return Array.from(state.selectedShots).sort((a, b) => a - b);
}

function setSelectedShots(indexes) {
  const values = indexes instanceof Set ? Array.from(indexes) : Array.isArray(indexes) ? indexes : [];
  state.selectedShots = new Set(values.map(Number).filter((index) => Number.isInteger(index) && index >= 0));
}

function toggleSelectedShot(index) {
  const shotIndex = Number(index);
  if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
  if (state.selectedShots.has(shotIndex)) {
    state.selectedShots.delete(shotIndex);
  } else {
    state.selectedShots.add(shotIndex);
  }
  storyView.updateSelection({ persist: true });
}

function openImagePreviewFromThumb(thumb) {
  const img = thumb?.querySelector?.("img");
  const modal = $("imagePreviewModal");
  const preview = $("imagePreviewFull");
  if (!img?.src || !modal || !preview) return;
  preview.src = img.src;
  modal.hidden = false;
}

function closeImagePreview() {
  const modal = $("imagePreviewModal");
  const preview = $("imagePreviewFull");
  if (!modal) return;
  modal.hidden = true;
  if (preview) preview.removeAttribute("src");
}

function escapeTextareaValue(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function closeShotPromptEditor(editor, save = true) {
  if (!editor?.isConnected) return;
  const index = Number(editor.dataset.shotPromptEditor);
  if (save && Number.isInteger(index)) {
    storyView.updateShotImagePrompt(index, editor.value);
  } else {
    storyView.renderShotGrid();
  }
}

function openShotPromptEditor(promptNode) {
  const index = Number(promptNode?.dataset.editShotPrompt);
  if (!Number.isInteger(index)) return;
  const value = storyView.getShotImagePrompt(index);
  promptNode.innerHTML = `<textarea class="shot-prompt-editor" data-shot-prompt-editor="${index}" aria-label="镜头 ${index + 1} 图片提示词">${escapeTextareaValue(value)}</textarea>`;
  const editor = promptNode.querySelector("textarea");
  if (!editor) return;
  editor.focus();
  editor.setSelectionRange(editor.value.length, editor.value.length);
}

function applyTtsPreset() {
  if (els.ttsProvider?.value !== "edge") return;
  const option = els.ttsPreset?.selectedOptions?.[0];
  if (!option?.dataset?.voice || !option?.dataset?.rate) return;
  els.voice.value = option.dataset.voice;
  els.rate.value = option.dataset.rate;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  ui.setTab(tab);
  if (tab === "image") storyView.renderShotGrid();
}

function syncThemeMirrors() {
  if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
  if (els.themeIntroMirror) els.themeIntroMirror.textContent = els.themeIntro?.value.trim() || "未填写主题介绍";
}

function activeImageJobForShot(index) {
  const shotIndex = Number(index);
  if (!Number.isInteger(shotIndex) || !(state.activeImageJobs instanceof Map)) return null;
  const job = state.activeImageJobs.get(shotIndex);
  if (!job) return null;
  if (state.currentProjectId && job.projectId && job.projectId !== state.currentProjectId) return null;
  return job;
}

function persistAndSave({ promptMeta = false, themeMirror = false } = {}) {
  if (themeMirror) syncThemeMirrors();
  settings.persist();
  if (promptMeta) storyView.updatePromptMeta();
  projectStore.scheduleSave();
}

function promptMetaAndSave() {
  storyView.updatePromptMeta();
  projectStore.scheduleSave();
}

const settings = createSettings({ els });

const storyView = createStoryView({
  els,
  getSelectedShots: () => state.selectedShots,
  setSelectedShots,
  getActiveTab: () => state.activeTab,
  getActiveImageJob: activeImageJobForShot,
  getActiveImageStatus: (index) => activeImageJobForShot(index)?.status || "",
  onStoryChanged: () => projectStore?.scheduleSave(),
});

projectStore = createProjectStore({
  els,
  ui,
  api,
  storyView,
  state,
  settings,
  setActiveTab,
});

state.referenceAssets = createReferenceAssets({
  els,
  ui,
  api,
  state,
  projectStore,
  storyView,
});

const workflowContext = {
  els,
  ui,
  api,
  settings,
  storyView,
  projectStore,
  state,
  setActiveTab,
};

const workflow = createWorkflow(workflowContext);

if (typeof workflow.generateThemeIdeas !== "function") {
  Object.assign(workflow, createThemeWorkflow(workflowContext));
}

function runThemeIdeas(options = {}) {
  if (typeof workflow.generateThemeIdeas !== "function") {
    ui.setStatus("AI 出方向模块未加载，请刷新页面", "error");
    if (els.result) els.result.textContent = "AI 出方向模块未加载：workflow.generateThemeIdeas 不存在。";
    return;
  }
  workflow.generateThemeIdeas(options);
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const tabButton = event.target.closest("[data-tab]");
    if (tabButton) setActiveTab(tabButton.dataset.tab);

    const openProjectButton = event.target.closest("[data-open-project]");
    if (openProjectButton) {
      workflow.clearThemeIdeas?.();
      workflow.clearImageJobPollers?.();
      projectStore.activate(openProjectButton.dataset.openProject).then(() => {
        workflow.restoreActiveImageJobs?.();
        workflow.restoreActiveAutoPipelineJobs?.();
      });
      return;
    }

    const deleteProjectButton = event.target.closest("[data-delete-project]");
    if (deleteProjectButton) {
      workflow.clearThemeIdeas?.();
      if (deleteProjectButton.dataset.deleteProject === state.currentProjectId) {
        workflow.clearImageJobPollers?.();
      }
      projectStore.remove(deleteProjectButton.dataset.deleteProject);
      return;
    }

    const aiPromptButton = event.target.closest("[data-ai-shot-prompt]");
    if (aiPromptButton) {
      workflow.improveShotImagePrompt(Number(aiPromptButton.dataset.aiShotPrompt));
      return;
    }

    const themeIdeaButton = event.target.closest("[data-theme-idea-action]");
    if (themeIdeaButton) {
      const index = Number(themeIdeaButton.dataset.themeIdeaIndex);
      const action = themeIdeaButton.dataset.themeIdeaAction;
      if (action === "adopt") workflow.adoptThemeIdea(index);
      if (action === "refine") runThemeIdeas({ refineIndex: index });
      if (action === "reroll") runThemeIdeas({ rerollIndex: index });
      return;
    }

    const redrawButton = event.target.closest("[data-redraw-shot]");
    if (redrawButton) {
      if (redrawButton.disabled) return;
      workflow.redrawShot(Number(redrawButton.dataset.redrawShot));
      return;
    }

    const setCoverButton = event.target.closest("[data-set-cover-shot]");
    if (setCoverButton) {
      workflow.setShotAsCover(Number(setCoverButton.dataset.setCoverShot));
      return;
    }

    const selectButton = event.target.closest("[data-select-shot]");
    if (selectButton) {
      clearTimeout(shotClickTimer);
      shotClickTimer = window.setTimeout(() => {
        toggleSelectedShot(selectButton.dataset.selectShot);
        shotClickTimer = 0;
      }, 180);
    }
  });

  document.addEventListener("dblclick", (event) => {
    if (event.target.closest("[data-ai-shot-prompt]")) return;
    const promptNode = event.target.closest("[data-edit-shot-prompt]");
    if (promptNode) {
      event.preventDefault();
      event.stopPropagation();
      openShotPromptEditor(promptNode);
      return;
    }
    if (event.target.closest("[data-redraw-shot]")) return;
    const thumb = event.target.closest("[data-select-shot]");
    if (!thumb) return;
    clearTimeout(shotClickTimer);
    shotClickTimer = 0;
    openImagePreviewFromThumb(thumb);
  });

  on("loadExample", "click", () => {
    workflow.clearImageJobPollers?.();
    workflow.loadExample();
  });
  on("startAutoPipeline", "click", workflow.startAutoPipeline);
  on("cancelAutoPipeline", "click", workflow.cancelAutoPipeline);
  on("generateThemeIdeas", "click", () => runThemeIdeas());
  on("rerollThemeIdeas", "click", () => runThemeIdeas({ reroll: true }));
  on("generateTheme", "click", workflow.generateTheme);
  on("rerollTheme", "click", () => workflow.generateTheme({ reroll: true }));
  on("reviseTheme", "click", workflow.reviseTheme);
  on("goCopyFromTheme", "click", () => setActiveTab("copy"));
  on("generate", "click", workflow.generateStory);
  on("generateCopy", "click", workflow.generateCopy);
  on("buildStoryboard", "click", workflow.buildStoryboardFromCopy);
  on("generateImages", "click", workflow.generateImagesParallel);
  on("redrawSelected", "click", () => workflow.redrawSelectedShots(selectedShotIndexes()));
  on("refreshGallery", "click", storyView.renderShotGrid);
  on("validate", "click", () => storyView.validate(els.result, ui.setStatus));
  on("render", "click", workflow.renderVideo);
  on("exportJianying", "click", workflow.exportJianyingDraft);
  on("editJianying", "click", workflow.editJianyingDraft);
  on("previewIntroTemplates", "click", workflow.previewIntroTemplates);
  on("uploadBgm", "click", workflow.uploadBgm);
  on("uploadIntroSfx", "click", workflow.uploadIntroSfx);
  on("closeIntroPreview", "click", workflow.closeIntroPreviewModal);
  on("introPreviewBackdrop", "click", workflow.closeIntroPreviewModal);
  on("closeImagePreview", "click", closeImagePreview);
  on("imagePreviewBackdrop", "click", closeImagePreview);
  on(els.preview, "loadedmetadata", updatePreviewAspect);
  on(els.preview, "emptied", updatePreviewAspect);
  on("sidebarToggle", "click", () => {
    setSidebarCollapsed(!document.querySelector(".app-frame")?.classList.contains("sidebar-collapsed"));
  });
  on("topbarToggle", "click", () => {
    setTopbarExpanded(!$("projectTopbar")?.classList.contains("is-expanded"));
  });
  on("toggleImagePrompt", "click", () => {
    setImagePromptExpanded($("tab-image")?.classList.contains("image-prompt-collapsed"));
  });
  on("saveProject", "click", async () => {
    ui.setStatus("保存中", "busy");
    await projectStore.saveNow();
    ui.setStatus("就绪");
  });
  on("newProject", "click", () => {
    workflow.clearThemeIdeas?.();
    workflow.clearImageJobPollers?.();
    projectStore.createNew();
  });
  on(els.projectPicker, "change", () => {
    if (els.projectPicker.value) {
      workflow.clearThemeIdeas?.();
      workflow.clearImageJobPollers?.();
      projectStore.activate(els.projectPicker.value).then(() => {
        workflow.restoreActiveImageJobs?.();
        workflow.restoreActiveAutoPipelineJobs?.();
      });
    }
  });

  on("openSettings", "click", ui.openSettings);
  on("closeSettings", "click", ui.closeSettings);
  on("settingsBackdrop", "click", ui.closeSettings);
  on("testTextConnection", "click", workflow.testTextConnection);
  on("testImageConnection", "click", workflow.testImageConnection);
  on("previewTts", "click", workflow.previewTts);
  on("resetCopyPrompt", "click", () => {
    settings.resetCopyPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on("copyPromptPreset", "change", () => {
    settings.applyCopyPromptPreset(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on("themeCopyPreset", "change", () => {
    settings.applyCopyPromptPreset(storyView.updatePromptMeta, projectStore.scheduleSave, els.themeCopyPreset.value);
  });
  on("resetCopyToStoryPrompt", "click", () => {
    settings.resetCopyToStoryPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on("resetImagePrompt", "click", () => {
    settings.resetImagePrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on(els.imageStylePreset, "change", () => {
    settings.applyImageStylePreset(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on("resetImproveImagePrompt", "click", () => {
    settings.resetImproveImagePrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  on("resetThemeIdeaPrompt", "click", () => {
    settings.resetThemeIdeaPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });

  document.addEventListener("focusout", (event) => {
    const editor = event.target.closest?.("[data-shot-prompt-editor]");
    if (editor) closeShotPromptEditor(editor, true);
  });

  on(els.editor, "input", storyView.onEditorInput);
  on(els.copyPrompt, "input", () => {
    persistAndSave({ promptMeta: true });
  });
  on(els.copyOutput, "input", () => {
    promptMetaAndSave();
  });
  on(els.copyToStoryPrompt, "input", () => {
    persistAndSave({ promptMeta: true });
  });
  on(els.imagePrompt, "input", () => {
    persistAndSave({ promptMeta: true });
  });
  on(els.improveImagePrompt, "input", () => {
    persistAndSave({ promptMeta: true });
  });
  on(els.themeIdeaPrompt, "input", () => {
    persistAndSave({ promptMeta: true });
  });
  on(els.themeBrief, "input", () => {
    persistAndSave();
  });
  on(els.themeIntro, "input", () => {
    persistAndSave({ promptMeta: true, themeMirror: true });
  });
  on(els.themeRevision, "input", () => {
    persistAndSave();
  });
  for (const id of ["autoBrief", "autoCopyPreset", "autoStoryboardGranularity", "autoImageSize", "autoIntroTemplate", "autoTtsPreset"]) {
    onEach([id], "input", settings.persist);
    onEach([id], "change", settings.persist);
  }
  on(els.storyboardGranularity, "change", () => {
    persistAndSave();
  });
  for (const id of ["autoOptimizeImagePrompts", "autoInfiniteImageRetry", "autoRenderAfterImages"]) {
    on(id, "change", settings.persist);
  }
  on(els.topic, "input", () => {
    syncThemeMirrors();
    persistAndSave();
  });

  for (const id of [
    "textProvider",
    "baseUrl",
    "model",
    "apiKey",
    "imageProvider",
    "imageBaseUrl",
    "imageModel",
    "imageApiKey",
    "ttsBaseUrl",
    "ttsGroupId",
    "ttsModel",
    "ttsVoiceId",
    "ttsSpeed",
    "ttsEmotion",
    "ttsLanguageBoost",
    "voice",
    "rate",
  ]) {
    on(id, "change", settings.persist);
  }
  on("imageSize", "change", () => {
    settings.persist();
    storyView.applyImageSize(els.imageSize.value, { scheduleSave: false });
    projectStore.scheduleSave();
  });
  for (const id of ["introTemplate", "introImageSeconds", "bgmSelect", "introSfxSelect"]) {
    on(id, "change", () => {
      settings.persist();
      projectStore.scheduleSave();
      if (id === "introTemplate" && els.introPreviewGrid) {
        for (const node of els.introPreviewGrid.querySelectorAll(".intro-preview-card")) {
          node.classList.toggle("active", node.dataset.template === els.introTemplate.value);
        }
      }
    });
  }
  on("ttsPreset", "change", () => {
    applyTtsPreset();
    persistAndSave();
  });
  for (const id of ["apiKey", "imageApiKey"]) {
    on(id, "input", settings.persist);
  }
  on("ttsProvider", "change", () => {
    settings.updateTtsProviderVisibility();
    persistAndSave();
  });
  for (const id of ["ttsApiKey", "ttsBaseUrl", "ttsGroupId", "ttsModel", "ttsVoiceId", "ttsSpeed", "ttsEmotion", "ttsLanguageBoost"]) {
    on(id, "input", settings.persist);
  }
  on("textProvider", "change", () => {
    settings.applyTextProviderDefaults();
    settings.persist();
  });
  state.referenceAssets?.bindEvents();
  document.addEventListener("keydown", (event) => {
    const promptEditor = event.target.closest?.("[data-shot-prompt-editor]");
    if (promptEditor) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeShotPromptEditor(promptEditor, false);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        closeShotPromptEditor(promptEditor, true);
      }
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && event.target.matches?.("[data-select-shot]")) {
      event.preventDefault();
      toggleSelectedShot(event.target.dataset.selectShot);
      return;
    }
    if (event.key === "Escape") {
      closeImagePreview();
      workflow.closeIntroPreviewModal();
      ui.closeSettings();
    }
  });
}

async function boot() {
  bindEvents();
  restoreLayoutPrefs();
  await workflow.loadBgmOptions().catch(() => null);
  await workflow.loadIntroSfxOptions().catch(() => null);
  await state.referenceAssets?.loadCollections?.().catch(() => null);
  settings.load();
  applyTtsPreset();
  settings.updateTtsProviderVisibility();
  if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
  await settings.loadPromptDefaults(api.fetchJson, storyView.updatePromptMeta).catch(() => storyView.updatePromptMeta());
  const restored = await projectStore.loadState();
  if (!restored) await workflow.loadExample();
  await projectStore.loadList();
  await workflow.restoreActiveImageJobs?.();
  await workflow.restoreActiveAutoPipelineJobs?.();
  if (!state.activeAutoPipelineJob) ui.setStatus("就绪");
}

boot().catch((err) => {
  ui.setStatus("出错", "error");
  els.result.textContent = String(err.message || err);
});
