const $ = (id) => document.getElementById(id);

const editor = $("jsonEditor");
const statusEl = $("status");
const resultEl = $("result");
const preview = $("preview");
const openVideo = $("openVideo");
const jsonMeta = $("jsonMeta");
const shotGrid = $("shotGrid");
const selectedShotLabel = $("selectedShotLabel");
const copyPrompt = $("copyPrompt");
const copyOutput = $("copyOutput");
const copyPromptMeta = $("copyPromptMeta");
const copyMeta = $("copyMeta");
const imagePrompt = $("imagePrompt");
const imagePromptMeta = $("imagePromptMeta");
const settingsDrawer = $("settingsDrawer");
const settingsBackdrop = $("settingsBackdrop");
const textConnectionResult = $("textConnectionResult");
const imageConnectionResult = $("imageConnectionResult");
const projectLabel = $("projectLabel");
const projectSaveMeta = $("projectSaveMeta");
const projectPicker = $("projectPicker");
const SETTINGS_KEY = "rensheng-fuben-settings";
const GEMINI_WEB2API_DEFAULT_BASE_URL = "http://127.0.0.1:8081/v1";
const GEMINI_WEB2API_DEFAULT_MODEL = "gemini-3.5-flash-thinking";
const PROJECT_SAVE_DELAY_MS = 700;
const IMAGE_RETRY_LIMIT = 2;

