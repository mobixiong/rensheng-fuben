export const SETTINGS_KEY = "rensheng-fuben-settings";
export const DEFAULT_LLM_BASE_URL = "http://43.131.249.187:3000/v1";
export const DEFAULT_TEXT_MODEL = "gpt-5.5";
export const DEFAULT_IMAGE_MODEL = "gpt-image-2";
export const ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com";
export const ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-5";
export const GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";
export const GEMINI_DEFAULT_MODEL = "gemini-2.0-flash";
export const GEMINI_IMAGE_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";
export const GEMINI_IMAGE_DEFAULT_MODEL = "imagen-3.0-generate-002";
export const MINIMAX_TTS_DEFAULT_BASE_URL = "https://api.minimaxi.com/v1/t2a_v2";
export const MINIMAX_TTS_DEFAULT_MODEL = "speech-2.8-hd";
export const MINIMAX_TTS_DEFAULT_VOICE_ID = "male-qn-qingse";
export const MINIMAX_TTS_MODELS = [
  "speech-2.8-hd",
  "speech-2.8-turbo",
  "speech-2.6-hd",
  "speech-2.6-turbo",
  "speech-02-hd",
  "speech-02-turbo",
  "speech-01-hd",
  "speech-01-turbo",
];
export const DOUBAO_TTS_DEFAULT_BASE_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional";
export const DOUBAO_TTS_DEFAULT_MODEL = "volc.service_type.10029";
export const DOUBAO_TTS_DEFAULT_VOICE_ID = "zh_male_beijingxiaoye_emo_v2_mars_bigtts";
export const DOUBAO_TTS_MODELS = [
  { value: "volc.service_type.10029", label: "volc.service_type.10029 (legacy 1.0)" },
  { value: "seed-tts-2.0", label: "seed-tts-2.0 (2.0)" },
  { value: "seed-tts-1.0", label: "seed-tts-1.0 (1.0)" },
  { value: "seed-tts-1.0-concurr", label: "seed-tts-1.0-concurr (1.0 concurrent)" },
];
export const PROJECT_SAVE_DELAY_MS = 1600;
export const PROJECT_PROGRESS_SAVE_INTERVAL_MS = 2000;
export const IMAGE_RETRY_LIMIT = 2;
export const IMAGE_CONCURRENCY_LIMIT = 100;

export const COPY_PROMPT_VERSION = 8;
export const COPY_TO_STORY_PROMPT_VERSION = 4;
export const IMPROVE_IMAGE_PROMPT_VERSION = 1;
export const THEME_IDEA_PROMPT_VERSION = 1;

export const COPY_PROMPT_PRESETS = [
  "reality_reverse",
  "reality_breakout",
  "reality_stop_loss",
  "reality_burnout_support",
  "xianxia",
  "fantasy_wuxia",
  "fantasy_zombie",
  "fantasy_otherworld",
  "fantasy_cyberpunk",
  "fantasy_weird_rules",
];
export const AUTO_COPY_PROMPT_PRESETS = ["random", ...COPY_PROMPT_PRESETS];
export const COPY_PRESET_THEME_INSTRUCTIONS = {
  reality_reverse: "文案类型：现实反转压迫型。选题必须来自现实职业、家庭关系、县城/城市生活、平台规则、收入成本和人际压力；情绪方向是期待、短暂回报、规则压迫、账目窒息和无尽循环。不要出现修仙、武侠、丧尸、异世界、赛博朋克、规则怪谈等超现实设定。",
  reality_breakout: "文案类型：现实理智破局型。选题必须来自现实职场、婚姻家庭、平台经济、生意合作、利益博弈和证据筹码；适合写主角隐忍计算、暗中积累筹码、理智清算并完成跃迁。不要写成无脑复仇、突然暴富或超现实世界观。",
  reality_stop_loss: "文案类型：现实止损型。选题必须来自现实高压赛道、消费升级、债务杠杆、城市体面、健康透支和主动退出；适合写主角通过生命账单核算后主动降杠杆、断舍离。不要写成鸡汤治愈、逆袭爽文或超现实题材。",
  reality_burnout_support: "文案类型：现实燃尽托举型。选题必须来自现实家庭托举、父母子女、病痛账单、教育开销、房贷压力和长期隐忍；适合写主角为了软肋主动燃烧自己。不要把家人写成纯恶人，不要加入超现实设定。",
  xianxia: "文案类型：修仙型。选题必须来自宗门、散修、灵石债务、丹药成本、秘境名额、功法内卷、天劫和寿元折损；要把修仙世界写成可计算的生存系统。不要生成纯现实职业题或无脑龙傲天爽文。",
  fantasy_wuxia: "文案类型：武侠江湖型。选题必须来自镖局、门派、武馆、江湖客栈、师门债、人情债、兵器折旧和江湖规矩；适合写江湖外壳下的生存账本。不要生成现代职场题或无成本快意恩仇。",
  fantasy_zombie: "文案类型：丧尸末日型。选题必须来自末日庇护所、感染风险、物资配给、避难名额、巡逻任务、药品和信任崩塌；围绕资源稀缺和生存代价展开。不要写血腥细节或现实都市题。",
  fantasy_otherworld: "文案类型：异世界型。选题必须来自冒险者公会、魔法药水、装备折旧、系统任务、复活费用、队伍分成和传送门；把异世界冒险写成高危外包工作。不要生成现实职业题或拯救世界式爽文。",
  fantasy_cyberpunk: "文案类型：赛博朋克型。选题必须来自义体贷款、数据公司、算法评分、黑市维修、脑机接口、城市分层和身份权限；适合写科技外壳下的债务、监控和身体折旧。不要生成古风修仙或纯现实职业题。",
  fantasy_weird_rules: "文案类型：规则怪谈型。选题必须来自诡异规则、封闭场域、职位守则、禁忌条款、积分惩罚、信息差和生存选择；恐惧来自制度化约束而不是血腥描写。不要生成普通现实职业题，不要把规则写得随机混乱。",
};
export const STORYBOARD_GRANULARITIES = ["coarse", "balanced", "fine"];
export const IMAGE_SIZES = ["9:16", "1:1", "16:9"];
export const INTRO_TEMPLATES = [
  "none",
  "life_copy_fast_cut",
  "life_copy_expand_cut",
  "life_copy_flash_horizontal",
  "life_copy_flash_vertical",
  "life_copy_staggered_mask",
  "life_copy_mosaic_collage",
];

export const DEFAULT_COPY_PROMPT_PRESET = "reality_reverse";
export const DEFAULT_AUTO_COPY_PROMPT_PRESET = "random";
export const DEFAULT_STORYBOARD_GRANULARITY = "balanced";
export const DEFAULT_IMAGE_SIZE = "9:16";
export const DEFAULT_INTRO_TEMPLATE = "life_copy_fast_cut";

export const IMAGE_STATUS = {
  pending: "pending",
  done: "done",
  error: "error",
  policyError: "policy_error",
};

export const IMAGE_JOB_STATUS = {
  generating: "generating",
  redrawing: "redrawing",
  retrying: "retrying",
};
