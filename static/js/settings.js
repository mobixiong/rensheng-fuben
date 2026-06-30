import {
  GEMINI_WEB2API_DEFAULT_BASE_URL,
  GEMINI_WEB2API_DEFAULT_MODEL,
  SETTINGS_KEY,
} from "./constants.js";

const SECRET_SETTINGS_KEY = `${SETTINGS_KEY}-session-secrets`;

export function createSettings({ els }) {
  let defaultCopyPrompt = "";
  let defaultImagePrompt = "";

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
    delete cleaned.imageApiKey;
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

  function persist() {
    writeJson(localStorage, SETTINGS_KEY, {
      topic: els.topic.value,
      textProvider: els.textProvider.value,
      baseUrl: els.baseUrl.value,
      model: els.model.value,
      imageProvider: els.imageProvider.value,
      imageBaseUrl: els.imageBaseUrl.value,
      imageModel: els.imageModel.value,
      imageSize: els.imageSize.value,
      voice: els.voice.value,
      rate: els.rate.value,
      copyPrompt: els.copyPrompt.value,
      imagePrompt: els.imagePrompt.value,
    });
    writeJson(sessionStorage, SECRET_SETTINGS_KEY, {
      apiKey: els.apiKey.value,
      imageApiKey: els.imageApiKey.value,
    });
  }

  function load() {
    try {
      const s = readJson(localStorage, SETTINGS_KEY);
      const secrets = readJson(sessionStorage, SECRET_SETTINGS_KEY);
      if (s.apiKey || s.imageApiKey) {
        writeJson(sessionStorage, SECRET_SETTINGS_KEY, {
          apiKey: secrets.apiKey || s.apiKey || "",
          imageApiKey: secrets.imageApiKey || s.imageApiKey || "",
        });
        writeJson(localStorage, SETTINGS_KEY, cleanPersistedSettings(s));
      }
      els.textProvider.value = ["openai", "gemini_web2api"].includes(s.textProvider) ? s.textProvider : "openai";
      if (s.topic) els.topic.value = s.topic;
      els.baseUrl.value = s.baseUrl || "";
      els.model.value = s.model || "";
      els.apiKey.value = secrets.apiKey || s.apiKey || "";
      els.imageProvider.value = s.imageProvider === "openai" ? s.imageProvider : "openai";
      els.imageBaseUrl.value = s.imageBaseUrl || "";
      els.imageModel.value = s.imageModel || "";
      els.imageApiKey.value = secrets.imageApiKey || s.imageApiKey || "";
      els.imageSize.value = ["9:16", "1:1", "16:9"].includes(s.imageSize) ? s.imageSize : "9:16";
      els.voice.value = s.voice || "zh-CN-YunxiNeural";
      els.rate.value = s.rate || "+12%";
      if (s.copyPrompt) els.copyPrompt.value = s.copyPrompt;
      if (s.imagePrompt) els.imagePrompt.value = s.imagePrompt;
      applyTextProviderDefaults();
    } catch {}
  }

  async function loadPromptDefaults(fetchJson, updatePromptMeta) {
    const [copyData, imageData] = await Promise.all([
      fetchJson("/api/prompt/default"),
      fetchJson("/api/prompt/image"),
    ]);
    defaultCopyPrompt = copyData.prompt || "";
    defaultImagePrompt = imageData.prompt || "";
    if (!els.copyPrompt.value.trim()) els.copyPrompt.value = defaultCopyPrompt;
    if (!els.imagePrompt.value.trim()) els.imagePrompt.value = defaultImagePrompt;
    updatePromptMeta();
  }

  function resetCopyPrompt(updatePromptMeta, scheduleSave) {
    els.copyPrompt.value = defaultCopyPrompt;
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

  function textPayload() {
    return {
      topic: els.topic.value.trim(),
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

  function copyToStoryPayload(copyText) {
    return {
      topic: els.topic.value.trim(),
      copy_text: copyText.trim(),
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.5,
    };
  }

  function imageConnectionPayload() {
    return {
      provider: els.imageProvider.value,
      base_url: els.imageBaseUrl.value.trim(),
      model: els.imageModel.value.trim(),
      api_key: els.imageApiKey.value.trim(),
      size: els.imageSize.value.trim() || "9:16",
    };
  }

  function imagePayload(story, extra = {}) {
    return {
      story,
      provider: els.imageProvider.value,
      base_url: els.imageBaseUrl.value.trim(),
      model: els.imageModel.value.trim(),
      api_key: els.imageApiKey.value.trim(),
      size: els.imageSize.value.trim() || "9:16",
      fixed_prompt: els.imagePrompt.value,
      ...extra,
    };
  }

  return {
    applyTextProviderDefaults,
    persist,
    load,
    loadPromptDefaults,
    resetCopyPrompt,
    resetImagePrompt,
    textPayload,
    storyPayload,
    textConnectionPayload,
    copyToStoryPayload,
    imageConnectionPayload,
    imagePayload,
  };
}
