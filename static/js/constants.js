export const SETTINGS_KEY = "rensheng-fuben-settings";
export const GEMINI_WEB2API_DEFAULT_BASE_URL = "http://127.0.0.1:8081/v1";
export const GEMINI_WEB2API_DEFAULT_MODEL = "gemini-3.5-flash-thinking";
export const MINIMAX_TTS_DEFAULT_BASE_URL = "https://api.minimaxi.com/v1/t2a_v2";
export const MINIMAX_TTS_DEFAULT_MODEL = "speech-2.8-hd";
export const MINIMAX_TTS_DEFAULT_VOICE_ID = "male-qn-qingse";
export const PROJECT_SAVE_DELAY_MS = 1600;
export const PROJECT_PROGRESS_SAVE_INTERVAL_MS = 2000;
export const IMAGE_RETRY_LIMIT = 2;
export const IMAGE_CONCURRENCY_LIMIT = 100;

export const COPY_PROMPT_VERSION = 3;
export const COPY_TO_STORY_PROMPT_VERSION = 3;

export const COPY_PROMPT_PRESETS = ["reality", "xianxia"];
export const IMAGE_SIZES = ["9:16", "1:1", "16:9"];
export const INTRO_TEMPLATES = [
  "none",
  "life_copy_fast_cut",
  "life_copy_expand_cut",
  "life_copy_flash_horizontal",
  "life_copy_flash_vertical",
  "life_copy_staggered_mask",
];

export const DEFAULT_COPY_PROMPT_PRESET = "reality";
export const DEFAULT_IMAGE_SIZE = "9:16";
export const DEFAULT_INTRO_TEMPLATE = "life_copy_fast_cut";

export const IMAGE_STATUS = {
  pending: "pending",
  generating: "generating",
  redrawing: "redrawing",
  retrying: "retrying",
  done: "done",
  error: "error",
  policyError: "policy_error",
};

export const IMAGE_TRANSIENT_STATUSES = [
  IMAGE_STATUS.generating,
  IMAGE_STATUS.redrawing,
  IMAGE_STATUS.retrying,
];
