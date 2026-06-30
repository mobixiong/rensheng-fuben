import { IMAGE_CONCURRENCY_LIMIT, IMAGE_RETRY_LIMIT } from "./constants.js";

const INTRO_TEMPLATE_LABELS = {
  none: "无开头增强",
  life_copy_reveal: "人生副本揭幕模板",
  life_copy_fast_cut: "人生副本快切模板",
  clean: "干净淡入 + 暗角",
  soft: "柔和淡入",
  impact: "短视频冲击感",
};

const INTRO_TEMPLATE_PREVIEW_ITEMS = [
  "life_copy_fast_cut",
  "life_copy_reveal",
  "clean",
  "soft",
  "impact",
  "none",
].map((id) => ({
  id,
  video: `/static/assets/intro-previews/${id}.mp4`,
}));

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
  targetShot._image_version = Date.now();
  targetShot._image_status = "done";
  delete targetShot._image_error;
  if (sourceStory.project_id) targetStory.project_id = sourceStory.project_id;
  return targetStory;
}

function hasShotImage(shot) {
  return Boolean(shot?.image_url || shot?.image_path);
}

function normalizeShotIndexes(indexes, shotsLength) {
  const values = indexes instanceof Set ? Array.from(indexes) : Array.isArray(indexes) ? indexes : [indexes];
  return Array.from(new Set(
    values
      .map(Number)
      .filter((index) => Number.isInteger(index) && index >= 0 && index < shotsLength),
  )).sort((a, b) => a - b);
}

