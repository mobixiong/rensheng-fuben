import { escapeHtml } from "./html.js";
import { clampProgress, sleep } from "./workflow-utils.js";

const TERMINAL_STATUSES = new Set(["complete", "failed", "cancelled"]);
const NEXT_PIPELINE_DELAY_MS = 1200;

export function createAutoPipelineWorkflow({ els, ui, api, settings, projectStore, state, setActiveTab }) {
  function statusLabel(status) {
    if (status === "complete") return "已完成";
    if (status === "failed") return "失败";
    if (status === "cancelled") return "已停止";
    if (status === "running") return "运行中";
    if (status === "waiting_child_job") return "等待子任务";
    if (status === "queued") return "排队中";
    return "未开始";
  }

  function stepLabel(status) {
    if (status === "done") return "已完成";
    if (status === "skipped") return "已跳过";
    if (status === "running") return "进行中";
    if (status === "waiting") return "等待中";
    if (status === "failed") return "失败";
    if (status === "cancelled") return "已停止";
    return "等待中";
  }

  function cacheBust(url) {
    if (!url) return "";
    return `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}`;
  }

  function setLoopActive(active) {
    state.autoPipelineContinuous = Boolean(active);
    const startButton = document.getElementById("startAutoPipeline");
    if (startButton) {
      startButton.textContent = active ? "流水线运行中" : "开始流水线";
    }
  }

  function updateAutoPipelineView(job) {
    if (!els.autoPipelineStatus) return;
    const progress = clampProgress(job?.progress || 0);
    const percent = Math.round(progress * 100);
    els.autoPipelineStatus.textContent = statusLabel(job?.status);
    els.autoPipelineStatus.className = `state-badge ${job?.status === "failed" ? "error" : job?.status === "complete" ? "done" : job?.status === "cancelled" ? "pending" : "generating"}`;
    if (els.autoPipelineCurrent) els.autoPipelineCurrent.textContent = job?.detail || "等待开始";
    if (els.autoPipelinePercent) els.autoPipelinePercent.textContent = `${percent}%`;
    if (els.autoPipelineProgressBar) els.autoPipelineProgressBar.style.width = `${percent}%`;
    if (els.autoPipelineSteps) {
      const steps = Array.isArray(job?.steps) ? job.steps : [];
      els.autoPipelineSteps.innerHTML = steps.map((step) => `
        <div class="auto-step-item ${escapeHtml(step.status || "pending")}">
          <span>${escapeHtml(step.name || step.key || "")}</span>
          <strong>${escapeHtml(stepLabel(step.status))}</strong>
          ${step.detail ? `<em>${escapeHtml(step.detail)}</em>` : ""}
          ${step.error ? `<em class="error">${escapeHtml(step.error)}</em>` : ""}
        </div>
      `).join("");
    }
    if (els.autoPipelineResult) {
      els.autoPipelineResult.textContent = JSON.stringify({
        job_id: job?.job_id || "",
        project_id: job?.project_id || "",
        status: job?.status || "",
        current_step: job?.current_step || "",
        result: job?.result || {},
        error: job?.error || "",
      }, null, 2);
    }
  }

  function applyCompletedResult(job) {
    const videoUrl = job?.result?.video_url || "";
    if (videoUrl && els.preview && els.openVideo) {
      els.preview.src = cacheBust(videoUrl);
      els.openVideo.href = videoUrl;
      els.openVideo.hidden = false;
    }
    if (job?.project_id) {
      state.currentProjectId = job.project_id;
      projectStore.loadState(job.project_id).catch(() => null);
      projectStore.loadList().catch(() => null);
    }
    return videoUrl;
  }

  async function requestVideoFullscreen(video) {
    const target = video?.closest?.(".preview-panel") || video;
    if (!target || document.fullscreenElement) return true;
    const request = target.requestFullscreen
      || target.webkitRequestFullscreen
      || target.msRequestFullscreen;
    if (!request) return false;
    try {
      await request.call(target);
      return true;
    } catch {
      return false;
    }
  }

  async function exitVideoFullscreen() {
    if (!document.fullscreenElement) return;
    const exit = document.exitFullscreen
      || document.webkitExitFullscreen
      || document.msExitFullscreen;
    if (!exit) return;
    try {
      await exit.call(document);
    } catch {
      // 全屏退出失败不影响继续启动下一个项目。
    }
  }

  function waitForVideoEnd(video, token) {
    return new Promise((resolve) => {
      const finish = () => {
        cleanup();
        resolve();
      };
      const cleanup = () => {
        video.removeEventListener("ended", finish);
        video.removeEventListener("error", finish);
        window.clearInterval(cancelTimer);
      };
      const cancelTimer = window.setInterval(() => {
        if (!state.autoPipelineContinuous || state.autoPipelinePlaybackToken !== token) finish();
      }, 500);
      video.addEventListener("ended", finish, { once: true });
      video.addEventListener("error", finish, { once: true });
    });
  }

  async function playCompletedVideo(job) {
    const videoUrl = job?.result?.video_url || "";
    if (!videoUrl || !els.preview) {
      await sleep(NEXT_PIPELINE_DELAY_MS);
      return;
    }
    const token = (state.autoPipelinePlaybackToken || 0) + 1;
    state.autoPipelinePlaybackToken = token;
    setActiveTab("video");
    const video = els.preview;
    video.src = cacheBust(videoUrl);
    video.controls = true;
    video.muted = false;
    video.currentTime = 0;
    video.load();

    await requestVideoFullscreen(video);
    try {
      await video.play();
      ui.setStatus("成片播放中，播放结束后自动进入下一个项目", "busy");
      await waitForVideoEnd(video, token);
    } catch {
      try {
        video.muted = true;
        await video.play();
        ui.setStatus("浏览器限制声音自动播放，已静音播放；结束后自动进入下一个项目", "busy");
        await waitForVideoEnd(video, token);
      } catch {
        ui.setStatus("浏览器拦截了自动播放，短暂停留后进入下一个项目", "error");
        await sleep(3000);
      }
    } finally {
      if (state.autoPipelinePlaybackToken === token) {
        video.pause();
        video.muted = false;
        await exitVideoFullscreen();
      }
    }
  }

  async function pollAutoPipeline(job) {
    if (!job?.job_id || !job?.project_id) return null;
    state.activeAutoPipelineJob = { jobId: job.job_id, projectId: job.project_id };
    for (;;) {
      const data = await api.fetchJson(`/api/auto-pipeline/jobs/${encodeURIComponent(job.project_id)}/${encodeURIComponent(job.job_id)}`);
      const latest = data.job;
      updateAutoPipelineView(latest);
      if (TERMINAL_STATUSES.has(latest.status)) {
        state.activeAutoPipelineJob = null;
        if (latest.status === "complete") {
          ui.setStatus("自动流水线完成");
          applyCompletedResult(latest);
        } else {
          ui.setStatus(latest.status === "failed" ? "自动流水线失败" : "自动流水线已停止", latest.status === "failed" ? "error" : "");
        }
        return latest;
      }
      ui.setStatus("自动流水线运行中", "busy");
      await sleep(2000);
    }
  }

  async function createAndPollAutoPipeline() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("创建自动流水线", "busy");
    const data = await api.postJson("/api/auto-pipeline/jobs", settings.autoPipelinePayload());
    updateAutoPipelineView(data.job);
    setActiveTab("auto");
    ui.setBusy(false);
    return pollAutoPipeline(data.job);
  }

  async function startAutoPipeline() {
    if (state.autoPipelineLoopRunning) return;
    state.autoPipelineLoopRunning = true;
    setLoopActive(true);
    try {
      while (state.autoPipelineContinuous) {
        const completedJob = await createAndPollAutoPipeline();
        if (!state.autoPipelineContinuous || completedJob?.status !== "complete") break;
        applyCompletedResult(completedJob);
        await playCompletedVideo(completedJob);
        if (state.autoPipelineContinuous) {
          ui.setStatus("准备启动下一个自动项目", "busy");
          await sleep(NEXT_PIPELINE_DELAY_MS);
        }
      }
    } catch (err) {
      ui.setBusy(false);
      ui.setStatus("出错", "error");
      if (els.autoPipelineResult) els.autoPipelineResult.textContent = String(err.message || err);
    } finally {
      state.autoPipelineLoopRunning = false;
      setLoopActive(false);
      ui.setBusy(false);
    }
  }

  async function cancelAutoPipeline() {
    setLoopActive(false);
    state.autoPipelinePlaybackToken = (state.autoPipelinePlaybackToken || 0) + 1;
    if (els.preview) els.preview.pause();
    await exitVideoFullscreen();
    const active = state.activeAutoPipelineJob;
    if (!active?.jobId || !active?.projectId) {
      ui.setStatus("自动流水线已停止");
      return;
    }
    ui.setStatus("停止自动流水线", "busy");
    try {
      const data = await api.postJson(`/api/auto-pipeline/jobs/${encodeURIComponent(active.projectId)}/${encodeURIComponent(active.jobId)}/cancel`, {});
      updateAutoPipelineView(data.job);
      state.activeAutoPipelineJob = null;
      ui.setStatus("自动流水线已停止");
    } catch (err) {
      ui.setStatus("出错", "error");
      if (els.autoPipelineResult) els.autoPipelineResult.textContent = String(err.message || err);
    }
  }

  async function restoreActiveAutoPipelineJobs() {
    const projectId = state.currentProjectId;
    if (!projectId) return;
    const data = await api.fetchJson(`/api/auto-pipeline/jobs?project_id=${encodeURIComponent(projectId)}&active_only=true`).catch(() => null);
    const job = Array.isArray(data?.jobs) ? data.jobs[0] : null;
    if (!job) return;
    updateAutoPipelineView(job);
    setActiveTab("auto");
    pollAutoPipeline(job).catch((err) => {
      ui.setStatus("自动流水线轮询失败", "error");
      if (els.autoPipelineResult) els.autoPipelineResult.textContent = String(err.message || err);
    });
  }

  return {
    startAutoPipeline,
    cancelAutoPipeline,
    restoreActiveAutoPipelineJobs,
    updateAutoPipelineView,
  };
}
