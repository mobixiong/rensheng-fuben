import { PROJECT_PROGRESS_SAVE_INTERVAL_MS, PROJECT_SAVE_DELAY_MS } from "./constants.js";
import { escapeHtml } from "./html.js";

export function createProjectStore({ els, ui, api, storyView, state, settings, setActiveTab }) {
  function selectedShotIndexes() {
    return Array.from(state.selectedShots || []).sort((a, b) => a - b);
  }

  function resultVideoUrl(resultText) {
    try {
      const data = JSON.parse(resultText || "{}");
      return typeof data.video === "string" ? data.video : "";
    } catch {
      return "";
    }
  }

  function currentRenderedVideoUrl() {
    return els.preview?.getAttribute("src") || resultVideoUrl(els.result.textContent);
  }

  function applyRenderedVideo(url) {
    const videoUrl = String(url || "").trim();
    if (!els.preview || !els.openVideo) return;
    if (!videoUrl) {
      els.preview.removeAttribute("src");
      els.openVideo.hidden = true;
      els.openVideo.removeAttribute("href");
      return;
    }
    els.preview.src = videoUrl;
    els.openVideo.href = videoUrl;
    els.openVideo.hidden = false;
  }

  function projectState() {
    const selectedShots = selectedShotIndexes();
    return {
      version: 1,
      project_id: state.currentProjectId,
      topic: els.topic.value,
      active_tab: state.activeTab,
      selected_shots: selectedShots,
      selected_shot: selectedShots[0] ?? null,
      copy_text: els.copyOutput.value,
      story_json: els.editor.value,
      story: storyView.readOrNull(),
      result_text: els.result.textContent,
      rendered_video: currentRenderedVideoUrl(),
      copy_prompt: els.copyPrompt.value,
      image_prompt: els.imagePrompt.value,
      intro_template: els.introTemplate?.value || "none",
      tts_preset: els.ttsPreset?.value || "custom",
      bgm_id: els.bgmSelect?.value || "none",
    };
  }

  function scheduleSave() {
    if (state.restoringProject || state.imageGenerationActive) return;
    clearTimeout(state.saveTimer);
    ui.setProjectMeta(state.currentProjectId || "未保存项目", "自动保存待处理");
    state.saveTimer = window.setTimeout(saveNow, PROJECT_SAVE_DELAY_MS);
  }

  async function saveNow(options = {}) {
    const { applyState = true, refreshProjects = true } = options;
    if (state.restoringProject) return null;
    try {
      const data = await api.postJson("/api/project/current", projectState());
      if (data.project_id) state.currentProjectId = data.project_id;
      if (applyState && !state.imageGenerationActive && data.state) {
        applyProjectState(data.state, { preserveTab: true, fromSave: true });
      }
      ui.setProjectMeta(state.currentProjectId, data.saved_at ? `自动保存 ${data.saved_at}` : "自动保存完成");
      if (els.projectPicker && state.currentProjectId) els.projectPicker.value = state.currentProjectId;
      if (refreshProjects) await loadList();
      return data;
    } catch (err) {
      ui.setProjectMeta(state.currentProjectId || "自动保存失败", "自动保存失败");
      console.warn("Project autosave failed", err);
      return null;
    }
  }

  function queueSave(options = {}) {
    state.projectSaveQueue = state.projectSaveQueue
      .catch(() => null)
      .then(() => saveNow(options));
    return state.projectSaveQueue;
  }

  function queueProgressSave(options = {}) {
    const now = Date.now();
    if (now - (state.lastProgressSaveAt || 0) < PROJECT_PROGRESS_SAVE_INTERVAL_MS) {
      return state.projectSaveQueue;
    }
    state.lastProgressSaveAt = now;
    return queueSave(options);
  }

  async function ensureSaved(options = {}) {
    const data = await saveNow(options);
    return data?.project_id || state.currentProjectId;
  }

  function mediaProjectId() {
    return state.currentProjectId ? `projects/${state.currentProjectId}` : "";
  }

  function applyProjectState(projectStateData, options = {}) {
    state.restoringProject = true;
    state.currentProjectId = projectStateData.project_id || state.currentProjectId || "";
    ui.setProjectMeta(
      state.currentProjectId,
      projectStateData.saved_at ? `${options.fromSave ? "自动保存" : "已恢复"} ${projectStateData.saved_at}` : "已恢复",
    );
    if (typeof projectStateData.topic === "string") els.topic.value = projectStateData.topic;
    if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
    if (typeof projectStateData.copy_text === "string") els.copyOutput.value = projectStateData.copy_text;
    if (typeof projectStateData.copy_prompt === "string") els.copyPrompt.value = projectStateData.copy_prompt;
    if (typeof projectStateData.image_prompt === "string") els.imagePrompt.value = projectStateData.image_prompt;
    if (els.introTemplate && typeof projectStateData.intro_template === "string") els.introTemplate.value = projectStateData.intro_template;
    if (els.ttsPreset && typeof projectStateData.tts_preset === "string") els.ttsPreset.value = projectStateData.tts_preset;
    if (els.bgmSelect && typeof projectStateData.bgm_id === "string") {
      const exists = Array.from(els.bgmSelect.options).some((option) => option.value === projectStateData.bgm_id);
      if (exists) els.bgmSelect.value = projectStateData.bgm_id;
    }
    if (typeof projectStateData.result_text === "string") els.result.textContent = projectStateData.result_text;
    applyRenderedVideo(projectStateData.rendered_video || resultVideoUrl(projectStateData.result_text));
    const selectedShots = Array.isArray(projectStateData.selected_shots)
      ? projectStateData.selected_shots
      : Number.isInteger(projectStateData.selected_shot)
        ? [projectStateData.selected_shot]
        : [];
    state.selectedShots = new Set(
      selectedShots.map(Number).filter((index) => Number.isInteger(index) && index >= 0),
    );

    if (projectStateData.story && typeof projectStateData.story === "object") {
      storyView.write(projectStateData.story, { scheduleSave: false });
    } else if (typeof projectStateData.story_json === "string") {
      els.editor.value = projectStateData.story_json;
      storyView.updateMeta();
      storyView.renderShotGrid();
    }

    storyView.updatePromptMeta();
    if (!options.preserveTab) {
      setActiveTab(["project", "copy", "image", "video", "settings"].includes(projectStateData.active_tab) ? projectStateData.active_tab : "copy");
    }
    state.restoringProject = false;
  }

  async function loadList() {
    if (!els.projectPicker) return;
    const data = await api.fetchJson("/api/projects").catch(() => null);
    if (!data) return;
    const projects = Array.isArray(data.projects) ? data.projects : [];
    els.projectPicker.innerHTML = '<option value="">未保存项目</option>' + projects.map((project) => {
      const label = `${project.topic || project.project_id} ${project.saved_at ? "· " + project.saved_at : ""}`;
      return `<option value="${escapeHtml(project.project_id)}">${escapeHtml(label)}</option>`;
    }).join("");
    els.projectPicker.value = state.currentProjectId || data.active_project_id || "";
    if (els.projectGrid) {
      els.projectGrid.innerHTML = projects.map((project) => {
        const isActive = project.project_id === (state.currentProjectId || data.active_project_id || "");
        return `
          <article class="project-tile${isActive ? " active" : ""}">
            <div class="project-tile-head">
              <h2>${escapeHtml(project.topic || project.project_id)}</h2>
              <span class="state-badge ${isActive ? "editing" : "done"}">${isActive ? "进行中" : "已保存"}</span>
            </div>
            <p>${escapeHtml(project.project_id)}</p>
            <div class="project-tile-foot">
              <span>${escapeHtml(project.saved_at || "未记录时间")}</span>
              <button class="secondary-pill" type="button" data-open-project="${escapeHtml(project.project_id)}">打开</button>
            </div>
          </article>
        `;
      }).join("") || '<div class="empty-state">暂无项目，先新建一个主题。</div>';
    }
  }

  async function loadState() {
    const data = await api.fetchJson("/api/project/current").catch(() => null);
    if (!data?.exists || !data.state) return false;
    applyProjectState(data.state);
    return true;
  }

  async function activate(projectId) {
    if (!projectId) return;
    ui.setBusy(true);
    ui.setStatus("切换项目", "busy");
    try {
      const data = await api.postJson("/api/project/activate", { project_id: projectId });
      applyProjectState(data.state || {});
      await loadList();
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  function createNew() {
    state.currentProjectId = "";
    state.selectedShots = new Set();
    els.topic.value = "新项目";
    if (els.topicMirror) els.topicMirror.textContent = els.topic.value;
    els.copyOutput.value = "";
    els.result.textContent = "{}";
    applyRenderedVideo("");
    storyView.write({ title: "", style_preset: "", shots: [] }, { scheduleSave: false });
    storyView.updatePromptMeta();
    ui.setProjectMeta("未保存项目", "自动保存开启");
    if (els.projectPicker) els.projectPicker.value = "";
    setActiveTab("copy");
    settings.persist();
    scheduleSave();
  }

  return {
    scheduleSave,
    saveNow,
    queueSave,
    queueProgressSave,
    ensureSaved,
    mediaProjectId,
    applyProjectState,
    loadList,
    loadState,
    activate,
    createNew,
  };
}
