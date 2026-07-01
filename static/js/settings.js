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
const IMAGE_STYLE_PRESET_KEYS = ["short_video", "realistic", "cinematic", "anime"];
const IMAGE_STYLE_COMMON_RULES = [
  "景别以中景、全景为主，禁止连续使用人物大特写。",
  "人物出现时不要占满画面，角色与背景环境比例均衡，背景场景清晰可见。",
  "连续分镜中穿插纯场景空镜，允许用环境物件、道具和场景氛围推进叙事。",
  "整体画面必须符合当前镜头图片提示词的描述意境，场景构图服务于叙事内容。",
  "不要出现可读文字、字幕、界面、Logo、水印、二维码、品牌名或招牌文字。",
  "不要添加当前镜头图片提示词里没有的额外剧情元素。",
];
const IMAGE_STYLE_PRESET_DEFINITIONS = {
  realistic: {
    visual:
      "真实影视剧质感，自然光影，现实生活场景，人物比例真实，服装、道具、环境符合当代中国语境。画面有纪实剧情片氛围，情绪清晰但不过度表演，光影真实克制，有明确阴影和环境细节，不要过度奇幻化。",
    subject:
      "真实人物或真实主体物，五官、身体、服饰和动作符合现实逻辑。人物可有疲惫、紧张、震惊、压抑等情绪，但表演要克制自然，不要卡通化、表情包化或过度夸张。",
  },
  cinematic: {
    visual:
      "电影剧照质感，戏剧性光影，强烈但克制的视觉重点，画面有前景、中景、背景层次。可使用高对比阴影、实际光源、景深、低饱和或统一色彩倾向，整体像悬疑剧情片或社会现实电影分镜。",
    subject:
      "人物或主体物要融入电影场景，不要做成孤立头像或证件照式构图。人物姿态、表情和道具共同传达情绪，主体与空间关系清楚，有叙事张力。",
  },
  anime: {
    visual:
      "高质量 2D 二次元动画插画风，干净线稿，精致赛璐璐上色，背景细节丰富，光影有氛围，色彩完成度高。画面是动画分镜式构图，场景信息清楚，情绪节点明确，避免连续大头特写。",
    subject:
      "二次元动画角色或动画化主体物，人物表情有情绪但不过度夸张。角色服装和动作符合镜头语境，人物占画面比例适中，保留足够环境信息，不要做成单人头像海报。",
  },
};

function buildImageStylePrompt({ visual, subject }) {
  return [
    "视频视觉风格锚定词：",
    visual,
    "",
    "人物或主体物风格锚定词：",
    subject,
    "",
    "构图与叙事规则：",
    IMAGE_STYLE_COMMON_RULES.join("\n"),
  ].join("\n");
}
const LEGACY_ENGLISH_IMAGE_PROMPT_MARKERS = [
  "SCENE CONSTRUCTION",
  "Create one vertical",
  "Visual style:",
  "Composition rules:",
  "Show exactly one clear action",
  "Match the provided voiceover",
];

export function createSettings({ els }) {
  let defaultCopyPrompt = "";
  let defaultCopyPrompts = {};
  let defaultCopyToStoryPrompt = "";
  let defaultImagePrompt = "";
  let defaultImproveImagePrompt = "";

  function copyPromptPreset() {
    return COPY_PROMPT_PRESETS.includes(els.copyPromptPreset?.value) ? els.copyPromptPreset.value : DEFAULT_COPY_PROMPT_PRESET;
  }

  function imageStylePreset() {
    return IMAGE_STYLE_PRESET_KEYS.includes(els.imageStylePreset?.value) ? els.imageStylePreset.value : "short_video";
  }

  function imageStylePrompt(preset = imageStylePreset()) {
    if (preset === "short_video") return defaultImagePrompt;
    const definition = IMAGE_STYLE_PRESET_DEFINITIONS[preset];
    return definition ? buildImageStylePrompt(definition) : defaultImagePrompt;
  }

  function isLegacyEnglishImagePrompt(value) {
    const text = String(value || "");
    return LEGACY_ENGLISH_IMAGE_PROMPT_MARKERS.some((marker) => text.includes(marker));
  }

  function syncImageStylePresetPrompt(updatePromptMeta, options = {}) {
    const preset = imageStylePreset();
    if (!els.imagePrompt) return false;
    const current = els.imagePrompt.value || "";
    if (current.trim() && !isLegacyEnglishImagePrompt(current) && !options.force) return false;
    const prompt = imageStylePrompt(preset);
    if (!prompt) return false;
    els.imagePrompt.value = prompt;
    if (updatePromptMeta) updatePromptMeta();
    return true;
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
      imageStylePreset: imageStylePreset(),
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
      if (els.imageStylePreset) {
        els.imageStylePreset.value = IMAGE_STYLE_PRESET_KEYS.includes(s.imageStylePreset) ? s.imageStylePreset : "short_video";
      }
      if (s.copyPrompt && s.copyPromptVersion === COPY_PROMPT_VERSION) els.copyPrompt.value = s.copyPrompt;
      if (els.copyToStoryPrompt && s.copyToStoryPrompt && s.copyToStoryPromptVersion === COPY_TO_STORY_PROMPT_VERSION) {
        els.copyToStoryPrompt.value = s.copyToStoryPrompt;
      }
      if (s.imagePrompt) els.imagePrompt.value = s.imagePrompt;
      syncImageStylePresetPrompt();
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
    if (!els.imagePrompt.value.trim()) els.imagePrompt.value = imageStylePrompt();
    syncImageStylePresetPrompt(updatePromptMeta);
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
    if (els.imageStylePreset) els.imageStylePreset.value = "short_video";
    els.imagePrompt.value = defaultImagePrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function applyImageStylePreset(updatePromptMeta, scheduleSave) {
    syncImageStylePresetPrompt(updatePromptMeta, { force: true });
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
    applyImageStylePreset,
    syncImageStylePresetPrompt,
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
