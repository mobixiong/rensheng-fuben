import { escapeHtml } from "./html.js";

export function createStoryView({ els, getSelectedShots, setSelectedShots, getActiveTab, onStoryChanged }) {
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

  function withImageVersion(src, shot) {
    if (!shot._image_version) return src;
    return `${src}${src.includes("?") ? "&" : "?"}v=${encodeURIComponent(shot._image_version)}`;
  }

  function shotImageSrc(shot) {
    if (shot.image_url) return withImageVersion(shot.image_url, shot);
    if (shot.image_path) {
      const normalized = String(shot.image_path).replaceAll("\\", "/");
      const marker = "/workspace/";
      const index = normalized.toLowerCase().lastIndexOf(marker);
      if (index >= 0) {
        return withImageVersion(`/workspace/${normalized.slice(index + marker.length)}`, shot);
      }
    }
    return "";
  }

  function normalizeImageRatio(value) {
    const ratio = String(value || "").trim();
    if (ratio === "9:16" || ratio === "9 / 16") return "9 / 16";
    if (ratio === "1:1" || ratio === "1 / 1") return "1 / 1";
    if (ratio === "16:9" || ratio === "16 / 9") return "16 / 9";
    return "";
  }

  function ratioFromImageSize(width, height) {
    const imageRatio = width / height;
    if (!Number.isFinite(imageRatio) || imageRatio < 0.4 || imageRatio > 2.25) return "";
    return `${width} / ${height}`;
  }

  function shotImageRatio(shot, story) {
    return normalizeImageRatio(shot.image_size)
      || normalizeImageRatio(shot.size)
      || normalizeImageRatio(story.image_size)
      || normalizeImageRatio(els.imageSize?.value)
      || "9 / 16";
  }

  function hydrateLoadedImageRatios() {
    for (const img of els.shotGrid.querySelectorAll(".shot-thumb img")) {
      const applyRatio = () => {
        if (!img.naturalWidth || !img.naturalHeight) return;
        const ratio = ratioFromImageSize(img.naturalWidth, img.naturalHeight);
        if (ratio) img.closest(".shot-card")?.style.setProperty("--shot-ratio", ratio);
      };
      img.addEventListener("load", applyRatio, { once: true });
      if (img.complete) applyRatio();
    }
  }

  function normalizeSelectedShots(shotsLength) {
    const raw = getSelectedShots?.();
    const values = raw instanceof Set ? Array.from(raw) : Array.isArray(raw) ? raw : [];
    const normalized = values
      .map(Number)
      .filter((index) => Number.isInteger(index) && index >= 0 && index < shotsLength);
    const unique = Array.from(new Set(normalized)).sort((a, b) => a - b);
    if (unique.length !== values.length || unique.some((index, position) => index !== normalized[position])) {
      setSelectedShots(unique);
    }
    return new Set(unique);
  }

  function selectionLabel(count, shotsLength) {
    if (!shotsLength || !count) return "未选择图片";
    return `已选 ${count} 张图片`;
  }

  function updateSelection() {
    const cards = Array.from(els.shotGrid.querySelectorAll(".shot-card"));
    const selectedShots = normalizeSelectedShots(cards.length);
    els.selectedShotLabel.textContent = selectionLabel(selectedShots.size, cards.length);
    for (const card of cards) {
      const selected = selectedShots.has(Number(card.dataset.shot));
      card.classList.toggle("selected", selected);
      card.setAttribute("aria-selected", String(selected));
      const thumb = card.querySelector(".shot-thumb");
      if (thumb) thumb.setAttribute("aria-pressed", String(selected));
    }
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
    const selectedShots = normalizeSelectedShots(shots.length);
    els.selectedShotLabel.textContent = selectionLabel(selectedShots.size, shots.length);
    els.shotGrid.innerHTML = shots.map((shot, index) => {
      const src = shotImageSrc(shot);
      const ratio = shotImageRatio(shot, story);
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
      const selected = selectedShots.has(index) ? " selected" : "";
      const punch = shot.punch || shot.keyword || `镜头 ${index + 1}`;
      const voiceover = shot.voiceover || "";
      return `
        <article class="shot-card${selected}" data-shot="${index}" style="--shot-ratio: ${ratio}">
          <div class="shot-thumb" data-select-shot="${index}" role="button" tabindex="0" aria-pressed="${selected ? "true" : "false"}" aria-label="切换选择镜头 ${index + 1}">
            <span class="state-badge ${statusClass}">${statusLabel}</span>
            <button class="shot-redraw-button" type="button" data-redraw-shot="${index}" title="重抽" aria-label="重抽镜头 ${index + 1}">↻</button>
            ${thumb}
          </div>
          <div class="shot-info">
            <div class="shot-title-row">
              <strong>${escapeHtml(punch)}</strong>
              <span>${String(index + 1).padStart(2, "0")}</span>
            </div>
            <p>${escapeHtml(voiceover)}</p>
          </div>
        </article>
      `;
    }).join("");
    hydrateLoadedImageRatios();
    updateSelection();
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
    updateSelection,
    onEditorInput,
    validate,
  };
}
