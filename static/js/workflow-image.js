import { IMAGE_CONCURRENCY_LIMIT, IMAGE_RETRY_LIMIT, IMAGE_JOB_STATUS, IMAGE_STATUS } from "./constants.js";
import {
  clearImageError,
  clearImageJob,
  currentImageJobStatus,
  setImageFinalStatus,
  setImageJob,
} from "./image-state.js";
import {
  createImageProjectId,
  hasShotImage,
  mergeShotImageResult,
  normalizeShotIndexes,
  runWithConcurrency,
} from "./workflow-utils.js";

export function createImageWorkflow({ els, ui, api, settings, storyView, projectStore, state, withCurrentImageSize }) {
  function imageJobs() {
    if (!(state.activeImageJobs instanceof Map)) state.activeImageJobs = new Map();
    return state.activeImageJobs;
  }

  function setActiveImageJob(index, status) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
    imageJobs().set(shotIndex, { status, startedAt: Date.now() });
  }

  function clearActiveImageJob(index) {
    imageJobs().delete(Number(index));
  }

  function clearActiveImageJobs(indexes = null) {
    if (!indexes) {
      imageJobs().clear();
      return;
    }
    for (const index of indexes) clearActiveImageJob(index);
  }

  function syncImageGenerationActive() {
    state.imageGenerationActive = imageJobs().size > 0;
  }

  function activeImageIndexes(extraIndexes = []) {
    const indexes = Array.from(imageJobs().keys());
    for (const index of extraIndexes) {
      const shotIndex = Number(index);
      if (Number.isInteger(shotIndex) && shotIndex >= 0) indexes.push(shotIndex);
    }
    return new Set(indexes);
  }

  function clearImageRuntimeFields(shot) {
    clearImageJob(shot);
    clearImageError(shot);
  }

  function normalizeIdleImageStatuses(story, activeIndexes = []) {
    const activeSet = activeIndexes instanceof Set ? activeIndexes : new Set(activeIndexes.map(Number));
    if (!Array.isArray(story?.shots)) return story;
    story.shots = story.shots.map((shot, index) => {
      if (!shot || activeSet.has(index)) return shot;
      if (!currentImageJobStatus(shot)) return shot;
      const nextShot = {
        ...shot,
      };
      setImageFinalStatus(nextShot, hasShotImage(nextShot) ? IMAGE_STATUS.done : IMAGE_STATUS.pending);
      clearImageRuntimeFields(nextShot);
      return nextShot;
    });
    return story;
  }

  function isPromptPolicyError(err) {
    const text = `${err?.message || ""} ${err?.code || ""} ${err?.category || ""}`.toLowerCase();
    return err?.category === "prompt_policy"
      || text.includes("content_policy_violation")
      || text.includes("policy_violation")
      || text.includes("content policy")
      || text.includes("moderation")
      || text.includes("提示词被内容安全策略拦截")
      || text.includes("不合规")
      || text.includes("防护限制")
      || text.includes("敏感");
  }

  function isNonRetryableImageError(err) {
    const text = `${err?.message || ""} ${err?.code || ""} ${err?.category || ""}`.toLowerCase();
    return err?.status === 429
      || err?.category === "quota"
      || text.includes("quota")
      || text.includes("rate limit")
      || text.includes("too many requests")
      || text.includes("no available image quota")
      || text.includes("额度不足")
      || text.includes("限流");
  }

  function imageErrorMessage(err) {
    const message = String(err?.message || err || "图片生成失败");
    return err?.suggestion ? `${message}\n${err.suggestion}` : message;
  }

  async function markShotFailed(story, index, err) {
    if (!story.shots?.[index]) return;
    clearActiveImageJob(index);
    clearImageJob(story.shots[index]);
    setImageFinalStatus(story.shots[index], isPromptPolicyError(err) ? IMAGE_STATUS.policyError : IMAGE_STATUS.error);
    story.shots[index]._image_error = imageErrorMessage(err);
    story.shots[index]._image_error_code = err?.code || "";
    story.shots[index]._image_error_category = err?.category || "";
    storyView.write(story);
    await projectStore.queueSave({ applyState: false, refreshProjects: false });
  }

  async function regenerateShotWithRetry(story, index, options = {}) {
    const initialStatus = options.initialStatus || IMAGE_JOB_STATUS.generating;
    let lastError = null;
    for (let attempt = 0; attempt <= IMAGE_RETRY_LIMIT; attempt += 1) {
      if (story.shots?.[index]) {
        const jobStatus = attempt === 0 ? initialStatus : IMAGE_JOB_STATUS.retrying;
        setActiveImageJob(index, jobStatus);
        setImageJob(story.shots[index], jobStatus, { attempt: attempt + 1 });
        setImageFinalStatus(story.shots[index], hasShotImage(story.shots[index]) ? IMAGE_STATUS.done : IMAGE_STATUS.pending);
        clearImageError(story.shots[index]);
        storyView.write(story);
        await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
      }
      try {
        return await api.postJson("/api/image/regenerate-shot", settings.imagePayload(story, { shot_index: index }));
      } catch (err) {
        lastError = err;
        if (isPromptPolicyError(err) || isNonRetryableImageError(err)) {
          await markShotFailed(story, index, err);
          break;
        }
        if (attempt < IMAGE_RETRY_LIMIT && story.shots?.[index]) {
          setActiveImageJob(index, IMAGE_JOB_STATUS.retrying);
          setImageJob(story.shots[index], IMAGE_JOB_STATUS.retrying, { attempt: attempt + 2 });
          story.shots[index]._image_error = imageErrorMessage(err);
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
    let pendingIndexes = [];
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
      const shots = story.shots || [];
      if (!Array.isArray(shots) || shots.length === 0) {
        throw new Error("分镜列表为空");
      }
      pendingIndexes = shots
        .map((shot, index) => hasShotImage(shot) ? -1 : index)
        .filter((index) => index >= 0);
      pendingIndexes.forEach((index) => setActiveImageJob(index, IMAGE_JOB_STATUS.generating));
      story = {
        ...story,
        project_id: projectStore.mediaProjectId() || story.project_id || createImageProjectId(),
        shots: shots.map((shot) => {
          const nextShot = { ...shot };
          setImageFinalStatus(nextShot, hasShotImage(nextShot) ? IMAGE_STATUS.done : IMAGE_STATUS.pending);
          if (!hasShotImage(nextShot)) {
            setImageJob(nextShot, IMAGE_JOB_STATUS.generating);
            clearImageError(nextShot);
          }
          return nextShot;
        }),
      };
      normalizeIdleImageStatuses(story, activeImageIndexes(pendingIndexes));
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
          clearActiveImageJob(index);
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
          await markShotFailed(story, index, err);
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
      clearActiveImageJobs(pendingIndexes);
      syncImageGenerationActive();
      storyView.renderShotGrid();
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function redrawShot(index) {
    const shotIndex = Number(index);
    if (imageJobs().has(shotIndex)) return;
    settings.persist();
    ui.setStatus("重抽中", "busy");
    state.imageGenerationActive = true;
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
      if (!story.project_id) {
        story = { ...story, project_id: projectStore.mediaProjectId() || createImageProjectId() };
        storyView.write(story);
      }
      normalizeIdleImageStatuses(story, activeImageIndexes([shotIndex]));
      if (story.shots?.[index]) {
        const now = Date.now();
        setActiveImageJob(index, IMAGE_JOB_STATUS.redrawing);
        setImageJob(story.shots[index], IMAGE_JOB_STATUS.redrawing, { attempt: 1, startedAt: now });
        setImageFinalStatus(story.shots[index], hasShotImage(story.shots[index]) ? IMAGE_STATUS.done : IMAGE_STATUS.pending);
        clearImageError(story.shots[index]);
        storyView.write(story);
        await projectStore.queueSave({ applyState: false, refreshProjects: false });
      }
      const data = await regenerateShotWithRetry(story, index, { initialStatus: IMAGE_JOB_STATUS.redrawing });
      story = mergeShotImageResult(story, data, index);
      clearActiveImageJob(index);
      storyView.write(story);
      els.result.textContent = JSON.stringify({
        "重抽": "完成",
        "镜头": index + 1,
        "项目编号": data.project_id,
      }, null, 2);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("就绪");
    } catch (err) {
      let story = null;
      try {
        story = storyView.read();
      } catch {
        story = null;
      }
      if (story?.shots?.[index]) {
        await markShotFailed(story, index, err);
      }
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
    } finally {
      await state.projectSaveQueue.catch(() => null);
      clearActiveImageJob(shotIndex);
      syncImageGenerationActive();
      storyView.renderShotGrid();
      await projectStore.loadList().catch(() => null);
    }
  }

  async function redrawSelectedShots(indexes) {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("批量重抽", "busy");
    state.imageGenerationActive = true;
    clearTimeout(state.saveTimer);
    let availableRedrawIndexes = [];
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
      const shots = story.shots || [];
      if (!Array.isArray(shots) || shots.length === 0) {
        throw new Error("分镜列表为空");
      }
      const redrawIndexes = normalizeShotIndexes(indexes, shots.length);
      availableRedrawIndexes = redrawIndexes.filter((index) => !imageJobs().has(index));
      if (redrawIndexes.length === 0) {
        throw new Error("请先点击选择要重抽的图片");
      }
      if (availableRedrawIndexes.length === 0) {
        throw new Error("选中的图片正在生成或重抽中");
      }
      const redrawSet = new Set(availableRedrawIndexes);
      availableRedrawIndexes.forEach((index) => setActiveImageJob(index, IMAGE_JOB_STATUS.redrawing));
      normalizeIdleImageStatuses(story, activeImageIndexes(availableRedrawIndexes));
      const normalizedShots = story.shots || shots;
      story = {
        ...story,
        project_id: story.project_id || projectStore.mediaProjectId() || createImageProjectId(),
        shots: normalizedShots.map((shot, index) => {
          const nextShot = { ...shot };
          if (redrawSet.has(index)) {
            setImageJob(nextShot, IMAGE_JOB_STATUS.redrawing, { attempt: 1 });
            setImageFinalStatus(nextShot, hasShotImage(nextShot) ? IMAGE_STATUS.done : IMAGE_STATUS.pending);
            clearImageError(nextShot);
          }
          return nextShot;
        }),
      };
      storyView.write(story);

      let completed = 0;
      const results = await runWithConcurrency(availableRedrawIndexes, IMAGE_CONCURRENCY_LIMIT, async (index) => {
        try {
          const data = await regenerateShotWithRetry(story, index, { initialStatus: IMAGE_JOB_STATUS.redrawing });
          story = mergeShotImageResult(story, data, index);
          clearActiveImageJob(index);
          completed += 1;
          storyView.write(story);
          els.result.textContent = JSON.stringify({
            "批量重抽": "进行中",
            "已完成": completed,
            "总数": availableRedrawIndexes.length,
            "最近完成镜头": index + 1,
            "项目编号": story.project_id,
          }, null, 2);
          ui.setStatus(`重抽 ${completed}/${availableRedrawIndexes.length}`, "busy");
          await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
          return data;
        } catch (err) {
          await markShotFailed(story, index, err);
          throw err;
        }
      });
      const failed = results.filter((item) => item.status === "rejected");
      if (failed.length) {
        throw new Error(`批量重抽完成 ${completed}/${availableRedrawIndexes.length}，失败 ${failed.length} 张：${failed[0].reason?.message || failed[0].reason}`);
      }

      els.result.textContent = JSON.stringify({
        "批量重抽": "完成",
        "本次重抽": availableRedrawIndexes.length,
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
      clearActiveImageJobs(availableRedrawIndexes);
      syncImageGenerationActive();
      storyView.renderShotGrid();
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function improveShotImagePrompt(index) {
    settings.persist();
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
    storyView.setShotImagePromptStatus(shotIndex, "optimizing", "AI 正在根据口播和画面描述优化图片提示词");
    await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
    ui.setStatus("优化提示词", "busy");
    try {
      const story = storyView.read();
      const data = await api.postJson("/api/text/improve-image-prompt", settings.improveImagePromptPayload(story, shotIndex));
      const nextPrompt = String(data.image_prompt || "").trim();
      if (!nextPrompt) throw new Error("AI 没有返回图片提示词");
      storyView.updateShotImagePrompt(shotIndex, nextPrompt, { status: "optimized", message: "已用 AI 重写图片提示词" });
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      els.result.textContent = JSON.stringify({
        "图片提示词": "已优化",
        "镜头": shotIndex + 1,
        "提示词": nextPrompt,
      }, null, 2);
      ui.setStatus("就绪");
    } catch (err) {
      storyView.setShotImagePromptStatus(shotIndex, "error", String(err.message || err));
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    }
  }

  async function generateCoverImage() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("生成封面", "busy");
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
      if (!story.project_id) {
        story = { ...story, project_id: projectStore.mediaProjectId() || createImageProjectId() };
      }
      story.cover = {
        ...(story.cover || {}),
        title: els.topic.value.trim() || story.title || "",
        image_prompt: els.coverPrompt?.value.trim() || story.cover?.image_prompt || "",
        image_size: els.imageSize?.value || story.image_size || "",
        _cover_status: "generating",
      };
      delete story.cover._cover_error;
      storyView.write(story);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });

      const data = await api.postJson("/api/image/generate-cover", settings.imagePayload(story, {
        topic: els.topic.value.trim() || story.title || "",
        cover: story.cover,
      }));
      storyView.write(data);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      els.result.textContent = JSON.stringify({
        "封面": "已生成",
        "项目编号": data.project_id,
        "封面地址": data.cover?.image_url || "",
      }, null, 2);
      ui.setStatus("就绪");
    } catch (err) {
      storyView.setCoverStatus("error", String(err.message || err));
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      await state.projectSaveQueue.catch(() => null);
      storyView.renderCoverPanel();
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function setShotAsCover(index) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
    ui.setStatus("设置封面", "busy");
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      storyView.setShotAsCover(shotIndex);
      let story = withCurrentImageSize(storyView.read());
      story.cover = {
        ...(story.cover || {}),
        title: els.topic.value.trim() || story.title || "",
        _cover_status: "generating",
      };
      storyView.write(story);
      const data = await api.postJson("/api/image/apply-cover", {
        story,
        cover: story.cover,
        topic: els.topic.value.trim() || story.title || "",
        size: els.imageSize?.value || story.image_size || "9:16",
      });
      storyView.write(data);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("已设置封面");
    } catch (err) {
      storyView.setCoverStatus("error", String(err.message || err));
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      await state.projectSaveQueue.catch(() => null);
      storyView.renderShotGrid();
      storyView.renderCoverPanel();
    }
  }

  return {
    generateImagesParallel,
    redrawShot,
    redrawSelectedShots,
    improveShotImagePrompt,
    generateCoverImage,
    setShotAsCover,
  };
}
