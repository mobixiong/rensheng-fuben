export function createConnectionWorkflow({ els, ui, api, settings, storyView, projectStore }) {
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

  return {
    testTextConnection,
    testImageConnection,
    loadExample,
  };
}
