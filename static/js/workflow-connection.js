export function createConnectionWorkflow({ els, ui, api, settings, storyView, projectStore }) {
  function ttsProviderLabel(provider) {
    if (provider === "doubao") return "豆包语音 / 火山 TTS";
    if (provider === "minimax") return "MiniMax T2A HTTP";
    return "Edge TTS";
  }

  function previewVoiceLabel(payload) {
    return payload.tts_provider === "edge" ? payload.voice : payload.tts_voice_id;
  }

  function formatTtsPreviewError(err) {
    const raw = String(err?.message || err || "未知错误").trim();
    if (/missing api key/i.test(raw)) return { summary: "缺少 API Key", raw };
    if (/missing voice id|missing speaker|missing voice_id/i.test(raw)) return { summary: "缺少音色/说话人 ID", raw };
    if (/HTTP 401|unauthorized|invalid.*key|key.*invalid/i.test(raw)) return { summary: "API Key 无效或无权限", raw };
    if (/HTTP 403|forbidden|permission|not authorized/i.test(raw)) return { summary: "账号无权限或资源未开通", raw };
    if (/resource/i.test(raw) && /not|invalid|permission|denied/i.test(raw)) return { summary: "模型 / Resource ID 不可用", raw };
    if (/speaker|voice/i.test(raw) && /not|invalid|permission|denied/i.test(raw)) return { summary: "音色 ID 不可用", raw };
    return { summary: raw.length > 80 ? `${raw.slice(0, 80)}...` : raw, raw };
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

  async function previewTts() {
    const payload = settings.ttsPreviewPayload();
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("生成试听", "busy");
    ui.setTestResult(els.ttsPreviewResult, "生成中", "testing");
    if (els.ttsPreviewResult) els.ttsPreviewResult.removeAttribute("title");
    if (els.ttsPreviewAudio) {
      els.ttsPreviewAudio.hidden = true;
      els.ttsPreviewAudio.removeAttribute("src");
    }
    try {
      const data = await api.postJson("/api/tts/preview", payload);
      const audioUrl = `${data.audio}${String(data.audio || "").includes("?") ? "&" : "?"}v=${Date.now()}`;
      if (els.ttsPreviewAudio) {
        els.ttsPreviewAudio.src = audioUrl;
        els.ttsPreviewAudio.hidden = false;
        await els.ttsPreviewAudio.play().catch(() => null);
      }
      ui.setTestResult(els.ttsPreviewResult, "试听已生成", "ok");
      ui.setStatus("试听完成");
      els.result.textContent = JSON.stringify({
        "配音试听": "已生成",
        "服务": ttsProviderLabel(data.provider || payload.tts_provider),
        "模型 / Resource ID": payload.tts_model || "Edge 默认",
        "音色/说话人 ID": previewVoiceLabel(payload) || "Edge 语音角色",
        "音频": data.audio,
      }, null, 2);
    } catch (err) {
      const error = formatTtsPreviewError(err);
      ui.setTestResult(els.ttsPreviewResult, `试听失败：${error.summary}`, "error");
      if (els.ttsPreviewResult) els.ttsPreviewResult.title = error.raw;
      ui.setStatus("试听失败", "error");
      els.result.textContent = JSON.stringify({
        "配音试听": "失败",
        "服务": ttsProviderLabel(payload.tts_provider),
        "模型 / Resource ID": payload.tts_model || "Edge 默认",
        "音色/说话人 ID": previewVoiceLabel(payload) || "Edge 语音角色",
        "原因": error.summary,
        "原始错误": error.raw,
      }, null, 2);
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

  return {
    testTextConnection,
    testImageConnection,
    previewTts,
    loadExample,
  };
}