async function runWithConcurrency(items, limit, worker) {
  if (!items.length) return [];
  const results = new Array(items.length);
  const workerCount = Math.min(items.length, Math.max(1, Number(limit) || 1));
  let cursor = 0;

  async function runNext() {
    while (cursor < items.length) {
      const current = cursor;
      cursor += 1;
      try {
        results[current] = { status: "fulfilled", value: await worker(items[current], current) };
      } catch (reason) {
        results[current] = { status: "rejected", reason };
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, runNext));
  return results;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function clampProgress(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(1, numeric));
}

export function createWorkflow({ els, ui, api, settings, storyView, projectStore, state, setActiveTab }) {
  function openIntroPreviewModal() {
    if (!els.introPreviewModal) return;
    els.introPreviewModal.hidden = false;
  }

  function closeIntroPreviewModal() {
    if (!els.introPreviewModal) return;
    els.introPreviewModal.hidden = true;
  }

  function updateRenderProgress(job, options = {}) {
    if (!els.renderProgress) return;
    const currentProgress = Number.parseInt(els.renderProgressPercent?.textContent || "0", 10) / 100;
    const progress = clampProgress(job?.progress ?? currentProgress);
    const percent = Math.round(progress * 100);
    const label = job?.detail || job?.stage || "等待渲染";
    els.renderProgress.hidden = false;
    els.renderProgress.classList.toggle("error", options.error || job?.status === "error");
    if (els.renderProgressBar) els.renderProgressBar.style.width = `${percent}%`;
    if (els.renderProgressPercent) els.renderProgressPercent.textContent = `${percent}%`;
    if (els.renderProgressText) els.renderProgressText.textContent = label;
  }

  function renderVoiceConfig() {
    if (els.ttsProvider?.value === "minimax") {
      return {
        voice: els.voice?.value || "zh-CN-YunxiNeural",
        rate: els.rate?.value || "+12%",
        ttsPreset: "minimax",
        ttsProvider: "minimax",
        ttsBaseUrl: els.ttsBaseUrl?.value.trim() || "",
        ttsApiKey: els.ttsApiKey?.value.trim() || "",
        ttsGroupId: els.ttsGroupId?.value.trim() || "",
        ttsModel: els.ttsModel?.value.trim() || "speech-2.8-hd",
        ttsVoiceId: els.ttsVoiceId?.value.trim() || "male-qn-qingse",
        ttsSpeed: Number.parseFloat(els.ttsSpeed?.value || "1") || 1,
        ttsEmotion: els.ttsEmotion?.value || "",
        ttsLanguageBoost: els.ttsLanguageBoost?.value || "Chinese",
      };
    }
    const option = els.ttsPreset?.selectedOptions?.[0];
    if (option?.dataset?.voice && option?.dataset?.rate) {
      return {
        voice: option.dataset.voice,
        rate: option.dataset.rate,
        ttsPreset: els.ttsPreset.value,
        ttsProvider: "edge",
      };
    }
    return {
      voice: els.voice.value,
      rate: els.rate.value,
      ttsPreset: els.ttsPreset?.value || "custom",
      ttsProvider: "edge",
    };
  }

  async function loadBgmOptions() {
    if (!els.bgmSelect) return;
    const selected = els.bgmSelect.value || "none";
    const data = await api.fetchJson("/api/bgm");
    const items = Array.isArray(data.items) ? data.items : [];
    els.bgmSelect.replaceChildren();

    const noneOption = document.createElement("option");
    noneOption.value = "none";
    noneOption.textContent = "无 BGM";
    els.bgmSelect.appendChild(noneOption);

    for (const item of items) {
      const id = String(item.id || "").trim();
      if (!id) continue;
      const option = document.createElement("option");
      option.value = id;
      option.textContent = String(item.name || item.filename || id);
      els.bgmSelect.appendChild(option);
    }

    els.bgmSelect.value = Array.from(els.bgmSelect.options).some((option) => option.value === selected) ? selected : "none";
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

  async function testTextConnection() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("测试文案", "busy");
    ui.setTestResult(els.textConnectionResult, "测试中", "testing");
    try {
      const data = await api.postJson("/api/settings/test-text", settings.textConnectionPayload());
      ui.setTestResult(els.textConnectionResult, "连接成功", "ok");
      els.result.textContent = JSON.stringify({
        "文案连接": "通过",
        "服务": data.provider,
        "模型": data.model,
        "返回": data.sample,
      }, null, 2);
      ui.setStatus("连接正常");
    } catch (err) {
      ui.setTestResult(els.textConnectionResult, "连接失败", "error");
      ui.setStatus("连接失败", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function testImageConnection() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("测试图片", "busy");
    ui.setTestResult(els.imageConnectionResult, "测试中", "testing");
    try {
      const data = await api.postJson("/api/settings/test-image", settings.imageConnectionPayload());
      ui.setTestResult(els.imageConnectionResult, "连接成功", "ok");
      els.result.textContent = JSON.stringify({
        "图片连接": "通过",
        "服务": data.provider,
        "模型": data.model,
        "返回": data.returned,
      }, null, 2);
      ui.setStatus("连接正常");
    } catch (err) {
      ui.setTestResult(els.imageConnectionResult, "连接失败", "error");
      ui.setStatus("连接失败", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function loadExample() {
    ui.setStatus("加载中", "busy");
    storyView.write(await api.fetchJson("/api/example"));
    projectStore.scheduleSave();
    ui.setStatus("就绪");
  }

  async function generateStory() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("生成中", "busy");
    try {
      const data = await api.postJson("/api/text/generate", settings.storyPayload());
      storyView.write(data);
      els.result.textContent = JSON.stringify({ "分镜生成": "完成", "镜头数": data.shots?.length || 0 }, null, 2);
      await projectStore.saveNow();
      ui.setStatus("就绪");
      setActiveTab("image");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function generateCopy() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("写口播", "busy");
    try {
      const data = await api.postJson("/api/text/generate-copy", settings.textPayload());
      els.copyOutput.value = data.text || "";
      storyView.updatePromptMeta();
      ui.setStatus("拆分镜", "busy");
      const story = await api.postJson("/api/text/copy-to-story", settings.copyToStoryPayload(els.copyOutput.value));
      storyView.write(story);
      els.result.textContent = JSON.stringify({
        "口播生成": "完成",
        "分镜拆分": "完成",
        "主题": data.topic,
        "字数": els.copyOutput.value.length,
        "镜头数": story.shots?.length || 0,
      }, null, 2);
      await projectStore.saveNow();
      ui.setStatus("就绪");
      setActiveTab("image");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function buildStoryboardFromCopy() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("拆分镜", "busy");
    try {
      const text = els.copyOutput.value.trim();
      if (!text) throw new Error("请先生成或填写口播文案");
      const story = await api.postJson("/api/text/copy-to-story", settings.copyToStoryPayload(text));
      storyView.write(story);
      els.result.textContent = JSON.stringify({
        "分镜拆分": "完成",
        "镜头数": story.shots?.length || 0,
      }, null, 2);
      await projectStore.saveNow();
      ui.setStatus("就绪");
      setActiveTab("image");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function regenerateShotWithRetry(story, index) {
    let lastError = null;
    for (let attempt = 0; attempt <= IMAGE_RETRY_LIMIT; attempt += 1) {
      if (story.shots?.[index]) {
        story.shots[index]._image_status = attempt === 0 ? "generating" : "retrying";
        story.shots[index]._image_attempt = attempt + 1;
        delete story.shots[index]._image_error;
        storyView.write(story);
        await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
      }
      try {
        return await api.postJson("/api/image/regenerate-shot", settings.imagePayload(story, { shot_index: index }));
      } catch (err) {
        lastError = err;
        if (attempt < IMAGE_RETRY_LIMIT && story.shots?.[index]) {
          story.shots[index]._image_status = "retrying";
          story.shots[index]._image_error = String(err.message || err);
          storyView.write(story);
          await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
        }
      }
    }
    throw lastError;
  }

  async function generateImagesParallel() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("并行生图", "busy");
    state.imageGenerationActive = true;
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = storyView.read();
      const shots = story.shots || [];
      if (!Array.isArray(shots) || shots.length === 0) {
        throw new Error("分镜列表为空");
      }
      const pendingIndexes = shots
        .map((shot, index) => hasShotImage(shot) ? -1 : index)
        .filter((index) => index >= 0);
      story = {
        ...story,
        project_id: projectStore.mediaProjectId() || story.project_id || createImageProjectId(),
        shots: shots.map((shot) => ({
          ...shot,
          _image_status: hasShotImage(shot) ? "done" : "generating",
        })),
      };
      storyView.write(story);

      if (pendingIndexes.length === 0) {
        els.result.textContent = JSON.stringify({
          "图片生成": "无需生成",
          "已有图片": shots.length,
          "项目编号": story.project_id,
        }, null, 2);
        await projectStore.queueSave({ applyState: false, refreshProjects: false });
        ui.setStatus("就绪");
        return;
      }

      let completed = 0;
      const results = await runWithConcurrency(pendingIndexes, IMAGE_CONCURRENCY_LIMIT, async (index) => {
        try {
          const data = await regenerateShotWithRetry(story, index);
          story = mergeShotImageResult(story, data, index);
          completed += 1;
          storyView.write(story);
          els.result.textContent = JSON.stringify({
            "图片生成": "并行进行中",
            "已完成": completed,
            "待生成数": pendingIndexes.length,
            "总镜头数": shots.length,
            "最近完成镜头": index + 1,
            "项目编号": story.project_id,
          }, null, 2);
          ui.setStatus(`生图 ${completed}/${pendingIndexes.length}`, "busy");
          await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
          return data;
        } catch (err) {
          if (story.shots?.[index]) {
            story.shots[index]._image_status = "error";
            story.shots[index]._image_error = String(err.message || err);
            storyView.write(story);
            await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
          }
          throw err;
        }
      });
      const failed = results.filter((item) => item.status === "rejected");
      if (failed.length) {
        throw new Error(`并行生图完成 ${completed}/${pendingIndexes.length}，失败 ${failed.length} 张：${failed[0].reason?.message || failed[0].reason}`);
      }

      els.result.textContent = JSON.stringify({
        "图片生成": "完成",
        "项目编号": story.project_id,
        "本次生成": pendingIndexes.length,
        "镜头数": story.shots?.length || 0,
      }, null, 2);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
    } finally {
      await state.projectSaveQueue.catch(() => null);
      state.imageGenerationActive = false;
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function redrawShot(index) {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("重抽中", "busy");
    state.imageGenerationActive = true;
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = storyView.read();
      if (!story.project_id) {
        story = { ...story, project_id: projectStore.mediaProjectId() || createImageProjectId() };
        storyView.write(story);
      }
      const data = await regenerateShotWithRetry(story, index);
      story = mergeShotImageResult(story, data, index);
      storyView.write(story);
      els.result.textContent = JSON.stringify({
        "重抽": "完成",
        "镜头": index + 1,
        "项目编号": data.project_id,
      }, null, 2);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
    } finally {
      await state.projectSaveQueue.catch(() => null);
      state.imageGenerationActive = false;
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function redrawSelectedShots(indexes) {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("批量重抽", "busy");
    state.imageGenerationActive = true;
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = storyView.read();
      const shots = story.shots || [];
      if (!Array.isArray(shots) || shots.length === 0) {
        throw new Error("分镜列表为空");
      }
      const redrawIndexes = normalizeShotIndexes(indexes, shots.length);
      if (redrawIndexes.length === 0) {
        throw new Error("请先点击选择要重抽的图片");
      }
      const redrawSet = new Set(redrawIndexes);
      story = {
        ...story,
        project_id: story.project_id || projectStore.mediaProjectId() || createImageProjectId(),
        shots: shots.map((shot, index) => ({
          ...shot,
          _image_status: redrawSet.has(index) ? "generating" : shot._image_status,
        })),
      };
      storyView.write(story);

      let completed = 0;
      const results = await runWithConcurrency(redrawIndexes, IMAGE_CONCURRENCY_LIMIT, async (index) => {
        try {
          const data = await regenerateShotWithRetry(story, index);
          story = mergeShotImageResult(story, data, index);
          completed += 1;
          storyView.write(story);
          els.result.textContent = JSON.stringify({
            "批量重抽": "进行中",
            "已完成": completed,
            "总数": redrawIndexes.length,
            "最近完成镜头": index + 1,
            "项目编号": story.project_id,
          }, null, 2);
          ui.setStatus(`重抽 ${completed}/${redrawIndexes.length}`, "busy");
          await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
          return data;
        } catch (err) {
          if (story.shots?.[index]) {
            story.shots[index]._image_status = "error";
            story.shots[index]._image_error = String(err.message || err);
            storyView.write(story);
            await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
          }
          throw err;
        }
      });
      const failed = results.filter((item) => item.status === "rejected");
      if (failed.length) {
        throw new Error(`批量重抽完成 ${completed}/${redrawIndexes.length}，失败 ${failed.length} 张：${failed[0].reason?.message || failed[0].reason}`);
      }

      els.result.textContent = JSON.stringify({
        "批量重抽": "完成",
        "本次重抽": redrawIndexes.length,
        "项目编号": story.project_id,
      }, null, 2);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
    } finally {
      await state.projectSaveQueue.catch(() => null);
      state.imageGenerationActive = false;
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function renderVideo() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("提交渲染", "busy");
    updateRenderProgress({ progress: 0, stage: "提交渲染", detail: "正在提交渲染任务" });
    els.openVideo.hidden = true;
    els.preview.removeAttribute("src");
    try {
      await projectStore.ensureSaved();
      const voiceConfig = renderVoiceConfig();
      const payload = {
        story: storyView.read(),
        voice: voiceConfig.voice,
        rate: voiceConfig.rate,
        tts_preset: voiceConfig.ttsPreset,
        tts_provider: voiceConfig.ttsProvider,
        tts_base_url: voiceConfig.ttsBaseUrl || "",
        tts_api_key: voiceConfig.ttsApiKey || "",
        tts_group_id: voiceConfig.ttsGroupId || "",
        tts_model: voiceConfig.ttsModel || "",
        tts_voice_id: voiceConfig.ttsVoiceId || "",
        tts_speed: voiceConfig.ttsSpeed || 1,
        tts_emotion: voiceConfig.ttsEmotion || "",
        tts_language_boost: voiceConfig.ttsLanguageBoost || "",
        project_id: projectStore.mediaProjectId(),
        cleanup_intermediate: true,
        intro_template: els.introTemplate?.value || "none",
        bgm_id: els.bgmSelect?.value || "none",
      };
      const job = await api.postJson("/api/render/jobs", payload);
      updateRenderProgress(job);
      let data = null;
      for (;;) {
        const status = await api.fetchJson(`/api/render/jobs/${encodeURIComponent(job.job_id)}`);
        updateRenderProgress(status);
        els.result.textContent = JSON.stringify(status, null, 2);
        if (status.status === "complete") {
          data = status.result;
          break;
        }
        if (status.status === "error") {
          updateRenderProgress(status, { error: true });
          throw new Error(status.error || "渲染失败");
        }
        const percent = Math.round(clampProgress(status.progress) * 100);
        ui.setStatus(status.status === "running" ? `渲染 ${percent}%` : "排队中", "busy");
        await sleep(2000);
      }
      els.result.textContent = JSON.stringify(data, null, 2);
      els.preview.src = data.video;
      els.openVideo.href = data.video;
      els.openVideo.hidden = false;
      await projectStore.saveNow();
      updateRenderProgress({ progress: 1, stage: "渲染完成", detail: "成片已导出" });
      ui.setStatus("完成");
    } catch (err) {
      ui.setStatus("出错", "error");
      updateRenderProgress({ stage: "渲染失败", detail: String(err.message || err), status: "error" }, { error: true });
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  return {
    testTextConnection,
    testImageConnection,
    loadExample,
    generateStory,
    generateCopy,
    buildStoryboardFromCopy,
    generateImagesParallel,
    redrawShot,
    redrawSelectedShots,
    loadBgmOptions,
    previewIntroTemplates,
    closeIntroPreviewModal,
    renderVideo,
  };
}