let activeTab = "copy";
let selectedShot = 0;
let defaultCopyPrompt = "";
let defaultImagePrompt = "";
let saveTimer = 0;
let restoringProject = false;
let currentProjectId = "";

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status-pill ${kind}`.trim();
}

function setBusy(busy) {
  for (const id of ["loadExample", "generate", "generateCopy", "buildStoryboard", "generateImages", "redrawSelected", "validate", "render", "refreshGallery", "resetCopyPrompt", "resetImagePrompt", "testTextConnection", "testImageConnection", "saveProject", "newProject", "projectPicker"]) {
    const el = $(id);
    if (el) el.disabled = busy;
  }
}

function readStory() {
  return JSON.parse(editor.value);
}

function writeStory(obj) {
  editor.value = JSON.stringify(obj, null, 2);
  updateMeta();
  renderShotGrid();
  scheduleProjectSave();
}

function updateMeta() {
  try {
    const story = readStory();
    const shots = story.shots?.length || 0;
    const imageCount = (story.shots || []).filter((shot) => shot.image_path || shot.image_url).length;
    jsonMeta.textContent = `${shots} 个镜头 · ${imageCount} 张图`;
  } catch {
    jsonMeta.textContent = "分镜数据无效";
  }
}

function updatePromptMeta() {
  if (copyPromptMeta) copyPromptMeta.textContent = `${copyPrompt.value.length} 字`;
  if (copyMeta) copyMeta.textContent = `${copyOutput.value.length} 字`;
  if (imagePromptMeta) imagePromptMeta.textContent = `${imagePrompt.value.length} 字`;
}

function setTab(tab) {
  activeTab = tab;
  for (const button of document.querySelectorAll(".tab-button")) {
    button.classList.toggle("active", button.dataset.tab === tab);
  }
  for (const panel of document.querySelectorAll(".tab-view")) {
    panel.classList.toggle("active", panel.id === `tab-${tab}`);
  }
  if (tab === "image") renderShotGrid();
}

function applyTextProviderDefaults() {
  if ($("textProvider").value !== "gemini_web2api") return;
  if (!$("baseUrl").value.trim() || $("baseUrl").value.includes("api.example.com")) {
    $("baseUrl").value = GEMINI_WEB2API_DEFAULT_BASE_URL;
  }
  if (!$("model").value.trim() || $("model").value === "your-model-name") {
    $("model").value = GEMINI_WEB2API_DEFAULT_MODEL;
  }
  if (!$("apiKey").value.trim()) {
    $("apiKey").value = "sk-local";
  }
}

function setTestResult(el, text, kind = "") {
  if (!el) return;
  el.textContent = text;
  el.className = `test-result ${kind}`.trim();
}

function setProjectMeta(label, detail = "") {
  if (projectLabel) projectLabel.textContent = label || "未保存项目";
  if (projectSaveMeta) projectSaveMeta.textContent = detail || "尚未保存";
  if (projectPicker && currentProjectId) projectPicker.value = currentProjectId;
}

function openSettings() {
  settingsBackdrop.hidden = false;
  settingsDrawer.classList.add("open");
  settingsDrawer.setAttribute("aria-hidden", "false");
}

function closeSettings() {
  settingsDrawer.classList.remove("open");
  settingsDrawer.setAttribute("aria-hidden", "true");
  settingsBackdrop.hidden = true;
}

function persistSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    topic: $("topic").value,
    textProvider: $("textProvider").value,
    baseUrl: $("baseUrl").value,
    model: $("model").value,
    apiKey: $("apiKey").value,
    imageProvider: $("imageProvider").value,
    imageBaseUrl: $("imageBaseUrl").value,
    imageModel: $("imageModel").value,
    imageApiKey: $("imageApiKey").value,
    imageSize: $("imageSize").value,
    voice: $("voice").value,
    rate: $("rate").value,
    copyPrompt: copyPrompt.value,
    imagePrompt: imagePrompt.value,
  }));
}

function readStoryOrNull() {
  try {
    return readStory();
  } catch {
    return null;
  }
}

function projectState() {
  return {
    version: 1,
    project_id: currentProjectId,
    topic: $("topic").value,
    active_tab: activeTab,
    selected_shot: selectedShot,
    copy_text: copyOutput.value,
    story_json: editor.value,
    story: readStoryOrNull(),
    result_text: resultEl.textContent,
    copy_prompt: copyPrompt.value,
    image_prompt: imagePrompt.value,
  };
}

function scheduleProjectSave() {
  if (restoringProject) return;
  clearTimeout(saveTimer);
  saveTimer = window.setTimeout(saveProjectNow, PROJECT_SAVE_DELAY_MS);
}

async function saveProjectNow() {
  if (restoringProject) return;
  try {
    const data = await postJson("/api/project/current", projectState());
    if (data.project_id) currentProjectId = data.project_id;
    if (data.state) applyProjectState(data.state, {preserveTab: true, fromSave: true});
    setProjectMeta(currentProjectId, data.saved_at ? `已保存 ${data.saved_at}` : "已保存");
    await loadProjectList();
    return data;
  } catch (err) {
    setProjectMeta(currentProjectId || "保存失败", "保存失败");
    console.warn("Project autosave failed", err);
    return null;
  }
}

async function ensureProjectSaved() {
  const data = await saveProjectNow();
  return data?.project_id || currentProjectId;
}

function mediaProjectId() {
  return currentProjectId ? `projects/${currentProjectId}` : "";
}

function applyProjectState(state, options = {}) {
  restoringProject = true;
  currentProjectId = state.project_id || currentProjectId || "";
  setProjectMeta(currentProjectId, state.saved_at ? `${options.fromSave ? "已保存" : "已恢复"} ${state.saved_at}` : "已恢复");
  if (typeof state.topic === "string") $("topic").value = state.topic;
  if (typeof state.copy_text === "string") copyOutput.value = state.copy_text;
  if (typeof state.copy_prompt === "string") copyPrompt.value = state.copy_prompt;
  if (typeof state.image_prompt === "string") imagePrompt.value = state.image_prompt;
  if (typeof state.result_text === "string") resultEl.textContent = state.result_text;
  selectedShot = Number.isInteger(state.selected_shot) ? state.selected_shot : selectedShot;

  if (state.story && typeof state.story === "object") {
    editor.value = JSON.stringify(state.story, null, 2);
    updateMeta();
    renderShotGrid();
  } else if (typeof state.story_json === "string") {
    editor.value = state.story_json;
    updateMeta();
    renderShotGrid();
  }

  updatePromptMeta();
  if (!options.preserveTab) {
    setTab(["copy", "image", "video"].includes(state.active_tab) ? state.active_tab : "copy");
  }
  restoringProject = false;
}

async function loadProjectList() {
  if (!projectPicker) return;
  const res = await fetch("/api/projects");
  if (!res.ok) return;
  const data = await res.json().catch(() => ({}));
  const projects = Array.isArray(data.projects) ? data.projects : [];
  projectPicker.innerHTML = '<option value="">未保存项目</option>' + projects.map((project) => {
    const label = `${project.topic || project.project_id} ${project.saved_at ? "· " + project.saved_at : ""}`;
    return `<option value="${escapeHtml(project.project_id)}">${escapeHtml(label)}</option>`;
  }).join("");
  projectPicker.value = currentProjectId || data.active_project_id || "";
}

async function loadProjectState() {
  const res = await fetch("/api/project/current");
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.exists || !data.state) return false;

  applyProjectState(data.state);
  return true;
}

async function activateProject(projectId) {
  if (!projectId) return;
  setBusy(true);
  setStatus("切换项目", "busy");
  try {
    const data = await postJson("/api/project/activate", {project_id: projectId});
    applyProjectState(data.state || {});
    await loadProjectList();
    setStatus("就绪");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

function newProject() {
  currentProjectId = "";
  selectedShot = 0;
  $("topic").value = "新项目";
  copyOutput.value = "";
  resultEl.textContent = "{}";
  editor.value = JSON.stringify({title: "", style_preset: "", shots: []}, null, 2);
  updateMeta();
  updatePromptMeta();
  renderShotGrid();
  setProjectMeta("未保存项目", "新项目");
  if (projectPicker) projectPicker.value = "";
  setTab("copy");
  scheduleProjectSave();
}

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
    $("textProvider").value = ["openai", "gemini_web2api"].includes(s.textProvider) ? s.textProvider : "openai";
    if (s.topic) $("topic").value = s.topic;
    $("baseUrl").value = s.baseUrl || "";
    $("model").value = s.model || "";
    $("apiKey").value = s.apiKey || "";
    $("imageProvider").value = s.imageProvider === "openai" ? s.imageProvider : "openai";
    $("imageBaseUrl").value = s.imageBaseUrl || "";
    $("imageModel").value = s.imageModel || "";
    $("imageApiKey").value = s.imageApiKey || "";
    $("imageSize").value = ["9:16", "1:1", "16:9"].includes(s.imageSize) ? s.imageSize : "9:16";
    $("voice").value = s.voice || "zh-CN-YunxiNeural";
    $("rate").value = s.rate || "+12%";
    if (s.copyPrompt) copyPrompt.value = s.copyPrompt;
    if (s.imagePrompt) imagePrompt.value = s.imagePrompt;
    applyTextProviderDefaults();
  } catch {}
}

async function loadPromptDefaults() {
  const [copyRes, imageRes] = await Promise.all([
    fetch("/api/prompt/default"),
    fetch("/api/prompt/image"),
  ]);
  defaultCopyPrompt = (await copyRes.json()).prompt || "";
  defaultImagePrompt = (await imageRes.json()).prompt || "";
  if (!copyPrompt.value.trim()) copyPrompt.value = defaultCopyPrompt;
  if (!imagePrompt.value.trim()) imagePrompt.value = defaultImagePrompt;
  updatePromptMeta();
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function textPayload() {
  return {
    topic: $("topic").value.trim(),
    provider: $("textProvider").value,
    base_url: $("baseUrl").value.trim(),
    model: $("model").value.trim(),
    api_key: $("apiKey").value.trim(),
    system_prompt: copyPrompt.value,
    temperature: 0.8,
  };
}

function storyPayload() {
  return {
    topic: $("topic").value.trim(),
    provider: $("textProvider").value,
    base_url: $("baseUrl").value.trim(),
    model: $("model").value.trim(),
    api_key: $("apiKey").value.trim(),
    temperature: 0.8,
  };
}

function textConnectionPayload() {
  return {
    provider: $("textProvider").value,
    base_url: $("baseUrl").value.trim(),
    model: $("model").value.trim(),
    api_key: $("apiKey").value.trim(),
    temperature: 0,
  };
}

function copyToStoryPayload(copyText) {
  return {
    topic: $("topic").value.trim(),
    copy_text: copyText.trim(),
    provider: $("textProvider").value,
    base_url: $("baseUrl").value.trim(),
    model: $("model").value.trim(),
    api_key: $("apiKey").value.trim(),
    temperature: 0.5,
  };
}

function imageConnectionPayload() {
  return {
    provider: $("imageProvider").value,
    base_url: $("imageBaseUrl").value.trim(),
    model: $("imageModel").value.trim(),
    api_key: $("imageApiKey").value.trim(),
    size: $("imageSize").value.trim() || "9:16",
  };
}

function imagePayload(extra = {}, storyOverride = null) {
  return {
    story: storyOverride || readStory(),
    provider: $("imageProvider").value,
    base_url: $("imageBaseUrl").value.trim(),
    model: $("imageModel").value.trim(),
    api_key: $("imageApiKey").value.trim(),
    size: $("imageSize").value.trim() || "9:16",
    fixed_prompt: imagePrompt.value,
    ...extra,
  };
}

async function testTextConnection() {
  persistSettings();
  setBusy(true);
  setStatus("测试文案", "busy");
  setTestResult(textConnectionResult, "测试中", "testing");
  try {
    const data = await postJson("/api/settings/test-text", textConnectionPayload());
    setTestResult(textConnectionResult, "连接成功", "ok");
    resultEl.textContent = JSON.stringify({
      "文案连接": "通过",
      "服务": data.provider,
      "模型": data.model,
      "返回": data.sample,
    }, null, 2);
    setStatus("连接正常");
  } catch (err) {
    setTestResult(textConnectionResult, "连接失败", "error");
    setStatus("连接失败", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function testImageConnection() {
  persistSettings();
  setBusy(true);
  setStatus("测试图片", "busy");
  setTestResult(imageConnectionResult, "测试中", "testing");
  try {
    const data = await postJson("/api/settings/test-image", imageConnectionPayload());
    setTestResult(imageConnectionResult, "连接成功", "ok");
    resultEl.textContent = JSON.stringify({
      "图片连接": "通过",
      "服务": data.provider,
      "模型": data.model,
      "返回": data.returned,
    }, null, 2);
    setStatus("连接正常");
  } catch (err) {
    setTestResult(imageConnectionResult, "连接失败", "error");
    setStatus("连接失败", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function loadExample() {
  setStatus("加载中", "busy");
  const res = await fetch("/api/example");
  writeStory(await res.json());
  scheduleProjectSave();
  setStatus("就绪");
}

async function generateStory() {
  persistSettings();
  setBusy(true);
  setStatus("生成中", "busy");
  try {
    const data = await postJson("/api/text/generate", storyPayload());
    writeStory(data);
    resultEl.textContent = JSON.stringify({ "分镜生成": "完成", "镜头数": data.shots?.length || 0 }, null, 2);
    await saveProjectNow();
    setStatus("就绪");
    setTab("image");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function generateCopy() {
  persistSettings();
  setBusy(true);
  setStatus("写口播", "busy");
  try {
    const data = await postJson("/api/text/generate-copy", textPayload());
    copyOutput.value = data.text || "";
    updatePromptMeta();
    setStatus("拆分镜", "busy");
    const story = await postJson("/api/text/copy-to-story", copyToStoryPayload(copyOutput.value));
    writeStory(story);
    resultEl.textContent = JSON.stringify({
      "口播生成": "完成",
      "分镜拆分": "完成",
      "主题": data.topic,
      "字数": copyOutput.value.length,
      "镜头数": story.shots?.length || 0,
    }, null, 2);
    await saveProjectNow();
    setStatus("就绪");
    setTab("image");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function buildStoryboardFromCopy() {
  persistSettings();
  setBusy(true);
  setStatus("拆分镜", "busy");
  try {
    const text = copyOutput.value.trim();
    if (!text) throw new Error("请先生成或填写口播文案");
    const story = await postJson("/api/text/copy-to-story", copyToStoryPayload(text));
    writeStory(story);
    resultEl.textContent = JSON.stringify({
      "分镜拆分": "完成",
      "镜头数": story.shots?.length || 0,
    }, null, 2);
    await saveProjectNow();
    setStatus("就绪");
    setTab("image");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

function createImageProjectId() {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  const rand = Math.random().toString(16).slice(2, 10);
  return `img_${stamp}_${rand}`;
}

function mergeShotImageResult(targetStory, sourceStory, index) {
  const sourceShot = sourceStory?.shots?.[index];
  const targetShot = targetStory?.shots?.[index];
  if (!sourceShot || !targetShot) return targetStory;
  for (const key of ["image_path", "image_url", "resolved_image_prompt"]) {
    if (sourceShot[key]) targetShot[key] = sourceShot[key];
  }
  targetShot._image_status = "done";
  delete targetShot._image_error;
  if (sourceStory.project_id) targetStory.project_id = sourceStory.project_id;
  return targetStory;
}

async function regenerateShotWithRetry(story, index) {
  let lastError = null;
  for (let attempt = 0; attempt <= IMAGE_RETRY_LIMIT; attempt += 1) {
    if (story.shots?.[index]) {
      story.shots[index]._image_status = attempt === 0 ? "generating" : "retrying";
      story.shots[index]._image_attempt = attempt + 1;
      delete story.shots[index]._image_error;
      writeStory(story);
      await saveProjectNow();
    }
    try {
      return await postJson("/api/image/regenerate-shot", imagePayload({ shot_index: index }, story));
    } catch (err) {
      lastError = err;
      if (attempt < IMAGE_RETRY_LIMIT && story.shots?.[index]) {
        story.shots[index]._image_status = "retrying";
        story.shots[index]._image_error = String(err.message || err);
        writeStory(story);
        await saveProjectNow();
      }
    }
  }
  throw lastError;
}

async function generateImagesParallel() {
  persistSettings();
  setBusy(true);
  setStatus("并行生图", "busy");
  try {
    await ensureProjectSaved();
    let story = readStory();
    const shots = story.shots || [];
    if (!Array.isArray(shots) || shots.length === 0) {
      throw new Error("分镜列表为空");
    }
    story = {
      ...story,
      project_id: mediaProjectId() || story.project_id || createImageProjectId(),
      shots: shots.map((shot) => ({
        ...shot,
        _image_status: shot.image_url || shot.image_path ? "done" : "generating",
      })),
    };
    writeStory(story);

    let completed = 0;
    const tasks = story.shots.map((_, index) =>
      regenerateShotWithRetry(story, index)
        .then(async (data) => {
          story = mergeShotImageResult(story, data, index);
          completed += 1;
          writeStory(story);
          resultEl.textContent = JSON.stringify({
            "图片生成": "并行进行中",
            "已完成": completed,
            "总镜头数": shots.length,
            "最近完成镜头": index + 1,
            "项目编号": story.project_id,
          }, null, 2);
          setStatus(`生图 ${completed}/${shots.length}`, "busy");
          await saveProjectNow();
          return data;
        })
        .catch(async (err) => {
          if (story.shots?.[index]) {
            story.shots[index]._image_status = "error";
            story.shots[index]._image_error = String(err.message || err);
            writeStory(story);
            await saveProjectNow();
          }
          throw err;
        })
    );

    const results = await Promise.allSettled(tasks);
    const failed = results.filter((item) => item.status === "rejected");
    if (failed.length) {
      throw new Error(`并行生图完成 ${completed}/${shots.length}，失败 ${failed.length} 张：${failed[0].reason?.message || failed[0].reason}`);
    }

    resultEl.textContent = JSON.stringify({
      "图片生成": "完成",
      "项目编号": story.project_id,
      "镜头数": story.shots?.length || 0,
    }, null, 2);
    setStatus("就绪");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function generateImages() {
  persistSettings();
  setBusy(true);
  setStatus("生图中", "busy");
  try {
    await ensureProjectSaved();
    let story = readStory();
    const shots = story.shots || [];
    if (!Array.isArray(shots) || shots.length === 0) {
      throw new Error("分镜列表为空");
    }
    story = {
      ...story,
      project_id: mediaProjectId() || story.project_id || createImageProjectId(),
      shots: shots.map((shot) => ({
        ...shot,
        _image_status: shot.image_url || shot.image_path ? "done" : "pending",
      })),
    };
    writeStory(story);
    for (let index = 0; index < shots.length; index += 1) {
      setStatus(`生图 ${index + 1}/${shots.length}`, "busy");
      const data = await regenerateShotWithRetry(story, index);
      story = mergeShotImageResult(story, data, index);
      writeStory(story);
      resultEl.textContent = JSON.stringify({
        "图片生成": "进行中",
        "当前镜头": index + 1,
        "总镜头数": shots.length,
        "项目编号": story.project_id,
      }, null, 2);
      await saveProjectNow();
    }
    resultEl.textContent = JSON.stringify({
      "图片生成": "完成",
      "项目编号": story.project_id,
      "镜头数": story.shots?.length || 0,
    }, null, 2);
    setStatus("就绪");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

async function redrawShot(index) {
  persistSettings();
  selectedShot = index;
  setBusy(true);
  setStatus("重抽中", "busy");
  try {
    await ensureProjectSaved();
    let story = readStory();
    if (!story.project_id) {
      story = {...story, project_id: mediaProjectId() || createImageProjectId()};
      writeStory(story);
    }
    const data = await regenerateShotWithRetry(story, index);
    story = mergeShotImageResult(story, data, index);
    writeStory(story);
    resultEl.textContent = JSON.stringify({
      "重抽": "完成",
      "镜头": index + 1,
      "项目编号": data.project_id,
    }, null, 2);
    setStatus("就绪");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

function validateJson() {
  try {
    const story = readStory();
    if (!Array.isArray(story.shots) || story.shots.length === 0) {
      throw new Error("分镜数据里必须有镜头列表");
    }
    for (const [i, shot] of story.shots.entries()) {
      if (!shot.voiceover) throw new Error(`第 ${i + 1} 个镜头缺少口播`);
    }
    resultEl.textContent = JSON.stringify({
      "校验": "通过",
      "标题": story.title,
      "镜头数": story.shots.length,
      "图片数": story.shots.filter((shot) => shot.image_path || shot.image_url).length,
    }, null, 2);
    setStatus("已通过");
  } catch (err) {
    setStatus("无效", "error");
    resultEl.textContent = String(err.message || err);
  }
}

async function renderVideo() {
  persistSettings();
  setBusy(true);
  setStatus("渲染中", "busy");
  openVideo.hidden = true;
  preview.removeAttribute("src");
  try {
    await ensureProjectSaved();
    const data = await postJson("/api/render", {
      story: readStory(),
      voice: $("voice").value,
      rate: $("rate").value,
      project_id: mediaProjectId(),
    });
    resultEl.textContent = JSON.stringify(data, null, 2);
    preview.src = data.video;
    openVideo.href = data.video;
    openVideo.hidden = false;
    await saveProjectNow();
    setStatus("完成");
  } catch (err) {
    setStatus("出错", "error");
    resultEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
  }
}

function shotImageSrc(shot) {
  if (shot.image_url) return `${shot.image_url}?v=${Date.now()}`;
  if (shot.image_path) {
    const normalized = String(shot.image_path).replaceAll("\\", "/");
    const marker = "/workspace/";
    const index = normalized.toLowerCase().lastIndexOf(marker);
    if (index >= 0) {
      return `/workspace/${normalized.slice(index + marker.length)}?v=${Date.now()}`;
    }
  }
  return "";
}

function renderShotGrid() {
  if (!shotGrid) return;
  let story;
  try {
    story = readStory();
  } catch {
    shotGrid.innerHTML = '<div class="shot-placeholder">JSON 无效</div>';
    return;
  }
  const shots = story.shots || [];
  if (selectedShot >= shots.length) selectedShot = 0;
  selectedShotLabel.textContent = shots[selectedShot] ? `选中镜头 ${selectedShot + 1}` : "未选择镜头";
  shotGrid.innerHTML = shots.map((shot, index) => {
    const src = shotImageSrc(shot);
    const status = shot._image_status || "";
    const placeholderText = status === "generating"
      ? "生成中"
      : status === "retrying"
        ? `重试中 ${shot._image_attempt || ""}`
      : status === "error"
        ? "生成失败"
        : "等待生成";
    const placeholderClass = status === "generating" || status === "retrying" ? " generating" : status === "error" ? " error" : "";
    const thumb = src
      ? `<img src="${src}" alt="镜头 ${index + 1}" />`
      : `<div class="shot-placeholder${placeholderClass}">镜头 ${index + 1}<br />${placeholderText}</div>`;
    const selected = index === selectedShot ? " selected" : "";
    const punch = shot.punch || shot.keyword || `镜头 ${index + 1}`;
    const voiceover = shot.voiceover || "";
    return `
      <article class="shot-card${selected}" data-shot="${index}">
        <button class="shot-thumb" type="button" data-select-shot="${index}" aria-label="选择镜头 ${index + 1}">${thumb}</button>
        <div class="shot-info">
          <div class="shot-title-row">
            <strong>${escapeHtml(punch)}</strong>
            <span>${String(index + 1).padStart(2, "0")}</span>
          </div>
          <p>${escapeHtml(voiceover)}</p>
          <div class="shot-actions">
            <button class="pearl-button" type="button" data-select-shot="${index}">选择</button>
            <button class="pearl-button" type="button" data-redraw-shot="${index}">重抽</button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.addEventListener("click", (event) => {
  const tabButton = event.target.closest("[data-tab]");
  if (tabButton) setTab(tabButton.dataset.tab);

  const selectButton = event.target.closest("[data-select-shot]");
  if (selectButton) {
    selectedShot = Number(selectButton.dataset.selectShot);
    renderShotGrid();
  }

  const redrawButton = event.target.closest("[data-redraw-shot]");
  if (redrawButton) redrawShot(Number(redrawButton.dataset.redrawShot));
});

