import { IMAGE_CONCURRENCY_LIMIT, IMAGE_JOB_STATUS } from "./constants.js";
import {
  createImageProjectId,
  hasShotImage,
  normalizeShotIndexes,
} from "./workflow-utils.js";

const ACTIVE_JOB_ITEM_STATUSES = new Set(["queued", "running", "retrying"]);
const TERMINAL_JOB_STATUSES = new Set(["done", "failed", "cancelled"]);
const JOB_POLL_INTERVAL_MS = 1000;

export function createImageWorkflow({ els, ui, api, settings, storyView, projectStore, state, withCurrentImageSize }) {
  function imageJobs() {
    if (!(state.activeImageJobs instanceof Map)) state.activeImageJobs = new Map();
    return state.activeImageJobs;
  }

  function imageJobPollers() {
    if (!(state.imageJobPollers instanceof Map)) state.imageJobPollers = new Map();
    return state.imageJobPollers;
  }

  function currentImagePollingToken() {
    return Number(state.imageJobPollingToken || 0);
  }

  function nextImagePollingToken() {
    state.imageJobPollingToken = currentImagePollingToken() + 1;
    return state.imageJobPollingToken;
  }

  function imageJobPollerKey(job) {
    return `${job?.project_id || ""}:${job?.job_id || ""}`;
  }

  function isCurrentProjectJob(job) {
    if (!job?.project_id) return false;
    return !state.currentProjectId || state.currentProjectId === job.project_id;
  }

  function isCurrentPoller(job, pollingToken) {
    return currentImagePollingToken() === pollingToken && isCurrentProjectJob(job);
  }

  function syncImageGenerationActive() {
    state.imageGenerationActive = imageJobs().size > 0;
  }

  function clearImageJobPollers(options = {}) {
    const { render = true } = options;
    nextImagePollingToken();
    for (const timer of imageJobPollers().values()) {
      window.clearTimeout(timer);
    }
    imageJobPollers().clear();
    imageJobs().clear();
    syncImageGenerationActive();
    if (render) storyView.renderShotGrid();
  }

  function modeUiStatus(job, item) {
    if (item?.status === "retrying") return IMAGE_JOB_STATUS.retrying;
    const mode = String(job?.mode || "");
    if (mode.includes("redraw")) return IMAGE_JOB_STATUS.redrawing;
    return IMAGE_JOB_STATUS.generating;
  }

  function applyJobToActiveMap(job) {
    if (!job?.job_id || !isCurrentProjectJob(job)) return;
    for (const [index, value] of Array.from(imageJobs().entries())) {
      if (value?.jobId === job.job_id) imageJobs().delete(index);
    }
    for (const item of job.items || []) {
      if (!ACTIVE_JOB_ITEM_STATUSES.has(item.status)) continue;
      imageJobs().set(Number(item.shot_index), {
        jobId: job.job_id,
        projectId: job.project_id,
        status: modeUiStatus(job, item),
        attempt: item.attempt || 1,
        startedAt: job.created_at || Date.now(),
      });
    }
    syncImageGenerationActive();
    storyView.renderShotGrid();
  }

  function clearJobFromActiveMap(job, options = {}) {
    const { render = true } = options;
    if (!job?.job_id) return;
    let changed = false;
    for (const [index, value] of Array.from(imageJobs().entries())) {
      if (value?.jobId === job.job_id) {
        imageJobs().delete(index);
        changed = true;
      }
    }
    syncImageGenerationActive();
    if (changed && render) storyView.renderShotGrid();
  }

  function jobSummary(job) {
    if (!job) return {};
    return {
      "任务": job.job_id,
      "状态": job.status,
      "总数": job.total || 0,
      "完成": job.done || 0,
      "失败": job.failed || 0,
      "取消": job.cancelled || 0,
    };
  }

  async function refreshProjectStory() {
    const data = await api.fetchJson("/api/project/current");
    if (data?.state?.project_id) state.currentProjectId = data.state.project_id;
    if (data?.state?.story) {
      storyView.write(data.state.story, { scheduleSave: false });
    }
    return data;
  }

  async function pollImageJob(job) {
    if (!job?.job_id || !job?.project_id) return;
    const pollers = imageJobPollers();
    const pollerKey = imageJobPollerKey(job);
    if (pollers.has(pollerKey)) return;
    const pollingToken = currentImagePollingToken();

    const tick = async () => {
      if (!isCurrentPoller(job, pollingToken)) {
        clearJobFromActiveMap(job, { render: false });
        pollers.delete(pollerKey);
        return;
      }
      try {
        const data = await api.fetchJson(`/api/image/jobs/${encodeURIComponent(job.project_id)}/${encodeURIComponent(job.job_id)}`);
        const latest = data.job;
        if (!latest) throw new Error("图片任务不存在");
        if (!isCurrentPoller(latest, pollingToken)) {
          clearJobFromActiveMap(job, { render: false });
          pollers.delete(pollerKey);
          return;
        }
        applyJobToActiveMap(latest);
        await refreshProjectStory().catch(() => null);
        if (!isCurrentPoller(latest, pollingToken)) {
          clearJobFromActiveMap(latest, { render: false });
          pollers.delete(pollerKey);
          return;
        }
        els.result.textContent = JSON.stringify(jobSummary(latest), null, 2);
        if (TERMINAL_JOB_STATUSES.has(latest.status)) {
          clearJobFromActiveMap(latest);
          pollers.delete(pollerKey);
          await projectStore.loadList().catch(() => null);
          if (!isCurrentPoller(latest, pollingToken)) return;
          ui.setStatus(latest.status === "failed" ? "部分失败" : "就绪", latest.status === "failed" ? "error" : "");
          return;
        }
        const timer = window.setTimeout(tick, JOB_POLL_INTERVAL_MS);
        pollers.set(pollerKey, timer);
      } catch (err) {
        if (!isCurrentPoller(job, pollingToken)) {
          pollers.delete(pollerKey);
          return;
        }
        clearJobFromActiveMap(job);
        await refreshProjectStory().catch(() => null);
        if (!isCurrentPoller(job, pollingToken)) {
          pollers.delete(pollerKey);
          return;
        }
        pollers.delete(pollerKey);
        ui.setStatus("任务轮询失败，已刷新图片状态", "error");
        els.result.textContent = String(err.message || err);
      }
    };

    pollers.set(pollerKey, window.setTimeout(tick, 0));
  }

  function activeShotIndexes() {
    return new Set(Array.from(imageJobs().keys()).map(Number));
  }

  function assertNoActiveShots(indexes) {
    const active = activeShotIndexes();
    const blocked = indexes.filter((index) => active.has(index));
    if (blocked.length) {
      throw new Error(`镜头 ${blocked.map((index) => index + 1).join("、")} 正在生成或重抽中`);
    }
  }

  async function createBackendImageJob({ mode, shotIndexes = null, statusText = "创建图片任务" }) {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus(statusText, "busy");
    clearTimeout(state.saveTimer);
    try {
      await projectStore.ensureSaved({ applyState: false, refreshProjects: false });
      let story = withCurrentImageSize(storyView.read());
      const shots = story.shots || [];
      if (!Array.isArray(shots) || shots.length === 0) {
        throw new Error("分镜列表为空");
      }

      const projectId = state.currentProjectId || projectStore.mediaProjectId().replace(/^projects\//, "") || createImageProjectId();
      story = {
        ...story,
        project_id: projectId,
      };

      const normalizedIndexes = shotIndexes
        ? normalizeShotIndexes(shotIndexes, shots.length)
        : shots.map((shot, index) => hasShotImage(shot) ? -1 : index).filter((index) => index >= 0);
      if (!normalizedIndexes.length) {
        throw new Error(mode.includes("redraw") ? "请先选择要重抽的图片" : "没有需要生成的图片");
      }
      assertNoActiveShots(normalizedIndexes);

      const payload = settings.imagePayload(story, {
        project_id: projectId,
        mode,
        shot_indexes: normalizedIndexes,
        concurrency: IMAGE_CONCURRENCY_LIMIT,
        ...(state.referenceAssets?.imageJobReferencePayload?.() || {}),
      });
      const data = await api.postJson("/api/image/jobs", payload);
      const job = data.job;
      applyJobToActiveMap(job);
      els.result.textContent = JSON.stringify(jobSummary(job), null, 2);
      ui.setStatus("图片任务已提交", "busy");
      await pollImageJob(job);
      return job;
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
      throw err;
    } finally {
      ui.setBusy(false);
    }
  }

  async function generateImagesParallel() {
    await createBackendImageJob({
      mode: "generate_missing",
      shotIndexes: null,
      statusText: "提交批量生图",
    }).catch(() => null);
  }

  async function redrawShot(index) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
    await createBackendImageJob({
      mode: "redraw",
      shotIndexes: [shotIndex],
      statusText: "提交重抽任务",
    }).catch(() => null);
  }

  async function redrawSelectedShots(indexes) {
    await createBackendImageJob({
      mode: "batch_redraw",
      shotIndexes: indexes,
      statusText: "提交批量重抽",
    }).catch(() => null);
  }

  async function restoreActiveImageJobs() {
    clearImageJobPollers({ render: false });
    const projectId = state.currentProjectId;
    if (!projectId) {
      storyView.renderShotGrid();
      return;
    }
    const data = await api.fetchJson(`/api/image/jobs?project_id=${encodeURIComponent(projectId)}&active_only=true`).catch(() => null);
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    if (!jobs.length) {
      imageJobs().clear();
      syncImageGenerationActive();
      storyView.renderShotGrid();
      return;
    }
    for (const job of jobs) {
      applyJobToActiveMap(job);
      pollImageJob(job);
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


  async function setShotAsCover(index) {
    const shotIndex = Number(index);
    if (!Number.isInteger(shotIndex) || shotIndex < 0) return;
    ui.setStatus("设置封面", "busy");
    clearTimeout(state.saveTimer);
    try {
      storyView.setShotAsCover(shotIndex);
      await projectStore.queueSave({ applyState: false, refreshProjects: false });
      await state.projectSaveQueue.catch(() => null);
      await projectStore.loadList().catch(() => null);
      ui.setStatus("已设置封面");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      storyView.renderShotGrid();
    }
  }
  return {
    clearImageJobPollers,
    generateImagesParallel,
    redrawShot,
    redrawSelectedShots,
    restoreActiveImageJobs,
    improveShotImagePrompt,
    setShotAsCover,
  };
}
