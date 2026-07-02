import { escapeHtml } from "./html.js";

const ASSET_TYPES = [
  ["character", "人物"],
  ["scene", "场景"],
  ["prop", "道具"],
  ["costume", "服装"],
  ["style", "风格"],
  ["other", "其他"],
];

function typeLabel(value) {
  return ASSET_TYPES.find(([key]) => key === value)?.[1] || "其他";
}

export function createReferenceAssets({
  els,
  ui,
  api,
  state,
  projectStore,
  storyView,
}) {
  let collections = [];
  let activeCollectionId = "";

  function collectionOptions(selectedId = "") {
    const options = collections.map((collection) => {
      const label = `${collection.name || collection.collection_id} · ${collection.asset_count || collection.assets?.length || 0} 张`;
      return `<option value="${escapeHtml(collection.collection_id)}"${collection.collection_id === selectedId ? " selected" : ""}>${escapeHtml(label)}</option>`;
    }).join("");
    return `<option value="">不使用参考图集合</option>${options}`;
  }

  function syncCollectionSelects() {
    const selectedProjectCollection = els.projectReferenceCollection?.value || state.referenceCollectionId || "";
    if (els.assetCollectionPicker) {
      els.assetCollectionPicker.innerHTML = collectionOptions(activeCollectionId);
      els.assetCollectionPicker.value = activeCollectionId;
    }
    if (els.projectReferenceCollection) {
      els.projectReferenceCollection.innerHTML = collectionOptions(selectedProjectCollection);
      els.projectReferenceCollection.value = selectedProjectCollection;
    }
  }

  async function loadCollections() {
    const data = await api.fetchJson("/api/reference-collections").catch(() => null);
    collections = Array.isArray(data?.collections) ? data.collections : [];
    if (!activeCollectionId && collections[0]) activeCollectionId = collections[0].collection_id;
    if (activeCollectionId && !collections.some((item) => item.collection_id === activeCollectionId)) {
      activeCollectionId = collections[0]?.collection_id || "";
    }
    syncCollectionSelects();
    await loadActiveCollection();
  }

  function renderAssetGrid(collection) {
    if (!els.assetGrid) return;
    const assets = Array.isArray(collection?.assets) ? collection.assets : [];
    if (!collection) {
      els.assetGrid.innerHTML = '<div class="empty-state">还没有参考图集合。</div>';
      return;
    }
    if (!assets.length) {
      els.assetGrid.innerHTML = '<div class="empty-state">这个集合还没有图片，先上传一张并命名。</div>';
      return;
    }
    els.assetGrid.innerHTML = assets.map((asset) => `
      <article class="asset-card">
        <div class="asset-thumb">
          <img src="${escapeHtml(asset.image_url || "")}" alt="${escapeHtml(asset.name || "参考图")}" />
        </div>
        <div class="asset-body">
          <div class="asset-title-row">
            <strong>${escapeHtml(asset.name || "未命名")}</strong>
            <span>${escapeHtml(typeLabel(asset.type))}</span>
          </div>
          <p>${escapeHtml(asset.description || "未填写描述")}</p>
          <div class="asset-tags">${(asset.tags || []).map((tag) => `<em>${escapeHtml(tag)}</em>`).join("")}</div>
          <button class="text-action danger" type="button" data-delete-reference-asset="${escapeHtml(asset.id)}">删除</button>
        </div>
      </article>
    `).join("");
  }

  async function loadActiveCollection() {
    if (!activeCollectionId) {
      renderAssetGrid(null);
      if (els.assetCollectionMeta) els.assetCollectionMeta.textContent = "未选择集合";
      return null;
    }
    const data = await api.fetchJson(`/api/reference-collections/${encodeURIComponent(activeCollectionId)}`).catch(() => null);
    const collection = data?.collection || null;
    if (els.assetCollectionMeta) {
      els.assetCollectionMeta.textContent = collection
        ? `${collection.assets?.length || 0} 张参考图`
        : "读取失败";
    }
    renderAssetGrid(collection);
    return collection;
  }

  async function createCollection() {
    const name = els.assetCollectionName?.value.trim() || "";
    if (!name) {
      ui.setStatus("请填写集合名称", "error");
      return;
    }
    ui.setBusy(true);
    ui.setStatus("创建资产集合", "busy");
    try {
      const data = await api.postJson("/api/reference-collections", {
        name,
        description: els.assetCollectionDescription?.value.trim() || "",
      });
      activeCollectionId = data.collection?.collection_id || "";
      if (els.assetCollectionName) els.assetCollectionName.value = "";
      if (els.assetCollectionDescription) els.assetCollectionDescription.value = "";
      await loadCollections();
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function uploadAsset() {
    if (!activeCollectionId) {
      ui.setStatus("请先选择集合", "error");
      return;
    }
    const file = els.assetUploadFile?.files?.[0];
    const name = els.assetName?.value.trim() || "";
    if (!file || !name) {
      ui.setStatus("请填写图片名称并选择文件", "error");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    form.append("asset_type", els.assetType?.value || "character");
    form.append("description", els.assetDescription?.value.trim() || "");
    form.append("tags", els.assetTags?.value.trim() || "");
    ui.setBusy(true);
    ui.setStatus("上传参考图", "busy");
    try {
      await api.postForm(`/api/reference-collections/${encodeURIComponent(activeCollectionId)}/assets`, form);
      if (els.assetUploadFile) els.assetUploadFile.value = "";
      if (els.assetName) els.assetName.value = "";
      if (els.assetDescription) els.assetDescription.value = "";
      if (els.assetTags) els.assetTags.value = "";
      await loadCollections();
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function deleteAsset(assetId) {
    if (!activeCollectionId || !assetId) return;
    const confirmed = window.confirm("确定删除这张参考图？");
    if (!confirmed) return;
    ui.setBusy(true);
    ui.setStatus("删除参考图", "busy");
    try {
      await api.deleteJson(`/api/reference-collections/${encodeURIComponent(activeCollectionId)}/assets/${encodeURIComponent(assetId)}`);
      await loadCollections();
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  function applyProjectReferenceSettings(options = {}) {
    state.referenceCollectionId = els.projectReferenceCollection?.value || "";
    state.autoReferenceEnabled = Boolean(els.autoReferenceEnabled?.checked);
    const story = storyView.readOrNull?.();
    if (story && typeof story === "object") {
      story.reference_collection_id = state.referenceCollectionId;
      story.auto_reference_enabled = state.autoReferenceEnabled;
      storyView.write(story, { scheduleSave: false });
    }
    if (options.persist !== false) projectStore.scheduleSave();
  }

  function applyProjectState(projectStateData) {
    state.referenceCollectionId = projectStateData.reference_collection_id || projectStateData.story?.reference_collection_id || "";
    state.autoReferenceEnabled = Boolean(projectStateData.auto_reference_enabled ?? projectStateData.story?.auto_reference_enabled);
    if (els.projectReferenceCollection) {
      els.projectReferenceCollection.value = state.referenceCollectionId;
    }
    if (els.autoReferenceEnabled) {
      els.autoReferenceEnabled.checked = state.autoReferenceEnabled;
    }
    syncCollectionSelects();
  }

  function bindEvents() {
    els.createAssetCollection?.addEventListener("click", createCollection);
    els.uploadReferenceAsset?.addEventListener("click", uploadAsset);
    els.assetCollectionPicker?.addEventListener("change", () => {
      activeCollectionId = els.assetCollectionPicker.value || "";
      loadActiveCollection();
    });
    els.projectReferenceCollection?.addEventListener("change", () => applyProjectReferenceSettings());
    els.autoReferenceEnabled?.addEventListener("change", () => applyProjectReferenceSettings());
    document.addEventListener("click", (event) => {
      const deleteButton = event.target.closest("[data-delete-reference-asset]");
      if (deleteButton) deleteAsset(deleteButton.dataset.deleteReferenceAsset);
    });
  }

  function imageJobReferencePayload() {
    return {
      reference_collection_id: els.projectReferenceCollection?.value || "",
      auto_reference_enabled: Boolean(els.autoReferenceEnabled?.checked && els.projectReferenceCollection?.value),
      reference_provider: els.textProvider.value,
      reference_base_url: els.baseUrl.value.trim(),
      reference_model: els.model.value.trim(),
      reference_api_key: els.apiKey.value.trim(),
      reference_temperature: 0,
    };
  }

  return {
    bindEvents,
    loadCollections,
    applyProjectState,
    applyProjectReferenceSettings,
    imageJobReferencePayload,
  };
}
