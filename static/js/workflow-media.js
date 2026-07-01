import { INTRO_TEMPLATES } from "./constants.js";

const INTRO_TEMPLATE_LABELS = {
  life_copy_fast_cut: "翻页快切模板",
  life_copy_expand_cut: "展开快切模板",
  life_copy_flash_horizontal: "横向羽化快闪模板",
  life_copy_flash_vertical: "纵向羽化快闪模板",
  life_copy_staggered_mask: "阶梯遮罩接力模板",
  none: "无模板",
};

const INTRO_TEMPLATE_PREVIEW_ITEMS = [
  ...INTRO_TEMPLATES.filter((id) => id !== "none"),
  "none",
].map((id) => ({
  id,
  video: `/static/assets/intro-previews/${id}.mp4`,
}));

export function createMediaWorkflow({ els, ui, api, settings, projectStore }) {
  function openIntroPreviewModal() {
    if (!els.introPreviewModal) return;
    els.introPreviewModal.hidden = false;
  }

  function closeIntroPreviewModal() {
    if (!els.introPreviewModal) return;
    els.introPreviewModal.hidden = true;
  }

  function fillAudioOptions(select, items, selected, fallback, fallbackText) {
    if (!select) return;
    select.replaceChildren();

    const fallbackOption = document.createElement("option");
    fallbackOption.value = fallback;
    fallbackOption.textContent = fallbackText;
    select.appendChild(fallbackOption);

    for (const item of items) {
      const id = String(item.id || "").trim();
      if (!id || id === fallback) continue;
      const option = document.createElement("option");
      option.value = id;
      option.textContent = String(item.name || item.filename || id);
      select.appendChild(option);
    }

    select.value = Array.from(select.options).some((option) => option.value === selected) ? selected : fallback;
  }

  async function loadBgmOptions(selectedValue = "") {
    if (!els.bgmSelect) return;
    const selected = selectedValue || els.bgmSelect.value || "none";
    const data = await api.fetchJson("/api/bgm");
    const items = Array.isArray(data.items) ? data.items : [];
    fillAudioOptions(els.bgmSelect, items, selected, "none", "无 BGM");
  }

  async function loadIntroSfxOptions(selectedValue = "") {
    if (!els.introSfxSelect) return;
    const selected = selectedValue || els.introSfxSelect.value || "default";
    const data = await api.fetchJson("/api/intro-sfx");
    const items = Array.isArray(data.items) ? data.items : [];
    fillAudioOptions(els.introSfxSelect, items, selected, "default", "默认齿轮音效");
    const hasNone = Array.from(els.introSfxSelect.options).some((option) => option.value === "none");
    if (!hasNone) {
      const noneOption = document.createElement("option");
      noneOption.value = "none";
      noneOption.textContent = "无音效";
      els.introSfxSelect.insertBefore(noneOption, els.introSfxSelect.options[1] || null);
    }
    els.introSfxSelect.value = Array.from(els.introSfxSelect.options).some((option) => option.value === selected) ? selected : "default";
  }

  async function uploadAudioAsset({ input, endpoint, reload, label }) {
    const file = input?.files?.[0];
    if (!file) {
      ui.setStatus(`请选择${label}文件`, "error");
      return;
    }
    ui.setBusy(true);
    ui.setStatus(`上传${label}`, "busy");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api.postForm(endpoint, form);
      await reload(data.id);
      input.value = "";
      settings.persist();
      projectStore.scheduleSave();
      ui.setStatus(`${label}已上传`);
    } catch (err) {
      ui.setStatus("上传失败", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  function uploadBgm() {
    return uploadAudioAsset({
      input: els.bgmUploadFile,
      endpoint: "/api/bgm/upload",
      reload: loadBgmOptions,
      label: "BGM",
    });
  }

  function uploadIntroSfx() {
    return uploadAudioAsset({
      input: els.introSfxUploadFile,
      endpoint: "/api/intro-sfx/upload",
      reload: loadIntroSfxOptions,
      label: "开头音效",
    });
  }

  function renderIntroPreviewGrid(data) {
    if (!els.introPreviewGrid) return;
    const items = Array.isArray(data?.items) ? data.items : [];
    els.introPreviewGrid.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "intro-preview-empty";
      empty.textContent = "暂无预览";
      els.introPreviewGrid.appendChild(empty);
      return;
    }
    for (const item of items) {
      const templateId = String(item.id || "");
      const card = document.createElement("button");
      card.type = "button";
      card.className = "intro-preview-card";
      card.dataset.template = templateId;
      card.classList.toggle("active", els.introTemplate?.value === templateId);

      const video = document.createElement("video");
      video.src = String(item.video || "");
      video.controls = true;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.addEventListener("click", (event) => event.stopPropagation());

      const label = document.createElement("span");
      label.textContent = INTRO_TEMPLATE_LABELS[templateId] || templateId;

      card.append(video, label);
      card.addEventListener("click", () => {
        if (els.introTemplate) els.introTemplate.value = templateId;
        for (const node of els.introPreviewGrid.querySelectorAll(".intro-preview-card")) {
          node.classList.toggle("active", node === card);
        }
        settings.persist();
        projectStore.scheduleSave();
      });
      els.introPreviewGrid.appendChild(card);
    }
  }

  async function previewIntroTemplates() {
    settings.persist();
    openIntroPreviewModal();
    renderIntroPreviewGrid({ items: INTRO_TEMPLATE_PREVIEW_ITEMS });
    ui.setStatus("开头模板预览已打开");
  }

  return {
    loadBgmOptions,
    loadIntroSfxOptions,
    uploadBgm,
    uploadIntroSfx,
    previewIntroTemplates,
    closeIntroPreviewModal,
  };
}
