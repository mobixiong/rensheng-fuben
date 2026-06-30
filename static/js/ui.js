export const $ = (id) => document.getElementById(id);

export function createUi() {
  const els = {
    editor: $("jsonEditor"),
    status: $("status"),
    result: $("result"),
    preview: $("preview"),
    openVideo: $("openVideo"),
    jsonMeta: $("jsonMeta"),
    shotGrid: $("shotGrid"),
    selectedShotLabel: $("selectedShotLabel"),
    copyPrompt: $("copyPrompt"),
    copyOutput: $("copyOutput"),
    copyPromptMeta: $("copyPromptMeta"),
    copyMeta: $("copyMeta"),
    imagePrompt: $("imagePrompt"),
    imagePromptMeta: $("imagePromptMeta"),
    settingsDrawer: $("settingsDrawer"),
    settingsBackdrop: $("settingsBackdrop"),
    textConnectionResult: $("textConnectionResult"),
    imageConnectionResult: $("imageConnectionResult"),
    projectLabel: $("projectLabel"),
    projectSaveMeta: $("projectSaveMeta"),
    projectPicker: $("projectPicker"),
    projectGrid: $("projectGrid"),
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
      "generate",
      "generateCopy",
      "buildStoryboard",
      "generateImages",
      "redrawSelected",
      "validate",
      "render",
      "refreshGallery",
      "resetCopyPrompt",
      "resetImagePrompt",
      "testTextConnection",
      "testImageConnection",
      "saveProject",
      "newProject",
      "projectPicker",
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
    if (els.projectSaveMeta) els.projectSaveMeta.textContent = detail || "尚未保存";
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
