from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any


AUTO_ACTIVE_STATUSES = {"queued", "running", "waiting_child_job"}

RENDER_STALL_SECONDS = 30 * 60

_RENDER_STALL_MSG = "渲染任务长时间无进展，疑似后台渲染已停止，请重试"

STEP_KEYS = [
    ("theme_ideas", "生成选题方向"),
    ("select_idea", "选择方向"),
    ("theme", "生成主题"),
    ("copy", "生成口播"),
    ("storyboard", "拆分镜"),
    ("improve_prompts", "优化图片提示词"),
    ("images", "生成图片"),
    ("cover", "选择封面"),
    ("render", "渲染视频"),
]

_runner = ThreadPoolExecutor(max_workers=2)

_lock = threading.RLock()

_cancelled: set[str] = set()

_runtime_secrets: dict[str, dict[str, Any]] = {}

_ACTIVE_AUTO_IDS: set[str] = set()

IMAGE_REPAIR_SINGLE_RETRY_SIZE = 1

IMAGE_REPAIR_BURST_SIZE = 9

IMAGE_REPAIR_INFINITE_BURST_SIZE = 4

COPY_PROMPT_PRESETS = (
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
)

COPY_PRESET_THEME_PROFILES: dict[str, dict[str, str]] = {
    "reality_reverse": {
        "label": "现实反转压迫型",
        "domain": "现实职业、家庭关系、县城/城市生活、平台规则、收入成本和人际压力",
        "direction": "主题要从期待、短暂回报，逐步走向规则压迫、账目窒息和无尽循环。",
        "examples": "外卖骑手、县城宝妈、北漂程序员、房产中介、网约车司机、工厂夜班工。",
        "avoid": "不要出现修仙、武侠、丧尸、异世界、赛博朋克、规则怪谈等超现实设定。",
    },
    "reality_breakout": {
        "label": "现实理智破局型",
        "domain": "现实职场、婚姻家庭、平台经济、生意合作、利益博弈和证据筹码",
        "direction": "主题要适合写主角隐忍计算、暗中积累筹码、理智清算并完成跃迁。",
        "examples": "被抢功劳的销售、被亲戚吸血的小老板、被平台压价的主播、被合伙人算计的创业者。",
        "avoid": "不要写成无脑复仇、突然暴富、天降贵人或超现实世界观。",
    },
    "reality_stop_loss": {
        "label": "现实止损型",
        "domain": "现实高压赛道、消费升级、债务杠杆、城市体面、健康透支和主动退出",
        "direction": "主题要适合写主角通过生命账单核算，看清隐性成本后主动降杠杆、断舍离。",
        "examples": "月薪三万却被车房榨干的白领、硬撑体面的城市中产、过度扩张的小店老板。",
        "avoid": "不要写成田园牧歌、鸡汤治愈、逆袭爽文或超现实题材。",
    },
    "reality_burnout_support": {
        "label": "现实燃尽托举型",
        "domain": "现实家庭托举、父母子女、病痛账单、教育开销、房贷压力和长期隐忍",
        "direction": "主题要适合写主角为了软肋主动燃烧自己，用身体和时间填补家人的账单。",
        "examples": "给孩子交学费的中年父亲、给父母治病的打工人、撑起一家人的县城母亲。",
        "avoid": "不要把家人写成纯恶人，不要写成大团圆，不要加入超现实设定。",
    },
    "xianxia": {
        "label": "修仙型",
        "domain": "宗门、散修、灵石债务、丹药成本、秘境名额、功法内卷、天劫和寿元折损",
        "direction": "主题要把修仙世界写成一套可计算的生存系统，围绕修炼资源和阶层压迫展开。",
        "examples": "背负灵石贷的外门弟子、给宗门炼丹还债的散修、被秘境KPI压垮的低阶修士。",
        "avoid": "不要生成纯现实职业题，不要写成无脑龙傲天爽文或突然觉醒无敌血脉。",
    },
    "fantasy_wuxia": {
        "label": "武侠江湖型",
        "domain": "镖局、门派、武馆、江湖客栈、师门债、人情债、兵器折旧和江湖规矩",
        "direction": "主题要适合写江湖外壳下的生存账本，侠义、门规和银钱压力互相撕扯。",
        "examples": "给镖局还债的趟子手、被师门绑住的年轻刀客、靠卖命接单的落魄侠客。",
        "avoid": "不要生成现代职场题，不要写成无成本快意恩仇。",
    },
    "fantasy_zombie": {
        "label": "丧尸末日型",
        "domain": "末日庇护所、感染风险、物资配给、避难名额、巡逻任务、药品和信任崩塌",
        "direction": "主题要围绕资源稀缺和生存代价展开，主角行动必须基于风险收益计算。",
        "examples": "为了换抗感染药出城搜物资的人、被庇护所积分制度压榨的巡逻员、末日里的单亲父亲。",
        "avoid": "不要写血腥细节，不要写成单纯打怪爽文或现实都市题。",
    },
    "fantasy_otherworld": {
        "label": "异世界型",
        "domain": "冒险者公会、魔法药水、装备折旧、系统任务、复活费用、队伍分成和传送门",
        "direction": "主题要把异世界冒险写成高危外包工作，用经济账本拆掉奇幻滤镜。",
        "examples": "签下公会长约的底层冒险者、靠系统续命的穿越者、背负装备贷的新手勇士。",
        "avoid": "不要生成现实职业题，不要打败魔王拯救世界，不要机械降神。",
    },
    "fantasy_cyberpunk": {
        "label": "赛博朋克型",
        "domain": "义体贷款、数据公司、算法评分、黑市维修、脑机接口、城市分层和身份权限",
        "direction": "主题要适合写科技外壳下的债务、监控和身体折旧，保持冷酷现实感。",
        "examples": "背着义体贷的外包黑客、靠记忆出租还债的底层青年、被评分系统锁死的快递员。",
        "avoid": "不要生成古风修仙或纯现实职业题，不要写成无脑科幻爽文。",
    },
    "fantasy_weird_rules": {
        "label": "规则怪谈型",
        "domain": "诡异规则、封闭场域、职位守则、禁忌条款、积分惩罚、信息差和生存选择",
        "direction": "主题要围绕规则理解、试探成本和生存账本展开，恐惧来自制度化约束而不是血腥描写。",
        "examples": "午夜便利店守则实习生、永不熄灯公寓管理员、无限商场导购、规则列车乘务员。",
        "avoid": "不要写血腥猎奇细节，不要生成普通现实职业题，不要把规则写得随机混乱。",
    },
}

class AutoPipelineError(RuntimeError):
    pass

class AutoPipelineCancelled(AutoPipelineError):
    pass

