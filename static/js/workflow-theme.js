export function createThemeWorkflow({ els, ui, api, settings, storyView, projectStore, setActiveTab }) {
  function applyThemeResult(data) {
    els.topic.value = data.topic || "";
    if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
    if (els.themeIntro) els.themeIntro.value = data.intro || "";
    if (els.themeIntroMirror) els.themeIntroMirror.textContent = els.themeIntro?.value.trim() || "未填写主题介绍";
    storyView.updatePromptMeta();
    settings.persist();
  }

  async function generateTheme(options = {}) {
    const { reroll = false } = options;
    settings.persist();
    if (!settings.themePayload().brief) {
      ui.setStatus("请先填写选题方向", "error");
      return;
    }
    ui.setBusy(true);
    ui.setStatus(reroll ? "重抽主题" : "生成主题", "busy");
    try {
      const payload = settings.themePayload();
      if (reroll && els.topic.value.trim()) {
        payload.brief = [
          payload.brief,
          "请重新抽一个不同的主题方案，避开当前已有主题。",
          `当前主题：${els.topic.value.trim()}`,
          `当前主题介绍：${els.themeIntro?.value.trim() || ""}`,
        ].join("\n");
      }
      const data = await api.postJson("/api/text/generate-theme", payload);
      applyThemeResult(data);
      await projectStore.saveNow();
      ui.setStatus("就绪");
      setActiveTab("theme");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function reviseTheme() {
    settings.persist();
    const payload = settings.themeRevisionPayload();
    if (!payload.topic || !payload.intro) {
      ui.setStatus("请先生成或填写主题", "error");
      return;
    }
    if (!payload.instruction) {
      ui.setStatus("请先填写修改意见", "error");
      return;
    }
    ui.setBusy(true);
    ui.setStatus("修改主题", "busy");
    try {
      const data = await api.postJson("/api/text/revise-theme", payload);
      applyThemeResult(data);
      await projectStore.saveNow();
      ui.setStatus("就绪");
      setActiveTab("theme");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  return {
    generateTheme,
    reviseTheme,
  };
}
