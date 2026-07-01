import {
  COPY_PROMPT_PRESETS,
  COPY_PROMPT_VERSION,
  COPY_TO_STORY_PROMPT_VERSION,
  DEFAULT_COPY_PROMPT_PRESET,
  DEFAULT_IMAGE_SIZE,
  DEFAULT_INTRO_TEMPLATE,
  GEMINI_WEB2API_DEFAULT_BASE_URL,
  GEMINI_WEB2API_DEFAULT_MODEL,
  IMAGE_SIZES,
  IMPROVE_IMAGE_PROMPT_VERSION,
  INTRO_TEMPLATES,
  MINIMAX_TTS_DEFAULT_BASE_URL,
  MINIMAX_TTS_DEFAULT_MODEL,
  MINIMAX_TTS_DEFAULT_VOICE_ID,
  SETTINGS_KEY,
} from "./constants.js";

const SECRET_SETTINGS_KEY = `${SETTINGS_KEY}-session-secrets`;

export function createSettings({ els }) {
  let defaultCopyPrompt = "";
  let defaultCopyPrompts = {};
  let defaultCopyToStoryPrompt = "";
  let defaultImagePrompt = "";
  let defaultImproveImagePrompt = "";

  function copyPromptPreset() {
    return COPY_PROMPT_PRESETS.includes(els.copyPromptPreset?.value) ? els.copyPromptPreset.value : DEFAULT_COPY_PROMPT_PRESET;
  }

  function readJson(storage, key) {
    try {
      return JSON.parse(storage.getItem(key) || "{}");
    } catch {
      return {};
    }
  }

  function writeJson(storage, key, value) {
    try {
      storage.setItem(key, JSON.stringify(value));
    } catch {}
  }

  function cleanPersistedSettings(s) {
    const cleaned = { ...s };
    delete cleaned.apiKey;
    delete cleaned.ttsApiKey;
    return cleaned;
  }

  function applyTextProviderDefaults() {
    if (els.textProvider.value !== "gemini_web2api") return;
    if (!els.baseUrl.value.trim() || els.baseUrl.value.includes("api.example.com")) {
      els.baseUrl.value = GEMINI_WEB2API_DEFAULT_BASE_URL;
    }
    if (!els.model.value.trim() || els.model.value === "your-model-name") {
      els.model.value = GEMINI_WEB2API_DEFAULT_MODEL;
    }
    if (!els.apiKey.value.trim()) {
      els.apiKey.value = "sk-local";
    }
  }

  function applyTtsProviderDefaults() {
    if (!els.ttsProvider || els.ttsProvider.value !== "minimax") return;
    if (els.ttsBaseUrl && !els.ttsBaseUrl.value.trim()) els.ttsBaseUrl.value = MINIMAX_TTS_DEFAULT_BASE_URL;
    if (els.ttsModel && !els.ttsModel.value.trim()) els.ttsModel.value = MINIMAX_TTS_DEFAULT_MODEL;
    if (els.ttsVoiceId && !els.ttsVoiceId.value.trim()) els.ttsVoiceId.value = MINIMAX_TTS_DEFAULT_VOICE_ID;
    if (els.ttsSpeed && !els.ttsSpeed.value.trim()) els.ttsSpeed.value = "1.0";
    if (els.ttsLanguageBoost && !els.ttsLanguageBoost.value.trim()) els.ttsLanguageBoost.value = "Chinese";
  }

  function updateTtsProviderVisibility() {
    const isMiniMax = els.ttsProvider?.value === "minimax";
    document.querySelectorAll(".tts-minimax-field").forEach((node) => {
      node.hidden = !isMiniMax;
    });
    const voiceField = els.voice?.closest(".field");
    const rateField = els.rate?.closest(".field");
    if (voiceField) voiceField.hidden = isMiniMax;
    if (rateField) rateField.hidden = isMiniMax;
    applyTtsProviderDefaults();
  }

  function persist() {
    writeJson(localStorage, SETTINGS_KEY, {
      topic: els.topic.value,
      themeBrief: els.themeBrief?.value || "",
      themeIntro: els.themeIntro?.value || "",
      themeRevision: els.themeRevision?.value || "",
      textProvider: els.textProvider.value,
      baseUrl: els.baseUrl.value,
      model: els.model.value,
      imageProvider: els.imageProvider.value,
      imageBaseUrl: els.imageBaseUrl.value,
      imageModel: els.imageModel.value,
      imageApiKey: els.imageApiKey.value,
      imageSize: els.imageSize.value,
      introTemplate: els.introTemplate?.value || "none",
      introImageSeconds: els.introImageSeconds?.value || "0.3",
      ttsPreset: els.ttsPreset?.value || "custom",
      bgmSelect: els.bgmSelect?.value || "none",
      introSfxSelect: els.introSfxSelect?.value || "default",
      ttsProvider: els.ttsProvider?.value || "edge",
      ttsBaseUrl: els.ttsBaseUrl?.value || "",
      ttsGroupId: els.ttsGroupId?.value || "",
      ttsModel: els.ttsModel?.value || MINIMAX_TTS_DEFAULT_MODEL,
      ttsVoiceId: els.ttsVoiceId?.value || MINIMAX_TTS_DEFAULT_VOICE_ID,
      ttsSpeed: els.ttsSpeed?.value || "1.0",
      ttsEmotion: els.ttsEmotion?.value || "",
      ttsLanguageBoost: els.ttsLanguageBoost?.value || "Chinese",
      voice: els.voice.value,
      rate: els.rate.value,
      copyPromptPreset: copyPromptPreset(),
      copyPrompt: els.copyPrompt.value,
      copyPromptVersion: COPY_PROMPT_VERSION,
      copyToStoryPrompt: els.copyToStoryPrompt?.value || "",
      copyToStoryPromptVersion: COPY_TO_STORY_PROMPT_VERSION,
      imagePrompt: els.imagePrompt.value,
      improveImagePrompt: els.improveImagePrompt?.value || "",
      improveImagePromptVersion: IMPROVE_IMAGE_PROMPT_VERSION,
    });
    writeJson(sessionStorage, SECRET_SETTINGS_KEY, {
      apiKey: els.apiKey.value,
      imageApiKey: els.imageApiKey.value,
      ttsApiKey: els.ttsApiKey?.value || "",
    });
  }

  function load() {
    try {
      const s = readJson(localStorage, SETTINGS_KEY);
      const secrets = readJson(sessionStorage, SECRET_SETTINGS_KEY);
      if (s.apiKey || s.imageApiKey || s.ttsApiKey) {
        writeJson(sessionStorage, SECRET_SETTINGS_KEY, {
          apiKey: secrets.apiKey || s.apiKey || "",
          imageApiKey: secrets.imageApiKey || s.imageApiKey || "",
          ttsApiKey: secrets.ttsApiKey || s.ttsApiKey || "",
        });
        writeJson(localStorage, SETTINGS_KEY, cleanPersistedSettings(s));
      }
      if (secrets.imageApiKey && secrets.imageApiKey !== s.imageApiKey) {
        writeJson(localStorage, SETTINGS_KEY, {
          ...cleanPersistedSettings(s),
          imageApiKey: secrets.imageApiKey,
        });
      }
      els.textProvider.value = ["openai", "gemini_web2api"].includes(s.textProvider) ? s.textProvider : "openai";
      if (s.topic) els.topic.value = s.topic;
      if (els.themeBrief && typeof s.themeBrief === "string") els.themeBrief.value = s.themeBrief;
      if (els.themeIntro && typeof s.themeIntro === "string") els.themeIntro.value = s.themeIntro;
      if (els.themeRevision && typeof s.themeRevision === "string") els.themeRevision.value = s.themeRevision;
      els.baseUrl.value = s.baseUrl || "";
      els.model.value = s.model || "";
      els.apiKey.value = secrets.apiKey || s.apiKey || "";
      els.imageProvider.value = s.imageProvider === "openai" ? s.imageProvider : "openai";
      els.imageBaseUrl.value = s.imageBaseUrl || "";
      els.imageModel.value = s.imageModel || "";
      els.imageApiKey.value = secrets.imageApiKey || s.imageApiKey || "";
      els.imageSize.value = IMAGE_SIZES.includes(s.imageSize) ? s.imageSize : DEFAULT_IMAGE_SIZE;
      if (els.introTemplate) {
        els.introTemplate.value = INTRO_TEMPLATES.includes(s.introTemplate)
          ? s.introTemplate
          : DEFAULT_INTRO_TEMPLATE;
      }
      if (els.introImageSeconds) els.introImageSeconds.value = s.introImageSeconds || "0.3";
      if (els.ttsPreset) els.ttsPreset.value = s.ttsPreset || "male_fast";
      if (els.bgmSelect && s.bgmSelect && Array.from(els.bgmSelect.options).some((option) => option.value === s.bgmSelect)) {
        els.bgmSelect.value = s.bgmSelect;
      }
      if (els.introSfxSelect && s.introSfxSelect && Array.from(els.introSfxSelect.options).some((option) => option.value === s.introSfxSelect)) {
        els.introSfxSelect.value = s.introSfxSelect;
      }
      if (els.ttsProvider) els.ttsProvider.value = ["edge", "minimax"].includes(s.ttsProvider) ? s.ttsProvider : "edge";
      if (els.ttsBaseUrl) els.ttsBaseUrl.value = s.ttsBaseUrl || MINIMAX_TTS_DEFAULT_BASE_URL;
      if (els.ttsApiKey) els.ttsApiKey.value = secrets.ttsApiKey || s.ttsApiKey || "";
      if (els.ttsGroupId) els.ttsGroupId.value = s.ttsGroupId || "";
      if (els.ttsModel) els.ttsModel.value = s.ttsModel || MINIMAX_TTS_DEFAULT_MODEL;
      if (els.ttsVoiceId) els.ttsVoiceId.value = s.ttsVoiceId || MINIMAX_TTS_DEFAULT_VOICE_ID;
      if (els.ttsSpeed) els.ttsSpeed.value = s.ttsSpeed || "1.0";
      if (els.ttsEmotion) els.ttsEmotion.value = s.ttsEmotion || "";
      if (els.ttsLanguageBoost) els.ttsLanguageBoost.value = s.ttsLanguageBoost || "Chinese";
      els.voice.value = s.voice || "zh-CN-YunxiNeural";
      els.rate.value = s.rate || "+12%";
      if (els.copyPromptPreset) {
        els.copyPromptPreset.value = COPY_PROMPT_PRESETS.includes(s.copyPromptPreset) ? s.copyPromptPreset : DEFAULT_COPY_PROMPT_PRESET;
      }
      if (s.copyPrompt && s.copyPromptVersion === COPY_PROMPT_VERSION) els.copyPrompt.value = s.copyPrompt;
      if (els.copyToStoryPrompt && s.copyToStoryPrompt && s.copyToStoryPromptVersion === COPY_TO_STORY_PROMPT_VERSION) {
        els.copyToStoryPrompt.value = s.copyToStoryPrompt;
      }
      if (s.imagePrompt) els.imagePrompt.value = s.imagePrompt;
      if (els.improveImagePrompt && s.improveImagePrompt && s.improveImagePromptVersion === IMPROVE_IMAGE_PROMPT_VERSION) {
        els.improveImagePrompt.value = s.improveImagePrompt;
      }
      applyTextProviderDefaults();
      updateTtsProviderVisibility();
    } catch {}
  }

  async function loadPromptDefaults(fetchJson, updatePromptMeta) {
    const [copyData, copyXianxiaData, copyToStoryData, imageData, improveImageData] = await Promise.all([
      fetchJson("/api/prompt/default"),
      fetchJson("/api/prompt/copy-xianxia"),
      fetchJson("/api/prompt/copy-to-story"),
      fetchJson("/api/prompt/image"),
      fetchJson("/api/prompt/improve-image"),
    ]);
    defaultCopyPrompts = {
      reality: copyData.prompt || "",
      xianxia: copyXianxiaData.prompt || "",
    };
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality || "";
    defaultCopyToStoryPrompt = copyToStoryData.prompt || "";
    defaultImagePrompt = imageData.prompt || "";
    defaultImproveImagePrompt = improveImageData.prompt || "";
    if (!els.copyPrompt.value.trim()) els.copyPrompt.value = defaultCopyPrompt;
    if (els.copyToStoryPrompt && !els.copyToStoryPrompt.value.trim()) {
      els.copyToStoryPrompt.value = defaultCopyToStoryPrompt;
      persist();
    }
    if (!els.imagePrompt.value.trim()) els.imagePrompt.value = defaultImagePrompt;
    if (els.improveImagePrompt && !els.improveImagePrompt.value.trim()) {
      els.improveImagePrompt.value = defaultImproveImagePrompt;
      persist();
    }
    updatePromptMeta();
  }

  function resetCopyPrompt(updatePromptMeta, scheduleSave) {
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality || "";
    els.copyPrompt.value = defaultCopyPrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function applyCopyPromptPreset(updatePromptMeta, scheduleSave) {
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality || "";
    if (defaultCopyPrompt) els.copyPrompt.value = defaultCopyPrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function resetCopyToStoryPrompt(updatePromptMeta, scheduleSave) {
    if (!els.copyToStoryPrompt) return;
    els.copyToStoryPrompt.value = defaultCopyToStoryPrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function resetImagePrompt(updatePromptMeta, scheduleSave) {
    els.imagePrompt.value = defaultImagePrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function resetImproveImagePrompt(updatePromptMeta, scheduleSave) {
    if (!els.improveImagePrompt) return;
    els.improveImagePrompt.value = defaultImproveImagePrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function textPayload() {
    return {
      topic: els.topic.value.trim(),
      topic_intro: els.themeIntro?.value.trim() || "",
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      system_prompt: els.copyPrompt.value,
      temperature: 0.8,
    };
  }

  function storyPayload() {
    return {
      topic: els.topic.value.trim(),
      topic_intro: els.themeIntro?.value.trim() || "",
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.8,
    };
  }

  function textConnectionPayload() {
    return {
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0,
    };
  }

  function themePayload() {
    return {
      brief: els.themeBrief?.value.trim() || els.topic.value.trim(),
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.7,
    };
  }

  function themeRevisionPayload() {
    return {
      ...themePayload(),
      topic: els.topic.value.trim(),
      intro: els.themeIntro?.value.trim() || "",
      instruction: els.themeRevision?.value.trim() || "",
    };
  }

  function copyToStoryPayload(copyText) {
    return {
      topic: els.topic.value.trim(),
      topic_intro: els.themeIntro?.value.trim() || "",
      copy_text: copyText.trim(),
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      system_prompt: els.copyToStoryPrompt?.value || "",
      temperature: 0.5,
    };
  }

  function imageConnectionPayload() {
    return {
      provider: els.imageProvider.value,
      base_url: els.imageBaseUrl.value.trim(),
      model: els.imageModel.value.trim(),
      api_key: els.imageApiKey.value.trim(),
      size: els.imageSize.value.trim() || DEFAULT_IMAGE_SIZE,
    };
  }

  function imagePayload(story, extra = {}) {
    return {
      story,
      provider: els.imageProvider.value,
      base_url: els.imageBaseUrl.value.trim(),
      model: els.imageModel.value.trim(),
      api_key: els.imageApiKey.value.trim(),
      size: els.imageSize.value.trim() || DEFAULT_IMAGE_SIZE,
      fixed_prompt: els.imagePrompt.value,
      ...extra,
    };
  }

  function improveImagePromptPayload(story, shotIndex) {
    return {
      story,
      shot_index: shotIndex,
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.4,
      system_prompt: els.improveImagePrompt?.value || "",
    };
  }

  return {
    applyTextProviderDefaults,
    persist,
    load,
    loadPromptDefaults,
    resetCopyPrompt,
    applyCopyPromptPreset,
    resetCopyToStoryPrompt,
    resetImagePrompt,
    resetImproveImagePrompt,
    textPayload,
    storyPayload,
    themePayload,
    themeRevisionPayload,
    textConnectionPayload,
    copyToStoryPayload,
    imageConnectionPayload,
    imagePayload,
    improveImagePromptPayload,
    applyTtsProviderDefaults,
    updateTtsProviderVisibility,
  };
}
