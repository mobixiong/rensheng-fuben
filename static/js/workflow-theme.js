import { escapeHtml } from "./html.js";

export function createThemeWorkflow({ els, ui, api, settings, storyView, projectStore, setActiveTab }) {
  let themeIdeas = [];
  let selectedIdeaIndex = -1;

  function renderThemeIdeas() {
    if (!els.themeIdeaCandidates) return;
    if (!themeIdeas.length) {
      els.themeIdeaCandidates.hidden = true;
      els.themeIdeaCandidates.innerHTML = "";
      return;
    }
    els.themeIdeaCandidates.hidden = false;
    els.themeIdeaCandidates.innerHTML = themeIdeas.map((idea, index) => {
      const tags = Array.isArray(idea.tags) ? idea.tags : [];
      const selected = index === selectedIdeaIndex ? " selected" : "";
      return `
        <article class="theme-idea-card${selected}" data-theme-idea="${index}">
          <h3>${escapeHtml(idea.title || `候选方向 ${index + 1}`)}</h3>
          <p>${escapeHtml(idea.direction || "")}</p>
          ${tags.length ? `<div class="theme-idea-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
          ${idea.reason ? `<p>${escapeHtml(idea.reason)}</p>` : ""}
          <div class="theme-idea-actions">
            <button class="text-action" type="button" data-theme-idea-action="adopt" data-theme-idea-index="${index}">采用</button>
            <button class="text-action" type="button" data-theme-idea-action="refine" data-theme-idea-index="${index}">细化</button>
            <button class="text-action" type="button" data-theme-idea-action="reroll" data-theme-idea-index="${index}">重抽</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function clearThemeIdeas() {
    themeIdeas = [];
    selectedIdeaIndex = -1;
    renderThemeIdeas();
  }

  function applyThemeResult(data) {
    els.topic.value = data.topic || "";
    if (els.topicMirror) els.topicMirror.textContent = els.topic.value || "未填写主题";
    if (els.themeIntro) els.themeIntro.value = data.intro || "";
    if (els.themeIntroMirror) els.themeIntroMirror.textContent = els.themeIntro?.value.trim() || "未填写主题介绍";
    storyView.updatePromptMeta();
    settings.persist();
  }

  async function generateThemeIdeas(options = {}) {
    const { reroll = false, refineIndex = -1, rerollIndex = -1 } = options;
    settings.persist();
    ui.setBusy(true);
    ui.setStatus(refineIndex >= 0 ? "细化方向" : rerollIndex >= 0 ? "重抽方向" : reroll ? "换一批方向" : "AI 出方向", "busy");
    try {
      const baseBrief = els.themeBrief?.value.trim() || "";
      const currentIdea = themeIdeas[refineIndex >= 0 ? refineIndex : rerollIndex];
      const extra = {};
      if (refineIndex >= 0 && currentIdea) {
        extra.count = 3;
        extra.brief = currentIdea.direction || baseBrief;
        extra.instruction = `基于这条方向继续细化，保留核心矛盾，但给出更具体、更有画面感、更适合后续生成主题的版本：${currentIdea.direction || ""}`;
      } else if (rerollIndex >= 0 && currentIdea) {
        extra.count = 1;
        extra.brief = baseBrief || currentIdea.direction || "";
        extra.instruction = `只重抽一条，不要和这条重复：${currentIdea.direction || ""}`;
      } else if (reroll) {
        extra.instruction = "换一批候选方向，避免和上一批重复。";
      }
      const data = await api.postJson("/api/text/generate-theme-ideas", settings.themeIdeasPayload(extra));
      const ideas = Array.isArray(data.ideas) ? data.ideas : [];
      if (!ideas.length) throw new Error("AI 没有返回候选方向");
      if (rerollIndex >= 0 && currentIdea) {
        themeIdeas.splice(rerollIndex, 1, ideas[0]);
        selectedIdeaIndex = selectedIdeaIndex === rerollIndex ? -1 : selectedIdeaIndex;
      } else {
        themeIdeas = ideas;
        selectedIdeaIndex = -1;
      }
      renderThemeIdeas();
      els.result.textContent = JSON.stringify({ "候选方向": themeIdeas }, null, 2);
      ui.setStatus("就绪");
    } catch (err) {
      ui.setStatus("出错", "error");
      els.result.textContent = String(err.message || err);
    } finally {
      ui.setBusy(false);
    }
  }

  async function adoptThemeIdea(index) {
    const ideaIndex = Number(index);
    if (!Number.isInteger(ideaIndex) || !themeIdeas[ideaIndex]) return;
    selectedIdeaIndex = ideaIndex;
    if (els.themeBrief) els.themeBrief.value = themeIdeas[ideaIndex].direction || "";
    renderThemeIdeas();
    settings.persist();
    await projectStore.queueSave({ applyState: false, refreshProjects: false });
    ui.setStatus("已采用方向");
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
    generateThemeIdeas,
    adoptThemeIdea,
    clearThemeIdeas,
    generateTheme,
    reviseTheme,
  };
}
