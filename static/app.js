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
const SETTINGS_KEY = "rensheng-fuben-settings";
const GEMINI_WEB2API_DEFAULT_BASE_URL = "http://127.0.0.1:8081/v1";
const GEMINI_WEB2API_DEFAULT_MODEL = "gemini-3.5-flash-thinking";

let activeTab = "copy";
let selectedShot = 0;
let defaultCopyPrompt = "";
let defaultImagePrompt = "";

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = `status-pill ${kind}`.trim();
}

function setBusy(busy) {
  for (const id of ["loadExample", "generate", "generateCopy", "buildStoryboard", "generateImages", "redrawSelected", "validate", "render", "refreshGallery", "resetCopyPrompt", "resetImagePrompt"]) {
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

function persistSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    textProvider: $("textProvider").value,
    baseUrl: $("baseUrl").value,
    model: $("model").value,
    imageProvider: $("imageProvider").value,
    imageBaseUrl: $("imageBaseUrl").value,
    imageModel: $("imageModel").value,
    imageSize: $("imageSize").value,
    voice: $("voice").value,
    rate: $("rate").value,
    copyPrompt: copyPrompt.value,
    imagePrompt: imagePrompt.value,
  }));
}

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
    $("textProvider").value = ["openai", "gemini_web2api"].includes(s.textProvider) ? s.textProvider : "openai";
    $("baseUrl").value = s.baseUrl || "";
    $("model").value = s.model || "";
    $("imageProvider").value = s.imageProvider === "openai" ? s.imageProvider : "openai";
    $("imageBaseUrl").value = s.imageBaseUrl || "";
    $("imageModel").value = s.imageModel || "";
    $("imageSize").value = s.imageSize || "1024x1792";
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

function imagePayload(extra = {}) {
  return {
    story: readStory(),
    provider: $("imageProvider").value,
    base_url: $("imageBaseUrl").value.trim(),
    model: $("imageModel").value.trim(),
    api_key: $("imageApiKey").value.trim(),
    size: $("imageSize").value.trim() || "1024x1792",
    fixed_prompt: imagePrompt.value,
    ...extra,
  };
}

async function loadExample() {
  setStatus("加载中", "busy");
  const res = await fetch("/api/example");
  writeStory(await res.json());
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
    setStatus("就绪");
    setTab("image");
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
    const data = await postJson("/api/image/generate-story", imagePayload());
    writeStory(data);
    resultEl.textContent = JSON.stringify({
      "图片生成": "完成",
      "项目编号": data.project_id,
      "镜头数": data.shots?.length || 0,
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
    const data = await postJson("/api/image/regenerate-shot", imagePayload({ shot_index: index }));
    writeStory(data);
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
    const data = await postJson("/api/render", {
      story: readStory(),
      voice: $("voice").value,
      rate: $("rate").value,
    });
    resultEl.textContent = JSON.stringify(data, null, 2);
    preview.src = data.video;
    openVideo.href = data.video;
    openVideo.hidden = false;
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
    const thumb = src
      ? `<img src="${src}" alt="镜头 ${index + 1}" />`
      : `<div class="shot-placeholder">镜头 ${index + 1}<br />等待生成</div>`;
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
$("generateImages").addEventListener("click", generateImages);
$("redrawSelected").addEventListener("click", () => redrawShot(selectedShot));
$("refreshGallery").addEventListener("click", renderShotGrid);
$("validate").addEventListener("click", validateJson);
$("render").addEventListener("click", renderVideo);
$("resetCopyPrompt").addEventListener("click", () => {
  copyPrompt.value = defaultCopyPrompt;
  persistSettings();
  updatePromptMeta();
});
$("resetImagePrompt").addEventListener("click", () => {
  imagePrompt.value = defaultImagePrompt;
  persistSettings();
  updatePromptMeta();
});
editor.addEventListener("input", () => {
  updateMeta();
  if (activeTab === "image") renderShotGrid();
});
copyPrompt.addEventListener("input", () => {
  persistSettings();
  updatePromptMeta();
});
copyOutput.addEventListener("input", updatePromptMeta);
imagePrompt.addEventListener("input", () => {
  persistSettings();
  updatePromptMeta();
});

for (const id of ["textProvider", "baseUrl", "model", "imageProvider", "imageBaseUrl", "imageModel", "imageSize", "voice", "rate"]) {
  $(id).addEventListener("change", persistSettings);
}
$("textProvider").addEventListener("change", () => {
  applyTextProviderDefaults();
  persistSettings();
});

loadSettings();
loadPromptDefaults().catch(() => updatePromptMeta());
loadExample().catch(() => setStatus("就绪"));
