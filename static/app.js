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
  selectedShot: 0,
  saveTimer: 0,
  restoringProject: false,
  currentProjectId: "",
  imageGenerationActive: false,
  projectSaveQueue: Promise.resolve(),
};

let projectStore;

function setSelectedShot(index) {
  state.selectedShot = index;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  ui.setTab(tab);
  if (tab === "image") storyView.renderShotGrid();
}

const settings = createSettings({ els });

const storyView = createStoryView({
  els,
  getSelectedShot: () => state.selectedShot,
  setSelectedShot,
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

    const selectButton = event.target.closest("[data-select-shot]");
    if (selectButton) {
      state.selectedShot = Number(selectButton.dataset.selectShot);
      storyView.renderShotGrid();
    }

    const redrawButton = event.target.closest("[data-redraw-shot]");
    if (redrawButton) workflow.redrawShot(Number(redrawButton.dataset.redrawShot));
  });

  $("loadExample").addEventListener("click", workflow.loadExample);
  $("generate").addEventListener("click", workflow.generateStory);
  $("generateCopy").addEventListener("click", workflow.generateCopy);
  $("buildStoryboard").addEventListener("click", workflow.buildStoryboardFromCopy);
  $("generateImages").addEventListener("click", workflow.generateImagesParallel);
  $("redrawSelected").addEventListener("click", () => workflow.redrawShot(state.selectedShot));
  $("refreshGallery").addEventListener("click", storyView.renderShotGrid);
  $("validate").addEventListener("click", () => storyView.validate(els.result, ui.setStatus));
  $("render").addEventListener("click", workflow.renderVideo);
  $("saveProject").addEventListener("click", async () => {
    ui.setStatus("保存中", "busy");
    await projectStore.saveNow();
    ui.setStatus("就绪");
  });
  $("newProject").addEventListener("click", projectStore.createNew);
  els.projectPicker.addEventListener("change", () => {
    if (els.projectPicker.value) projectStore.activate(els.projectPicker.value);
  });

  $("openSettings").addEventListener("click", ui.openSettings);
  $("closeSettings").addEventListener("click", ui.closeSettings);
  $("settingsBackdrop").addEventListener("click", ui.closeSettings);
  $("testTextConnection").addEventListener("click", workflow.testTextConnection);
  $("testImageConnection").addEventListener("click", workflow.testImageConnection);
  $("resetCopyPrompt").addEventListener("click", () => {
    settings.resetCopyPrompt(storyView.updatePromptMeta, projectStore.scheduleSave);
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
  els.imagePrompt.addEventListener("input", () => {
    settings.persist();
    storyView.updatePromptMeta();
    projectStore.scheduleSave();
  });
  els.topic.addEventListener("input", () => {
    settings.persist();
    projectStore.scheduleSave();
  });

  for (const id of ["textProvider", "baseUrl", "model", "apiKey", "imageProvider", "imageBaseUrl", "imageModel", "imageApiKey", "imageSize", "voice", "rate"]) {
    $(id).addEventListener("change", settings.persist);
  }
  for (const id of ["apiKey", "imageApiKey"]) {
    $(id).addEventListener("input", settings.persist);
  }
  $("textProvider").addEventListener("change", () => {
    settings.applyTextProviderDefaults();
    settings.persist();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") ui.closeSettings();
  });
}

async function boot() {
  bindEvents();
  settings.load();
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
