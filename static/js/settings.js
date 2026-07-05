import {
  AUTO_COPY_PROMPT_PRESETS,
  COPY_PRESET_THEME_INSTRUCTIONS,
  COPY_PROMPT_PRESETS,
  COPY_PROMPT_VERSION,
  COPY_TO_STORY_PROMPT_VERSION,
  DEFAULT_AUTO_COPY_PROMPT_PRESET,
  DEFAULT_COPY_PROMPT_PRESET,
  DEFAULT_IMAGE_SIZE,
  DEFAULT_INTRO_TEMPLATE,
  DEFAULT_STORYBOARD_GRANULARITY,
  DOUBAO_TTS_DEFAULT_BASE_URL,
  DOUBAO_TTS_DEFAULT_MODEL,
  DOUBAO_TTS_DEFAULT_VOICE_ID,
  DOUBAO_TTS_MODELS,
  GEMINI_WEB2API_DEFAULT_BASE_URL,
  GEMINI_WEB2API_DEFAULT_MODEL,
  IMAGE_CONCURRENCY_LIMIT,
  IMAGE_SIZES,
  IMPROVE_IMAGE_PROMPT_VERSION,
  INTRO_TEMPLATES,
  MINIMAX_TTS_DEFAULT_BASE_URL,
  MINIMAX_TTS_DEFAULT_MODEL,
  MINIMAX_TTS_DEFAULT_VOICE_ID,
  MINIMAX_TTS_MODELS,
  SETTINGS_KEY,
  STORYBOARD_GRANULARITIES,
  THEME_IDEA_PROMPT_VERSION,
} from "./constants.js?v=20260705_doubao_tts";

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
  let defaultThemeIdeaPrompt = "";

  function copyPromptPreset() {
    return syncCopyPromptPreset(els.copyPromptPreset?.value || els.themeCopyPreset?.value || DEFAULT_COPY_PROMPT_PRESET);
  }

  function syncCopyPromptPreset(value) {
    const preset = COPY_PROMPT_PRESETS.includes(value) ? value : DEFAULT_COPY_PROMPT_PRESET;
    if (els.copyPromptPreset && els.copyPromptPreset.value !== preset) els.copyPromptPreset.value = preset;
    if (els.themeCopyPreset && els.themeCopyPreset.value !== preset) els.themeCopyPreset.value = preset;
    return preset;
  }

  function autoCopyPromptPreset() {
    return AUTO_COPY_PROMPT_PRESETS.includes(els.autoCopyPreset?.value)
      ? els.autoCopyPreset.value
      : DEFAULT_AUTO_COPY_PROMPT_PRESET;
  }

  function themeStyleInstruction() {
    const preset = copyPromptPreset();
    return COPY_PRESET_THEME_INSTRUCTIONS[preset] || COPY_PRESET_THEME_INSTRUCTIONS.reality_reverse || "";
  }

  function themeBriefWithStyle(brief) {
    const cleanBrief = String(brief || "").trim();
    const instruction = themeStyleInstruction();
    if (!instruction) return cleanBrief;
    return [
      instruction,
      `用户原始选题方向：${cleanBrief || "未填写，请按上述文案类型自动给出方向"}`,
    ].join("\n\n");
  }

  function imageStylePreset() {
    return IMAGE_STYLE_PRESET_KEYS.includes(els.imageStylePreset?.value) ? els.imageStylePreset.value : "short_video";
  }

  function storyboardGranularity(value = els.storyboardGranularity?.value) {
    return STORYBOARD_GRANULARITIES.includes(value) ? value : DEFAULT_STORYBOARD_GRANULARITY;
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

  function optionExists(select, value) {
    return Array.from(select?.options || []).some((option) => option.value === value);
  }

  function setSelectOptions(select, options, fallbackValue, preferredValue = "") {
    if (!select) return;
    const current = preferredValue || select.value;
    select.replaceChildren(...options.map((item) => {
      const option = document.createElement("option");
      if (typeof item === "string") {
        option.value = item;
        option.textContent = item;
      } else {
        option.value = item.value;
        option.textContent = item.label || item.value;
      }
      return option;
    }));
    select.value = optionExists(select, current) ? current : fallbackValue;
  }

  function syncTtsModelOptions(preferredValue = "") {
    if (!els.ttsModel) return;
    if (els.ttsProvider?.value === "doubao") {
      setSelectOptions(els.ttsModel, DOUBAO_TTS_MODELS, DOUBAO_TTS_DEFAULT_MODEL, preferredValue);
      return;
    }
    setSelectOptions(els.ttsModel, MINIMAX_TTS_MODELS, MINIMAX_TTS_DEFAULT_MODEL, preferredValue);
  }

  function replaceIfBlankOrKnown(input, value, knownValues = []) {
    if (!input) return;
    const current = input.value.trim();
    if (!current || knownValues.includes(current)) input.value = value;
  }

  function applyTtsProviderDefaults() {
    if (!els.ttsProvider || els.ttsProvider.value === "edge") return;
    syncTtsModelOptions();
    if (els.ttsProvider.value === "doubao") {
      replaceIfBlankOrKnown(els.ttsBaseUrl, DOUBAO_TTS_DEFAULT_BASE_URL, [MINIMAX_TTS_DEFAULT_BASE_URL]);
      replaceIfBlankOrKnown(els.ttsVoiceId, DOUBAO_TTS_DEFAULT_VOICE_ID, [MINIMAX_TTS_DEFAULT_VOICE_ID]);
      if (els.ttsModel && !optionExists(els.ttsModel, els.ttsModel.value)) els.ttsModel.value = DOUBAO_TTS_DEFAULT_MODEL;
      if (els.ttsSpeed && !els.ttsSpeed.value.trim()) els.ttsSpeed.value = "1.0";
      return;
    }
    replaceIfBlankOrKnown(els.ttsBaseUrl, MINIMAX_TTS_DEFAULT_BASE_URL, [DOUBAO_TTS_DEFAULT_BASE_URL]);
    replaceIfBlankOrKnown(els.ttsVoiceId, MINIMAX_TTS_DEFAULT_VOICE_ID, [DOUBAO_TTS_DEFAULT_VOICE_ID]);
    if (els.ttsModel && !optionExists(els.ttsModel, els.ttsModel.value)) els.ttsModel.value = MINIMAX_TTS_DEFAULT_MODEL;
    if (els.ttsSpeed && !els.ttsSpeed.value.trim()) els.ttsSpeed.value = "1.0";
    if (els.ttsLanguageBoost && !els.ttsLanguageBoost.value.trim()) els.ttsLanguageBoost.value = "Chinese";
  }

  function updateTtsProviderVisibility() {
    const provider = els.ttsProvider?.value || "edge";
    syncTtsModelOptions();
    document.querySelectorAll(".tts-provider-field").forEach((node) => {
      const providers = String(node.dataset.ttsProviders || "").split(/\s+/).filter(Boolean);
      node.hidden = !providers.includes(provider);
    });
    const voiceField = els.voice?.closest(".field");
    const rateField = els.rate?.closest(".field");
    if (voiceField) voiceField.hidden = provider !== "edge";
    if (rateField) rateField.hidden = provider !== "edge";
    applyTtsProviderDefaults();
  }

  function persist() {
    writeJson(localStorage, SETTINGS_KEY, {
      topic: els.topic.value,
      themeBrief: els.themeBrief?.value || "",
      themeIntro: els.themeIntro?.value || "",
      themeRevision: els.themeRevision?.value || "",
      autoBrief: els.autoBrief?.value || "",
      autoCopyPreset: autoCopyPromptPreset(),
      autoStoryboardGranularity: storyboardGranularity(els.autoStoryboardGranularity?.value),
      autoImageSize: els.autoImageSize?.value || DEFAULT_IMAGE_SIZE,
      autoIntroTemplate: els.autoIntroTemplate?.value || DEFAULT_INTRO_TEMPLATE,
      autoTtsPreset: els.autoTtsPreset?.value || "male_fast",
      autoOptimizeImagePrompts: Boolean(els.autoOptimizeImagePrompts?.checked),
      autoInfiniteImageRetry: Boolean(els.autoInfiniteImageRetry?.checked),
      autoRenderAfterImages: Boolean(els.autoRenderAfterImages?.checked),
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
      storyboardGranularity: storyboardGranularity(),
      copyPrompt: els.copyPrompt.value,
      copyPromptVersion: COPY_PROMPT_VERSION,
      copyToStoryPrompt: els.copyToStoryPrompt?.value || "",
      copyToStoryPromptVersion: COPY_TO_STORY_PROMPT_VERSION,
      imageStylePreset: imageStylePreset(),
      imagePrompt: els.imagePrompt.value,
      improveImagePrompt: els.improveImagePrompt?.value || "",
      improveImagePromptVersion: IMPROVE_IMAGE_PROMPT_VERSION,
      themeIdeaPrompt: els.themeIdeaPrompt?.value || "",
      themeIdeaPromptVersion: THEME_IDEA_PROMPT_VERSION,
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
      if (els.autoBrief && typeof s.autoBrief === "string") els.autoBrief.value = s.autoBrief;
      if (els.autoCopyPreset) {
        els.autoCopyPreset.value = AUTO_COPY_PROMPT_PRESETS.includes(s.autoCopyPreset) ? s.autoCopyPreset : DEFAULT_AUTO_COPY_PROMPT_PRESET;
      }
      if (els.autoStoryboardGranularity) els.autoStoryboardGranularity.value = storyboardGranularity(s.autoStoryboardGranularity);
      if (els.autoImageSize) els.autoImageSize.value = IMAGE_SIZES.includes(s.autoImageSize) ? s.autoImageSize : DEFAULT_IMAGE_SIZE;
      if (els.autoIntroTemplate) els.autoIntroTemplate.value = INTRO_TEMPLATES.includes(s.autoIntroTemplate) ? s.autoIntroTemplate : DEFAULT_INTRO_TEMPLATE;
      if (els.autoTtsPreset) els.autoTtsPreset.value = s.autoTtsPreset || "male_fast";
      if (els.autoOptimizeImagePrompts) els.autoOptimizeImagePrompts.checked = s.autoOptimizeImagePrompts !== false;
      if (els.autoInfiniteImageRetry) els.autoInfiniteImageRetry.checked = Boolean(s.autoInfiniteImageRetry);
      if (els.autoRenderAfterImages) els.autoRenderAfterImages.checked = s.autoRenderAfterImages !== false;
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
      if (els.ttsProvider) els.ttsProvider.value = ["edge", "minimax", "doubao", "volcengine"].includes(s.ttsProvider) ? (s.ttsProvider === "volcengine" ? "doubao" : s.ttsProvider) : "edge";
      syncTtsModelOptions(s.ttsModel || "");
      if (els.ttsBaseUrl) els.ttsBaseUrl.value = s.ttsBaseUrl || (els.ttsProvider?.value === "doubao" ? DOUBAO_TTS_DEFAULT_BASE_URL : MINIMAX_TTS_DEFAULT_BASE_URL);
      if (els.ttsApiKey) els.ttsApiKey.value = secrets.ttsApiKey || s.ttsApiKey || "";
      if (els.ttsGroupId) els.ttsGroupId.value = s.ttsGroupId || "";
      if (els.ttsModel) els.ttsModel.value = optionExists(els.ttsModel, s.ttsModel) ? s.ttsModel : (els.ttsProvider?.value === "doubao" ? DOUBAO_TTS_DEFAULT_MODEL : MINIMAX_TTS_DEFAULT_MODEL);
      if (els.ttsVoiceId) els.ttsVoiceId.value = s.ttsVoiceId || (els.ttsProvider?.value === "doubao" ? DOUBAO_TTS_DEFAULT_VOICE_ID : MINIMAX_TTS_DEFAULT_VOICE_ID);
      if (els.ttsSpeed) els.ttsSpeed.value = s.ttsSpeed || "1.0";
      if (els.ttsEmotion) els.ttsEmotion.value = s.ttsEmotion || "";
      if (els.ttsLanguageBoost) els.ttsLanguageBoost.value = s.ttsLanguageBoost || "Chinese";
      els.voice.value = s.voice || "zh-CN-YunxiNeural";
      els.rate.value = s.rate || "+12%";
      if (els.copyPromptPreset) {
        syncCopyPromptPreset(s.copyPromptPreset);
      }
      if (els.storyboardGranularity) els.storyboardGranularity.value = storyboardGranularity(s.storyboardGranularity);
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
      if (els.themeIdeaPrompt && s.themeIdeaPrompt && s.themeIdeaPromptVersion === THEME_IDEA_PROMPT_VERSION) {
        els.themeIdeaPrompt.value = s.themeIdeaPrompt;
      }
      applyTextProviderDefaults();
      updateTtsProviderVisibility();
    } catch {}
  }

  async function loadPromptDefaults(fetchJson, updatePromptMeta) {
    const [
      copyData,
      copyBreakoutData,
      copyStopLossData,
      copyBurnoutSupportData,
      copyXianxiaData,
      copyWuxiaData,
      copyZombieData,
      copyOtherworldData,
      copyCyberpunkData,
      copyWeirdRulesData,
      copyToStoryData,
      imageData,
      improveImageData,
      themeIdeaData,
    ] = await Promise.all([
      fetchJson("/api/prompt/default"),
      fetchJson("/api/prompt/copy-reality-breakout"),
      fetchJson("/api/prompt/copy-reality-stop-loss"),
      fetchJson("/api/prompt/copy-reality-burnout-support"),
      fetchJson("/api/prompt/copy-xianxia"),
      fetchJson("/api/prompt/copy-fantasy-wuxia"),
      fetchJson("/api/prompt/copy-fantasy-zombie"),
      fetchJson("/api/prompt/copy-fantasy-otherworld"),
      fetchJson("/api/prompt/copy-fantasy-cyberpunk"),
      fetchJson("/api/prompt/copy-fantasy-weird-rules"),
      fetchJson("/api/prompt/copy-to-story"),
      fetchJson("/api/prompt/image"),
      fetchJson("/api/prompt/improve-image"),
      fetchJson("/api/prompt/theme-ideas"),
    ]);
    defaultCopyPrompts = {
      reality_reverse: copyData.prompt || "",
      reality_breakout: copyBreakoutData.prompt || "",
      reality_stop_loss: copyStopLossData.prompt || "",
      reality_burnout_support: copyBurnoutSupportData.prompt || "",
      xianxia: copyXianxiaData.prompt || "",
      fantasy_wuxia: copyWuxiaData.prompt || "",
      fantasy_zombie: copyZombieData.prompt || "",
      fantasy_otherworld: copyOtherworldData.prompt || "",
      fantasy_cyberpunk: copyCyberpunkData.prompt || "",
      fantasy_weird_rules: copyWeirdRulesData.prompt || "",
    };
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality_reverse || "";
    defaultCopyToStoryPrompt = copyToStoryData.prompt || "";
    defaultImagePrompt = imageData.prompt || "";
    defaultImproveImagePrompt = improveImageData.prompt || "";
    defaultThemeIdeaPrompt = themeIdeaData.prompt || "";
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
    if (els.themeIdeaPrompt && !els.themeIdeaPrompt.value.trim()) {
      els.themeIdeaPrompt.value = defaultThemeIdeaPrompt;
      persist();
    }
    updatePromptMeta();
  }

  function resetCopyPrompt(updatePromptMeta, scheduleSave) {
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality_reverse || "";
    els.copyPrompt.value = defaultCopyPrompt;
    persist();
    updatePromptMeta();
    scheduleSave();
  }

  function applyCopyPromptPreset(updatePromptMeta, scheduleSave, presetValue = "") {
    if (presetValue) syncCopyPromptPreset(presetValue);
    else syncCopyPromptPreset(els.copyPromptPreset?.value || els.themeCopyPreset?.value);
    defaultCopyPrompt = defaultCopyPrompts[copyPromptPreset()] || defaultCopyPrompts.reality_reverse || "";
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

  function resetThemeIdeaPrompt(updatePromptMeta, scheduleSave) {
    if (!els.themeIdeaPrompt) return;
    els.themeIdeaPrompt.value = defaultThemeIdeaPrompt;
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
    const brief = els.themeBrief?.value.trim() || els.topic.value.trim();
    return {
      brief: themeBriefWithStyle(brief),
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.7,
    };
  }

  function themeIdeasPayload(extra = {}) {
    const baseInstruction = themeStyleInstruction();
    const extraInstruction = String(extra.instruction || "").trim();
    return {
      brief: els.themeBrief?.value.trim() || "",
      provider: els.textProvider.value,
      base_url: els.baseUrl.value.trim(),
      model: els.model.value.trim(),
      api_key: els.apiKey.value.trim(),
      temperature: 0.8,
      system_prompt: els.themeIdeaPrompt?.value || "",
      count: 6,
      ...extra,
      instruction: [baseInstruction, extraInstruction].filter(Boolean).join("\n\n"),
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
      storyboard_granularity: storyboardGranularity(),
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

  function ttsConfigPayload() {
    const provider = els.ttsProvider?.value || "edge";
    if (provider === "edge") {
      return {
        provider,
        base_url: "",
        api_key: "",
        group_id: "",
        model: "",
        voice_id: "",
        speed: 1,
        emotion: "",
        language_boost: "",
      };
    }
    return {
      provider,
      base_url: els.ttsBaseUrl?.value.trim() || "",
      api_key: els.ttsApiKey?.value.trim() || "",
      group_id: els.ttsGroupId?.value.trim() || "",
      model: els.ttsModel?.value.trim() || "",
      voice_id: els.ttsVoiceId?.value.trim() || "",
      speed: Number.parseFloat(els.ttsSpeed?.value || "1") || 1,
      emotion: els.ttsEmotion?.value || "",
      language_boost: els.ttsLanguageBoost?.value || "",
    };
  }

  function ttsPreviewPayload() {
    const config = ttsConfigPayload();
    return {
      text: "今天体验的人生副本，是一次新的开始。",
      voice: els.voice?.value || "zh-CN-YunxiNeural",
      rate: els.rate?.value || "+12%",
      tts_provider: config.provider,
      tts_base_url: config.base_url,
      tts_api_key: config.api_key,
      tts_group_id: config.group_id,
      tts_model: config.model,
      tts_voice_id: config.voice_id,
      tts_speed: config.speed,
      tts_emotion: config.emotion,
      tts_language_boost: config.language_boost,
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

  function autoPipelinePayload() {
    const ttsOption = els.autoTtsPreset?.selectedOptions?.[0];
    const useConfiguredTts = els.autoTtsPreset?.value === "custom";
    const configuredTts = ttsConfigPayload();
    return {
      project_id: "",
      brief: els.autoBrief?.value.trim() || "",
      copy_preset: autoCopyPromptPreset(),
      storyboard_granularity: storyboardGranularity(els.autoStoryboardGranularity?.value),
      image_size: IMAGE_SIZES.includes(els.autoImageSize?.value) ? els.autoImageSize.value : (els.imageSize?.value || DEFAULT_IMAGE_SIZE),
      reference_collection_id: els.projectReferenceCollection?.value || "",
      auto_reference_enabled: Boolean(els.autoReferenceEnabled?.checked && els.projectReferenceCollection?.value),
      intro_template: INTRO_TEMPLATES.includes(els.autoIntroTemplate?.value) ? els.autoIntroTemplate.value : (els.introTemplate?.value || DEFAULT_INTRO_TEMPLATE),
      intro_image_seconds: Number.parseFloat(els.introImageSeconds?.value || "0.3") || 0.3,
      tts_preset: els.autoTtsPreset?.value || els.ttsPreset?.value || "custom",
      voice: ttsOption?.dataset?.voice || els.voice?.value || "zh-CN-YunxiNeural",
      rate: ttsOption?.dataset?.rate || els.rate?.value || "+12%",
      tts_speed: useConfiguredTts ? configuredTts.speed : 1,
      tts_emotion: useConfiguredTts ? configuredTts.emotion : "",
      tts_language_boost: useConfiguredTts ? configuredTts.language_boost : "Chinese",
      bgm_id: els.bgmSelect?.value || "none",
      intro_sfx_id: els.introSfxSelect?.value || "default",
      auto_optimize_image_prompts: els.autoOptimizeImagePrompts?.checked !== false,
      auto_infinite_image_retry: Boolean(els.autoInfiniteImageRetry?.checked),
      render_after_images: els.autoRenderAfterImages?.checked !== false,
      image_concurrency: IMAGE_CONCURRENCY_LIMIT,
      theme_idea_prompt: els.themeIdeaPrompt?.value || "",
      copy_prompt: autoCopyPromptPreset() === "random" ? "" : (defaultCopyPrompts[autoCopyPromptPreset()] || els.copyPrompt?.value || ""),
      copy_to_story_prompt: els.copyToStoryPrompt?.value || "",
      image_prompt: els.imagePrompt?.value || "",
      improve_image_prompt: els.improveImagePrompt?.value || "",
      text_config: {
        provider: els.textProvider.value,
        base_url: els.baseUrl.value.trim(),
        model: els.model.value.trim(),
        api_key: els.apiKey.value.trim(),
      },
      image_config: {
        provider: els.imageProvider.value,
        base_url: els.imageBaseUrl.value.trim(),
        model: els.imageModel.value.trim(),
        api_key: els.imageApiKey.value.trim(),
      },
      tts_config: {
        provider: useConfiguredTts ? configuredTts.provider : "edge",
        base_url: useConfiguredTts ? configuredTts.base_url : "",
        api_key: useConfiguredTts ? configuredTts.api_key : "",
        group_id: useConfiguredTts ? configuredTts.group_id : "",
        model: useConfiguredTts ? configuredTts.model : "",
        voice_id: useConfiguredTts ? configuredTts.voice_id : "",
      },
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
    resetThemeIdeaPrompt,
    textPayload,
    storyPayload,
    themePayload,
    themeIdeasPayload,
    themeRevisionPayload,
    textConnectionPayload,
    copyToStoryPayload,
    imageConnectionPayload,
    imagePayload,
    ttsPreviewPayload,
    improveImagePromptPayload,
    autoPipelinePayload,
    applyTtsProviderDefaults,
    updateTtsProviderVisibility,
  };
}
