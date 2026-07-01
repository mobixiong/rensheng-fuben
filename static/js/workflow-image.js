import { IMAGE_CONCURRENCY_LIMIT, IMAGE_RETRY_LIMIT, IMAGE_STATUS } from "./constants.js";
import {
  createImageProjectId,
  hasShotImage,
  mergeShotImageResult,
  normalizeShotIndexes,
  runWithConcurrency,
} from "./workflow-utils.js";

export function createImageWorkflow({ els, ui, api, settings, storyView, projectStore, state, withCurrentImageSize }) {
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

  function imageErrorMessage(err) {
    const message = String(err?.message || err || "图片生成失败");
    return err?.suggestion ? `${message}\n${err.suggestion}` : message;
  }

  async function markShotFailed(story, index, err) {
    if (!story.shots?.[index]) return;
    story.shots[index]._image_status = isPromptPolicyError(err) ? IMAGE_STATUS.policyError : IMAGE_STATUS.error;
    story.shots[index]._image_error = imageErrorMessage(err);
    story.shots[index]._image_error_code = err?.code || "";
    story.shots[index]._image_error_category = err?.category || "";
    storyView.write(story);
    await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
  }

  async function regenerateShotWithRetry(story, index, options = {}) {
    const initialStatus = options.initialStatus || IMAGE_STATUS.generating;
    let lastError = null;
    for (let attempt = 0; attempt <= IMAGE_RETRY_LIMIT; attempt += 1) {
      if (story.shots?.[index]) {
        story.shots[index]._image_status = attempt === 0 ? initialStatus : IMAGE_STATUS.retrying;
        story.shots[index]._image_attempt = attempt + 1;
        delete story.shots[index]._image_error;
        delete story.shots[index]._image_error_code;
        delete story.shots[index]._image_error_category;
        storyView.write(story);
        await projectStore.queueProgressSave({ applyState: false, refreshProjects: false });
      }
      try {
        return await api.postJson("/api/image/regenerate-shot", settings.imagePayload(story, { shot_index: index }));
      } catch (err) {
        lastError = err;
        if (isPromptPolicyError(err)) {
          await markShotFailed(story, index, err);
          break;
        }
        if (attempt < IMAGE_RETRY_LIMIT && story.shots?.[index]) {
          story.shots[index]._image_status = IMAGE_STATUS.retrying;
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
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
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
          _image_status: hasShotImage(shot) ? IMAGE_STATUS.done : IMAGE_STATUS.generating,
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
      state.imageGenerationActive = false;
      await projectStore.loadList().catch(() => null);
      ui.setBusy(false);
    }
  }

  async function redrawShot(index) {
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
      const data = await regenerateShotWithRetry(story, index, { initialStatus: IMAGE_STATUS.redrawing });
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
      state.imageGenerationActive = false;
      await projectStore.loadList().catch(() => null);
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
      let story = withCurrentImageSize(storyView.read());
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
          _image_status: redrawSet.has(index) ? IMAGE_STATUS.redrawing : shot._image_status,
        })),
      };
      storyView.write(story);

      let completed = 0;
      const results = await runWithConcurrency(redrawIndexes, IMAGE_CONCURRENCY_LIMIT, async (index) => {
        try {
          const data = await regenerateShotWithRetry(story, index, { initialStatus: IMAGE_STATUS.redrawing });
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
          await markShotFailed(story, index, err);
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

  return {
    generateImagesParallel,
    redrawShot,
    redrawSelectedShots,
  };
}
