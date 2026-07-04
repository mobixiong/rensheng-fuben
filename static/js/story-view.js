import { IMAGE_SIZES } from "./constants.js";
import { escapeHtml } from "./html.js";
import { imageDisplayState } from "./image-state.js";

export function createStoryView({
  els,
  getSelectedShots,
  setSelectedShots,
  getActiveTab,
  getActiveImageJob,
  getActiveImageStatus,
  onStoryChanged,
}) {
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
    if (els.themeIntroMeta) els.themeIntroMeta.textContent = `${els.themeIntro?.value.length || 0} 字`;
    if (els.themeIdeaPromptMeta) els.themeIdeaPromptMeta.textContent = `${els.themeIdeaPrompt?.value.length || 0} 字`;
    if (els.copyPromptMeta) els.copyPromptMeta.textContent = `${els.copyPrompt.value.length} 字`;
    if (els.copyMeta) els.copyMeta.textContent = `${els.copyOutput.value.length} 字`;
    if (els.copyToStoryPromptMeta) els.copyToStoryPromptMeta.textContent = `${els.copyToStoryPrompt.value.length} 字`;
    if (els.imagePromptMeta) els.imagePromptMeta.textContent = `${els.imagePrompt.value.length} 字`;
    if (els.improveImagePromptMeta) els.improveImagePromptMeta.textContent = `${els.improveImagePrompt?.value.length || 0} 字`;
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
    if (ratio === IMAGE_SIZES[0] || ratio === "9 / 16") return "9 / 16";
    if (ratio === IMAGE_SIZES[1] || ratio === "1 / 1") return "1 / 1";
    if (ratio === IMAGE_SIZES[2] || ratio === "16 / 9") return "16 / 9";
    return "";
  }

  function normalizeImageSizeToken(value) {
    const ratio = String(value || "").trim();
    if (ratio === IMAGE_SIZES[0] || ratio === "9 / 16") return IMAGE_SIZES[0];
    if (ratio === IMAGE_SIZES[1] || ratio === "1 / 1") return IMAGE_SIZES[1];
    if (ratio === IMAGE_SIZES[2] || ratio === "16 / 9") return IMAGE_SIZES[2];
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

  function withImageSize(story, size) {
    const imageSize = normalizeImageSizeToken(size);
    if (!imageSize || !story || typeof story !== "object") return story;
    return {
      ...story,
      image_size: imageSize,
      shots: Array.isArray(story.shots)
        ? story.shots.map((shot) => ({ ...shot, image_size: imageSize }))
        : story.shots,
    };
  }

  function applyImageSize(size, options = {}) {
    try {
      write(withImageSize(read(), size), options);
    } catch {
      renderShotGrid();
    }
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

  function updateSelection(options = {}) {
    const { persist = false } = options;
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
    if (persist) onStoryChanged();
  }

  function getShotImagePrompt(index) {
    const story = readOrNull();
    const shot = story?.shots?.[Number(index)];
    return String(shot?.image_prompt || "");
  }

  function setShotImagePromptStatus(index, status, message = "") {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return false;
    const story = read();
    if (!Array.isArray(story.shots) || !story.shots[shotIndex]) return false;
    if (status) {
      story.shots[shotIndex]._image_prompt_status = status;
      story.shots[shotIndex]._image_prompt_message = message;
    } else {
      delete story.shots[shotIndex]._image_prompt_status;
      delete story.shots[shotIndex]._image_prompt_message;
    }
    write(story);
    return true;
  }

  function updateShotImagePrompt(index, value, options = {}) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return false;
    const story = read();
    if (!Array.isArray(story.shots) || !story.shots[shotIndex]) return false;
    story.shots[shotIndex].image_prompt = String(value || "").trim();
    story.shots[shotIndex]._image_prompt_edited_at = Date.now();
    if (options.status) {
      story.shots[shotIndex]._image_prompt_status = options.status;
      story.shots[shotIndex]._image_prompt_message = options.message || "";
    } else {
      delete story.shots[shotIndex]._image_prompt_status;
      delete story.shots[shotIndex]._image_prompt_message;
    }
    delete story.shots[shotIndex].resolved_image_prompt;
    write(story);
    return true;
  }

  function setShotAsCover(index) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return false;
    const story = read();
    const shot = story.shots?.[shotIndex];
    if (!shot) return false;
    const src = shotImageSrc(shot);
    const title = String(els.topic?.value || story.title || "").trim();
    story.cover = {
      ...(story.cover || {}),
      title,
      source_shot_index: shotIndex,
      image_prompt: String(shot.image_prompt || shot.visual || shot.voiceover || "").trim(),
      image_path: shot.image_path || "",
      image_url: shot.image_url || src || "",
      image_size: shot.image_size || story.image_size || els.imageSize?.value || "",
      _cover_status: src ? "selected" : "pending",
      _cover_version: Date.now(),
    };
    delete story.cover.raw_image_path;
    delete story.cover.raw_image_url;
    delete story.cover._cover_error;
    write(story);
    return true;
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
    const coverShotIndex = Number(story.cover?.source_shot_index);
    els.selectedShotLabel.textContent = selectionLabel(selectedShots.size, shots.length);
    els.shotGrid.innerHTML = shots.map((shot, index) => {
      const src = shotImageSrc(shot);
      const ratio = shotImageRatio(shot, story);
      const activeJob = getActiveImageJob?.(index) || null;
      const activeStatus = activeJob?.status || getActiveImageStatus?.(index) || "";
      const displayState = imageDisplayState(shot, { activeJob, activeStatus, hasImage: Boolean(src) });
      const placeholderText = displayState.placeholderText;
      const placeholderClass = displayState.placeholderClass;
      const statusLabel = displayState.statusLabel;
      const statusClass = displayState.statusClass;
      const isImageBusy = displayState.isBusy;
      const redrawDisabled = isImageBusy ? " disabled" : "";
      const redrawTitle = isImageBusy ? statusLabel : "重抽";
      const errorTitle = shot._image_error ? ` title="${escapeHtml(String(shot._image_error))}"` : "";
      const thumb = src
        ? `<img src="${src}" alt="镜头 ${index + 1}" />`
        : `<div class="shot-placeholder${placeholderClass}">镜头 ${index + 1}<br />${placeholderText}</div>`;
      const selected = selectedShots.has(index) ? " selected" : "";
      const isCover = Number.isInteger(coverShotIndex) && coverShotIndex === index;
      const coverClass = isCover ? " cover-selected" : "";
      const coverLabel = isCover ? `<span class="cover-badge">封面</span>` : "";
      const coverDisabled = src ? "" : " disabled";
      const punch = shot.punch || shot.keyword || `镜头 ${index + 1}`;
      const voiceover = shot.voiceover || "";
      const imagePrompt = String(shot.image_prompt || "");
      const promptPreview = imagePrompt || "双击填写图片提示词";
      const promptTitle = imagePrompt || "双击填写图片提示词";
      const promptStatus = String(shot._image_prompt_status || "");
      const promptMessage = String(shot._image_prompt_message || "");
      const promptStatusLabel = promptStatus === "optimizing"
        ? "AI 正在优化..."
        : promptStatus === "optimized"
          ? "AI 已优化"
          : promptStatus === "error"
            ? `AI 优化失败${promptMessage ? `：${promptMessage}` : ""}`
            : "";
      const promptStatusHtml = promptStatusLabel
        ? `<div class="shot-prompt-status ${escapeHtml(promptStatus)}" title="${escapeHtml(promptStatusLabel)}">${escapeHtml(promptStatusLabel)}</div>`
        : "";
      const referenceAsset = shot.primary_reference_asset || null;
      const referenceName = referenceAsset?.name || "";
      const referenceReason = shot._reference_selection?.reason || "";
      const referenceHtml = referenceName
        ? `<div class="shot-reference" title="${escapeHtml(referenceReason || referenceName)}">主参考图：${escapeHtml(referenceName)}</div>`
        : "";
      const aiDisabled = promptStatus === "optimizing" ? " disabled" : "";
      const aiLabel = promptStatus === "optimizing" ? "优化中" : "AI";
      return `
        <article class="shot-card${selected}${coverClass}" data-shot="${index}" style="--shot-ratio: ${ratio}">
          <div class="shot-thumb" data-select-shot="${index}" role="button" tabindex="0" aria-pressed="${selected ? "true" : "false"}" aria-label="切换选择镜头 ${index + 1}">
            <span class="state-badge ${statusClass}"${errorTitle}>${statusLabel}</span>
            ${coverLabel}
            <button class="shot-redraw-button" type="button" data-redraw-shot="${index}" title="${escapeHtml(redrawTitle)}" aria-label="重抽镜头 ${index + 1}"${redrawDisabled}>↻</button>
            ${thumb}
          </div>
          <div class="shot-info">
            <div class="shot-title-row">
              <strong>${escapeHtml(punch)}</strong>
              <span>${String(index + 1).padStart(2, "0")}</span>
            </div>
            <button class="text-action shot-cover-button" type="button" data-set-cover-shot="${index}"${coverDisabled}>${isCover ? "已设为封面" : "设为封面"}</button>
            <p>${escapeHtml(voiceover)}</p>
            <div class="shot-prompt" data-edit-shot-prompt="${index}" title="${escapeHtml(promptTitle)}" role="button" tabindex="0" aria-label="编辑镜头 ${index + 1} 图片提示词">
              <div class="shot-prompt-head">
                <strong>图片提示词</strong>
                <span>${imagePrompt.length} 字</span>
                <button class="shot-prompt-ai" type="button" data-ai-shot-prompt="${index}" title="AI 优化图片提示词" aria-label="AI 优化镜头 ${index + 1} 图片提示词"${aiDisabled}>${aiLabel}</button>
              </div>
              <p>${escapeHtml(promptPreview)}</p>
              ${promptStatusHtml}
              ${referenceHtml}
            </div>
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
    withImageSize,
    applyImageSize,
    getShotImagePrompt,
    setShotImagePromptStatus,
    updateShotImagePrompt,
    setShotAsCover,
  };
}
