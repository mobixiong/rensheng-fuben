import { escapeHtml } from "./html.js";

export function createStoryView({ els, getSelectedShot, setSelectedShot, getActiveTab, onStoryChanged }) {
  function read() {
    return JSON.parse(els.editor.value);
  }

  function readOrNull() {
    try {
      return read();
    } catch {
      return null;
    }
  }

  function write(story, options = {}) {
    const { scheduleSave = true } = options;
    els.editor.value = JSON.stringify(story, null, 2);
    updateMeta();
    renderShotGrid();
    if (scheduleSave) onStoryChanged();
  }

  function updateMeta() {
    try {
      const story = read();
      const shots = story.shots?.length || 0;
      const imageCount = (story.shots || []).filter((shot) => shot.image_path || shot.image_url).length;
      els.jsonMeta.textContent = `${shots} 个镜头 · ${imageCount} 张图`;
    } catch {
      els.jsonMeta.textContent = "分镜数据无效";
    }
  }

  function updatePromptMeta() {
    if (els.copyPromptMeta) els.copyPromptMeta.textContent = `${els.copyPrompt.value.length} 字`;
    if (els.copyMeta) els.copyMeta.textContent = `${els.copyOutput.value.length} 字`;
    if (els.imagePromptMeta) els.imagePromptMeta.textContent = `${els.imagePrompt.value.length} 字`;
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
    if (!els.shotGrid) return;
    let story;
    try {
      story = read();
    } catch {
      els.shotGrid.innerHTML = '<div class="shot-placeholder">JSON 无效</div>';
      return;
    }
    const shots = story.shots || [];
    if (getSelectedShot() >= shots.length) setSelectedShot(0);
    const selectedShot = getSelectedShot();
    els.selectedShotLabel.textContent = shots[selectedShot] ? `选中镜头 ${selectedShot + 1}` : "未选择镜头";
    els.shotGrid.innerHTML = shots.map((shot, index) => {
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
      const statusLabel = src
        ? "已完成"
        : status === "generating"
          ? "生成中"
          : status === "retrying"
            ? "重试中"
            : status === "error"
              ? "失败"
              : "等待中";
      const statusClass = src
        ? "done"
        : status === "generating" || status === "retrying"
          ? "generating"
          : status === "error"
            ? "error"
            : "pending";
      const thumb = src
        ? `<img src="${src}" alt="镜头 ${index + 1}" />`
        : `<div class="shot-placeholder${placeholderClass}">镜头 ${index + 1}<br />${placeholderText}</div>`;
      const selected = index === selectedShot ? " selected" : "";
      const punch = shot.punch || shot.keyword || `镜头 ${index + 1}`;
      const voiceover = shot.voiceover || "";
      return `
        <article class="shot-card${selected}" data-shot="${index}">
          <button class="shot-thumb" type="button" data-select-shot="${index}" aria-label="选择镜头 ${index + 1}">
            <span class="state-badge ${statusClass}">${statusLabel}</span>
            ${thumb}
          </button>
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

  function onEditorInput() {
    updateMeta();
    if (getActiveTab() === "image") renderShotGrid();
    onStoryChanged();
  }

  function validate(resultEl, setStatus) {
    try {
      const story = read();
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

  return {
    read,
    readOrNull,
    write,
    updateMeta,
    updatePromptMeta,
    renderShotGrid,
    onEditorInput,
    validate,
  };
}
