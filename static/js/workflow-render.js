import { clampProgress, introImageSecondsValue, sleep } from "./workflow-utils.js";

export function createRenderWorkflow({ els, ui, api, settings, storyView, projectStore }) {
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

  function withCacheBust(url) {
    const value = String(url || "");
    if (!value) return value;
    return `${value}${value.includes("?") ? "&" : "?"}v=${Date.now()}`;
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
        intro_image_seconds: introImageSecondsValue(els),
        image_size: els.imageSize?.value || "9:16",
        bgm_id: els.bgmSelect?.value || "none",
        intro_sfx_id: els.introSfxSelect?.value || "default",
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
      els.preview.src = withCacheBust(data.video);
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
    renderVideo,
  };
}
