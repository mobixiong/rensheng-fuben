import * as api from "./js/api.js";
import { $ , createUi } from "./js/ui.js";
import { createSettings } from "./js/settings.js";
import { createStoryView } from "./js/story-view.js";
import { createProjectStore } from "./js/project-store.js";
import { createWorkflow } from "./js/workflow.js";

const ui = createUi();
const { els } = ui;

const state = {
  activeTab: "copy",
  selectedShots: new Set(),
  saveTimer: 0,
  restoringProject: false,
  currentProjectId: "",
  imageGenerationActive: false,
  projectSaveQueue: Promise.resolve(),
};

let projectStore;

const layoutKeys = {
  sidebar: "lifeCopy.sidebarCollapsed",
  topbar: "lifeCopy.topbarExpanded",
  imagePrompt: "lifeCopy.imagePromptExpanded",
};

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
  storyView.updateSelection();
}

function applyTtsPreset() {
  if (els.ttsProvider?.value === "minimax") return;
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

const settings = createSettings({ els });

const storyView = createStoryView({
  els,
  getSelectedShots: () => state.selectedShots,
  setSelectedShots,
  getActiveTab: () => state.activeTab,
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

const workflow = createWorkflow({
  els,
  ui,
  api,
  settings,
  storyView,
  projectStore,
  state,
  setActiveTab,
});

function bindEvents() {
  document.addEventListener("click", (event) => {
    const tabButton = event.target.closest("[data-tab]");
    if (tabButton) setActiveTab(tabButton.dataset.tab);

    const openProjectButton = event.target.closest("[data-open-project]");
    if (openProjectButton) projectStore.activate(openProjectButton.dataset.openProject);

    const redrawButton = event.target.closest("[data-redraw-shot]");
    if (redrawButton) {
      workflow.redrawShot(Number(redrawButton.dataset.redrawShot));
      return;
    }

    const selectButton = event.target.closest("[data-select-shot]");
    if (selectButton) {
      toggleSelectedShot(selectButton.dataset.selectShot);
    }
  });

  $("loadExample").addEventListener("click", workflow.loadExample);
  $("generate").addEventListener("click", workflow.generateStory);
  $("generateCopy").addEventListener("click", workflow.generateCopy);
  $("buildStoryboard").addEventListener("click", workflow.buildStoryboardFromCopy);
  $("generateImages").addEventListener("click", workflow.generateImagesParallel);
  $("redrawSelected").addEventListener("click", () => workflow.redrawSelectedShots(selectedShotIndexes()));
  $("refreshGallery").addEventListener("click", storyView.renderShotGrid);
  $("validate").addEventListener("click", () => storyView.validate(els.result, ui.setStatus));
  $("render").addEventListener("click", workflow.renderVideo);
  $("previewIntroTemplates")?.addEventListener("click", workflow.previewIntroTemplates);
  $("closeIntroPreview")?.addEventListener("click", workflow.closeIntroPreviewModal);
  $("introPreviewBackdrop")?.addEventListener("click", workflow.closeIntroPreviewModal);
  $("sidebarToggle")?.addEventListener("click", () => {
    setSidebarCollapsed(!document.querySelector(".app-frame")?.classList.contains("sidebar-collapsed"));
  });
  $("topbarToggle")?.addEventListener("click", () => {
    setTopbarExpanded(!$("projectTopbar")?.classList.contains("is-expanded"));
  });
  $("toggleImagePrompt")?.addEventListener("click", () => {
    setImagePromptExpanded($("tab-image")?.classList.contains("image-prompt-collapsed"));
  });
  $("saveProject").addEventListener("click", async () => {
    ui.setStatus("保存中", "busy");
    await projectStore.saveNow();
    ui.setStatus("就绪");
  });
  $("newProject").addEventListener("click", projectStore.createNew);
  els.projectPicker.addEventListener("change", () => {
    if (els.projectPicker.value) projectStore.activate(els.projectPicker.value);
  });

  $("openSettings")?.addEventListener("click", ui.openSettings);
  $("closeSettings")?.addEventListener("click", ui.closeSettings);
  $("settingsBackdrop")?.addEventListener("click", ui.closeSettings);
  $("testTextConnection").addEventListener("click", workflow.testTextConnection);
  $("testImageConnection").addEventListener("click", workflow.testImageConnection);
  $("resetCopyPrompt").addEventListener("click", () => {
    settings.resetCopyPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  $("resetCopyToStoryPrompt")?.addEventListener("click", () => {
    settings.resetCopyToStoryPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });
  $("resetImagePrompt").addEventListener("click", () => {
    settings.resetImagePrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
  });

  els.editor.addEventListener("input", storyView.onEditorInput);
  els.copyPrompt.addEventListener("input", () => {
    settings.persist();
    storyView.updatePromptMeta();
    projectStore.scheduleSave();
  });
  els.copyOutput.addEventListener("input", () => {
    storyView.updatePromptMeta();
    projectStore.scheduleSave();
  });
  els.copyToStoryPrompt?.addEventListener("input", () => {
    settings.persist();
    storyView.updatePromptMeta();
    projectStore.scheduleSave();
  });
  els.imagePrompt.addEventListener("input", () => {
    settings.persist();
    storyView.updatePromptMeta();
    projectStore.scheduleSave();
  });
  els.topic.addEventListener("input", () => {
    if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
    settings.persist();
    projectStore.scheduleSave();
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
    "imageSize",
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
    $(id).addEventListener("change", settings.persist);
  }
  for (const id of ["introTemplate", "introImageSeconds", "bgmSelect"]) {
    $(id)?.addEventListener("change", () => {
      settings.persist();
      projectStore.scheduleSave();
      if (id === "introTemplate" && els.introPreviewGrid) {
        for (const node of els.introPreviewGrid.querySelectorAll(".intro-preview-card")) {
          node.classList.toggle("active", node.dataset.template === els.introTemplate.value);
        }
      }
    });
  }
  $("ttsPreset")?.addEventListener("change", () => {
    applyTtsPreset();
    settings.persist();
    projectStore.scheduleSave();
  });
  for (const id of ["apiKey", "imageApiKey"]) {
    $(id).addEventListener("input", settings.persist);
  }
  $("ttsProvider")?.addEventListener("change", () => {
    settings.updateTtsProviderVisibility();
    settings.persist();
    projectStore.scheduleSave();
  });
  for (const id of ["ttsApiKey", "ttsBaseUrl", "ttsGroupId", "ttsVoiceId", "ttsSpeed"]) {
    $(id)?.addEventListener("input", settings.persist);
  }
  $("textProvider").addEventListener("change", () => {
    settings.applyTextProviderDefaults();
    settings.persist();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches?.("[data-select-shot]")) {
      event.preventDefault();
      toggleSelectedShot(event.target.dataset.selectShot);
      return;
    }
    if (event.key === "Escape") {
      workflow.closeIntroPreviewModal();
      ui.closeSettings();
    }
  });
}

async function boot() {
  bindEvents();
  restoreLayoutPrefs();
  await workflow.loadBgmOptions().catch(() => null);
  settings.load();
  applyTtsPreset();
  settings.updateTtsProviderVisibility();
  if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
  await settings.loadPromptDefaults(api.fetchJson, storyView.updatePromptMeta).catch(() => storyView.updatePromptMeta());
  const restored = await projectStore.loadState();
  if (!restored) await workflow.loadExample();
  await projectStore.loadList();
  ui.setStatus("就绪");
}

boot().catch((err) => {
  ui.setStatus("出错", "error");
  els.result.textContent = String(err.message || err);
});
