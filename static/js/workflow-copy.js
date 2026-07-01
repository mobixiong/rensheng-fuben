export function createCopyWorkflow({ els, ui, api, settings, storyView, projectStore, setActiveTab, withCurrentImageSize }) {
  async function generateStory() {
    settings.persist();
    ui.setBusy(true);
    ui.setStatus("生成中", "busy");
    try {
      const data = withCurrentImageSize(await api.postJson("/api/text/generate", settings.storyPayload()));
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
      const story = withCurrentImageSize(await api.postJson("/api/text/copy-to-story", settings.copyToStoryPayload(els.copyOutput.value)));
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
      const story = withCurrentImageSize(await api.postJson("/api/text/copy-to-story", settings.copyToStoryPayload(text)));
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

  return {
    generateStory,
    generateCopy,
    buildStoryboardFromCopy,
  };
}
