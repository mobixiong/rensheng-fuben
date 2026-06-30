import { IMAGE_CONCURRENCY_LIMIT, IMAGE_RETRY_LIMIT } from "./constants.js";

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

export function createWorkflow({ els, ui, api, settings, storyView, projectStore, state, setActiveTab }) {
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
        await projectStore.queueSave({ applyState: false, refreshProjects: false });
      }
      try {
        return await api.postJson("/api/image/regenerate-shot", settings.imagePayload(story, { shot_index: index }));
      } catch (err) {
        lastError = err;
        if (attempt < IMAGE_RETRY_LIMIT && story.shots?.[index]) {
          story.shots[index]._image_status = "retrying";
          story.shots[index]._image_error = String(err.message || err);
          storyView.write(story);
          await projectStore.queueSave({ applyState: false, refreshProjects: false });
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
          await projectStore.queueSave({ applyState: false, refreshProjects: false });
          return data;
        } catch (err) {
          if (story.shots?.[index]) {
            story.shots[index]._image_status = "error";
            story.shots[index]._image_error = String(err.message || err);
            storyView.write(story);
            await projectStore.queueSave({ applyState: false, refreshProjects: false });
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
          await projectStore.queueSave({ applyState: false, refreshProjects: false });
          return data;
        } catch (err) {
          if (story.shots?.[index]) {
            story.shots[index]._image_status = "error";
            story.shots[index]._image_error = String(err.message || err);
            storyView.write(story);
            await projectStore.queueSave({ applyState: false, refreshProjects: false });
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
    ui.setStatus("渲染中", "busy");
    els.openVideo.hidden = true;
    els.preview.removeAttribute("src");
    try {
      await projectStore.ensureSaved();
      const data = await api.postJson("/api/render", {
        story: storyView.read(),
        voice: els.voice.value,
        rate: els.rate.value,
        project_id: projectStore.mediaProjectId(),
      });
      els.result.textContent = JSON.stringify(data, null, 2);
      els.preview.src = data.video;
      els.openVideo.href = data.video;
      els.openVideo.hidden = false;
      await projectStore.saveNow();
      ui.setStatus("完成");
    } catch (err) {
      ui.setStatus("出错", "error");
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
    renderVideo,
  };
}