$("loadExample").addEventListener("click", loadExample);
$("generate").addEventListener("click", generateStory);
$("generateCopy").addEventListener("click", generateCopy);
$("buildStoryboard").addEventListener("click", buildStoryboardFromCopy);
$("generateImages").addEventListener("click", generateImagesParallel);
$("redrawSelected").addEventListener("click", () => redrawShot(selectedShot));
$("refreshGallery").addEventListener("click", renderShotGrid);
$("validate").addEventListener("click", validateJson);
$("render").addEventListener("click", renderVideo);
$("saveProject").addEventListener("click", async () => {
  setStatus("保存中", "busy");
  await saveProjectNow();
  setStatus("就绪");
});
$("newProject").addEventListener("click", newProject);
projectPicker.addEventListener("change", () => {
  if (projectPicker.value) activateProject(projectPicker.value);
});
$("openSettings").addEventListener("click", openSettings);
$("closeSettings").addEventListener("click", closeSettings);
$("settingsBackdrop").addEventListener("click", closeSettings);
$("testTextConnection").addEventListener("click", testTextConnection);
$("testImageConnection").addEventListener("click", testImageConnection);
$("resetCopyPrompt").addEventListener("click", () => {
  copyPrompt.value = defaultCopyPrompt;
  persistSettings();
  updatePromptMeta();
  scheduleProjectSave();
});
$("resetImagePrompt").addEventListener("click", () => {
  imagePrompt.value = defaultImagePrompt;
  persistSettings();
  updatePromptMeta();
  scheduleProjectSave();
});
editor.addEventListener("input", () => {
  updateMeta();
  if (activeTab === "image") renderShotGrid();
  scheduleProjectSave();
});
copyPrompt.addEventListener("input", () => {
  persistSettings();
  updatePromptMeta();
  scheduleProjectSave();
});
copyOutput.addEventListener("input", () => {
  updatePromptMeta();
  scheduleProjectSave();
});
imagePrompt.addEventListener("input", () => {
  persistSettings();
  updatePromptMeta();
  scheduleProjectSave();
});
$("topic").addEventListener("input", () => {
  persistSettings();
  scheduleProjectSave();
});

for (const id of ["textProvider", "baseUrl", "model", "apiKey", "imageProvider", "imageBaseUrl", "imageModel", "imageApiKey", "imageSize", "voice", "rate"]) {
  $(id).addEventListener("change", persistSettings);
}
for (const id of ["apiKey", "imageApiKey"]) {
  $(id).addEventListener("input", persistSettings);
}
$("textProvider").addEventListener("change", () => {
  applyTextProviderDefaults();
  persistSettings();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeSettings();
});

loadSettings();
loadPromptDefaults()
  .catch(() => updatePromptMeta())
  .then(() => loadProjectState())
  .then((restored) => {
    if (!restored) return loadExample();
    setStatus("就绪");
    return null;
  })
  .then(() => loadProjectList())
  .catch(() => setStatus("就绪"));
