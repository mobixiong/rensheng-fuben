# 全自动流水线落地方案

本文档描述“自动流水线”的可落地实现方案。目标不是把现有手动页面按钮串起来，而是在后端新增可恢复、可观测、可取消的任务系统，自动完成从顶层要求到 MP4 成片的完整流程。

## 1. 目标与输入

自动流水线必须支持两种输入方式：

- 用户完全不输入，直接开始。
- 用户只输入顶层要求，例如 `猎奇`、`温馨`、`猎奇，温馨`、`斗罗大陆世界观`、`现代都市，反转强一点`。

这些输入统一称为 `brief`，它不是最终主题，而是风格、世界观、情绪、题材或禁忌边界的顶层约束。流水线负责把它收敛成明确的“选题方向 -> 主题 -> 主题介绍 -> 口播 -> 分镜 -> 图片 -> 视频”。

## 2. 总体架构

新增后端模块：

```text
app/auto_pipeline_jobs.py
app/routes_auto_pipeline.py
```

前端新增：

```text
static/js/workflow-auto-pipeline.js
```

任务状态落盘：

```text
workspace/projects/{project_id}/jobs/auto_pipeline_{job_id}.json
```

核心原则：

- 后端执行流程，前端只负责创建任务、轮询状态、取消/恢复任务。
- 每一步都必须幂等，恢复任务时优先读取已有产物。
- 每次状态更新都原子写入 JSON 文件。
- 外部接口失败要分类处理，不允许一次失败把已有产物覆盖掉。
- 任务只追加或更新当前项目状态，不直接删除用户已有素材。

## 3. 阶段拆分

建议分 4 个阶段实现，降低风险。

### 阶段 0：任务基础设施

先抽出通用任务工具，避免图片任务、渲染任务、自动流水线各写一套。

建议新增：

```text
app/job_store.py
```

职责：

- `_now_ms()`
- `jobs_dir(project_id)`
- `job_path(project_id, job_id)`
- `read_job(project_id, job_id)`
- `write_job_atomic(project_id, job_id, data)`
- `list_jobs(project_id, prefix, active_only=False)`
- `safe_job_id(prefix)`

同时需要补齐渲染任务持久化。现状 `app/render_service.py` 的渲染 job 状态在内存里，进程重启后 `/api/render/jobs/{job_id}` 会丢失；但 `app/pipeline.py` 已经有 `render_resume.json`，所以改造方向是：

- 渲染 job 状态写入 `workspace/projects/{project_id}/jobs/render_{job_id}.json`。
- `progress_callback` 同时更新落盘 job。
- 进程重启后，如果最终 `final.mp4` 存在，渲染 job 可恢复为 `complete`。
- 如果 `render_resume.json` 显示中间步骤完成但 final 不存在，`resume` 重新调用 `render_story()`，让内部 resume manifest 接上。

### 阶段 1：自动流水线后端

新增 `app/auto_pipeline_jobs.py`，维护一个小型状态机。

任务状态：

```json
{
  "job_id": "auto_20260702_153000_ab12",
  "project_id": "20260702_153000_ab12",
  "status": "queued",
  "current_step": "theme_ideas",
  "created_at": 1782987000000,
  "updated_at": 1782987000000,
  "lease": {
    "owner": "",
    "expires_at": 0
  },
  "input": {
    "brief": "",
    "copy_preset": "reality",
    "image_size": "9:16",
    "intro_template": "life_copy_fast_cut",
    "tts_preset": "male_fast",
    "bgm_id": "none",
    "auto_select": "first",
    "image_retry_limit": 2,
    "policy_rewrite_limit": 1
  },
  "steps": [
    { "key": "theme_ideas", "name": "生成选题方向", "status": "pending", "attempt": 0, "error": "" },
    { "key": "select_idea", "name": "选择方向", "status": "pending", "attempt": 0, "error": "" },
    { "key": "theme", "name": "生成主题", "status": "pending", "attempt": 0, "error": "" },
    { "key": "copy", "name": "生成口播", "status": "pending", "attempt": 0, "error": "" },
    { "key": "storyboard", "name": "拆分镜", "status": "pending", "attempt": 0, "error": "" },
    { "key": "improve_prompts", "name": "优化图片提示词", "status": "pending", "attempt": 0, "error": "" },
    { "key": "images", "name": "生成图片", "status": "pending", "attempt": 0, "error": "" },
    { "key": "cover", "name": "选择封面", "status": "pending", "attempt": 0, "error": "" },
    { "key": "render", "name": "渲染视频", "status": "pending", "attempt": 0, "error": "" }
  ],
  "artifacts": {
    "selected_idea": null,
    "theme_ideas": [],
    "image_job_id": "",
    "render_job_id": ""
  },
  "result": {
    "topic": "",
    "video_url": "",
    "project_url": ""
  },
  "error": ""
}
```

状态枚举：

```text
queued
running
waiting_child_job
complete
failed
cancelled
paused
```

步骤状态：

```text
pending
running
waiting
done
failed
skipped
cancelled
```

### 阶段 2：前端自动流水线页

新增一个顶层 Tab：`自动流水线`。

页面只放必要输入：

```text
方向要求：可为空
文案版本：现实版 / 修仙版
图片比例：9:16 / 16:9 / 1:1
开头模板
TTS 模板
BGM
自动策略：自动优化图片提示词、合规失败自动改写、图片失败自动重试、完成后自动渲染
```

进度区：

```text
当前步骤：生成图片 8/18
生成选题方向：已完成
选择方向：已完成
生成主题：已完成
生成口播：已完成
拆分镜：已完成
优化图片提示词：已完成
生成图片：进行中
选择封面：等待
渲染视频：等待
```

前端不拼流程，只轮询：

```text
POST /api/auto-pipeline/jobs
GET  /api/auto-pipeline/jobs/{project_id}/{job_id}
```

### 阶段 3：恢复与守护

进程启动时可以先不自动恢复所有任务，避免误跑。第一版提供手动恢复：

```text
POST /api/auto-pipeline/jobs/{project_id}/{job_id}/resume
```

后续再加自动恢复策略：

- 只恢复 `status in ["running", "waiting_child_job"]` 且 `updated_at` 超过 60 秒未更新的任务。
- 恢复前检查 lease 是否过期。
- 同一 job 同一时间只允许一个 worker 持有 lease。

## 4. 步骤设计

### 4.1 生成选题方向

函数：

```text
run_theme_ideas(job)
```

输入：

- `job.input.brief`，允许为空。
- `prompts/theme_ideas.md` 或用户在设置里保存的选题方向提示词。

幂等规则：

- 如果 `artifacts.theme_ideas` 非空，跳过。
- 如果项目 state 中已有可用 `theme_brief`，可以直接作为候选方向。

失败处理：

- LLM 网络错误：重试 2 次，指数退避 2s/5s。
- JSON 解析失败：重试 1 次，并在 user content 里附加“上次输出不是合法 JSON”。
- 仍失败则 job `failed`，保留错误信息。

### 4.2 自动选择方向

第一版：

- 默认选择 `theme_ideas[0]`。

后续可升级：

- 调用 LLM 对候选做评分，维度为冲突强度、可视化程度、审核风险、短视频吸引力。

幂等规则：

- 如果 `artifacts.selected_idea` 已存在，跳过。
- 如果 `state.theme_brief` 已有值，且任务是恢复状态，可以使用该值。

### 4.3 生成主题和主题介绍

复用：

```text
generate_topic_plan()
```

幂等规则：

- 如果项目 state 已有 `topic` 和 `theme_intro`，跳过。
- 写入 `state.topic`、`state.theme_intro`，并保存项目。

稳定性要求：

- 主题生成成功后必须立刻写盘，不等后续步骤。
- 不允许后续失败覆盖已有主题。

### 4.4 生成口播文案

复用：

```text
generate_text()
```

输入：

- `topic`
- `theme_intro`
- 文案提示词版本：现实版 / 修仙版

幂等规则：

- 如果 `state.copy_text` 非空，跳过。
- 生成后写入 `copy.txt` 和 `state.copy_text`。

健壮性要求：

- 文案为空、过短或明显不是口播文本时判定失败。
- LLM 返回 Markdown 或多余解释时先不强行清洗，保留原文给拆分镜步骤处理；只有空文本才失败。

### 4.5 拆分镜

复用：

```text
generate_story_from_copy()
```

幂等规则：

- 如果 `state.story.shots` 是非空数组且每个 shot 有 `voiceover`，跳过。
- 拆分成功后写入 `story.json` 和 `state.story`。

校验规则：

- shots 数量必须在合理范围内，建议 6 到 40。
- 每个 shot 必须有 `voiceover`。
- 每个 shot 必须有 `image_prompt`，没有则降级用 `visual` 或 `voiceover` 生成一条。
- 自动补齐 `image_size`。

失败处理：

- JSON 解析失败重试 1 次。
- 校验失败时把校验错误附加给 LLM 再重试 1 次。

### 4.6 AI 优化图片提示词

复用：

```text
improve_image_prompt()
```

执行策略：

- 对每个 shot 都跑一次优化。
- 并发限制建议 3 到 5，不要和图片生成共用高并发。
- 单条失败不立刻终止，标记该 shot 的 `_image_prompt_status = "error"`，继续处理其他 shot。

幂等规则：

- 如果 shot 有 `_image_prompt_auto_optimized_at` 且 `image_prompt` 非空，跳过。
- 如果用户手动编辑过，可加 `_image_prompt_edited_at`，默认不覆盖用户手动编辑内容。

稳定性要求：

- 每优化成功一条就保存项目。
- 不能等所有优化完成再写盘。

### 4.7 生成图片

复用现有：

```text
create_image_job()
get_image_job()
```

自动流水线步骤进入 `waiting_child_job`：

- 创建图片 job 后，把 `image_job_id` 写入 `artifacts.image_job_id`。
- 自动流水线 worker 轮询图片 job，或每次被查询/恢复时检查图片 job 状态。

幂等规则：

- 如果所有 shot 都有 `image_url` 或 `image_path`，跳过。
- 如果已有 active image job，继续等待，不重复创建。
- 如果 `image_job_id` 指向的 job 已完成，读取项目 state 继续。

合规失败策略：

- 如果某张图失败且 `error_category == "prompt_policy"`：
  1. 对该 shot 再跑一次 `improve_image_prompt()`，要求降低敏感表达。
  2. 清除该 shot 的图片错误状态。
  3. 创建单张 redraw 图片 job。
  4. 每张图最多执行 `policy_rewrite_limit` 次。

失败阈值：

- 图片失败率 `<= 20%`：允许进入渲染，失败图用占位图或现有图兜底。
- 图片失败率 `> 20%`：流水线失败，提示用户检查提示词和模型审核。
- 如果总镜头数很少，至少允许 1 张失败兜底。

并发限制：

- 仍然使用 `IMAGE_CONCURRENCY_LIMIT`，但后端硬上限保持 12。
- 不建议让自动流水线绕过图片 job 的并发控制。

### 4.8 自动选择封面

第一版：

- 选择第一张成功生成的分镜图。
- 写入：

```json
{
  "source_shot_index": 0,
  "image_path": "...",
  "image_url": "...",
  "_cover_status": "selected"
}
```

幂等规则：

- 如果 `story.cover.image_url` 已存在，跳过。
- 如果第一张失败，选择第一张成功图。

### 4.9 渲染视频

复用：

```text
render_story()
```

建议先改造 `render_service.py`，让 render job 也落盘。自动流水线不要直接同步调用长时间渲染，避免占住 worker 且难以恢复。

执行策略：

- 创建 render job。
- 写入 `artifacts.render_job_id`。
- 流水线进入 `waiting_child_job`。
- 轮询 render job 完成后写入 `state.rendered_video`、`result.video_url`。

幂等规则：

- 如果项目目录下已有可用 `final.mp4`，直接标记 render done。
- 如果 render job 丢失但 `render_resume.json` 存在，重新创建 render job。

## 5. 稳定性设计

### 5.1 原子写盘

所有 job JSON 写入都必须走临时文件替换：

```text
auto_pipeline_xxx.json.tmp -> auto_pipeline_xxx.json
```

避免进程中断导致 JSON 半截损坏。

### 5.2 Lease 防重入

任务执行前获取 lease：

```json
{
  "owner": "pid-host-thread",
  "expires_at": 1782987060000
}
```

规则：

- lease 未过期时，其他 worker 不得执行。
- worker 每个步骤开始和结束都刷新 lease。
- 进程崩溃后 lease 超时，resume 可以接手。

### 5.3 幂等检查

每一步开始前都先读项目 state 和文件系统，判断是否已有产物。

检查顺序：

1. 项目 state
2. 文件系统产物
3. 子任务 job 状态
4. 当前步骤状态

只信任 step status 不够，因为 status 可能写盘了但产物没写完，或者产物写完后 status 没更新。

### 5.4 失败隔离

文本步骤失败：中止流水线。

图片单项失败：不立刻中止，按失败阈值判断。

渲染失败：中止流水线，但保留前面所有素材，允许修配置后 resume。

取消任务：不删除已生成素材，只停止后续步骤。

### 5.5 重试策略

建议默认：

```text
LLM 网络错误：2 次
LLM JSON 错误：1 次
图片普通错误：2 次
图片 prompt_policy：改写提示词后 1 次
TTS 网络错误：沿用现有 TTS 重试
FFmpeg 错误：不自动重试，直接失败
```

退避：

```text
2s -> 5s -> 10s
```

不要对 quota/rate limit 做高频重试，应该失败并提示降并发或换 key。

### 5.6 进度与可观测性

job JSON 里保留：

- `current_step`
- `progress`
- `detail`
- `steps[].attempt`
- `steps[].error`
- 子任务 id：`image_job_id`、`render_job_id`
- 最近一次异常 `error`

前端展示：

- 当前步骤
- 子任务进度，例如图片 `8/18`
- 最近错误
- 最终主题、项目链接、视频链接

## 6. API 设计

### 创建任务

```text
POST /api/auto-pipeline/jobs
```

请求：

```json
{
  "brief": "猎奇，温馨",
  "copy_preset": "reality",
  "image_size": "9:16",
  "intro_template": "life_copy_fast_cut",
  "intro_image_seconds": 0.3,
  "tts_preset": "male_fast",
  "bgm_id": "none",
  "intro_sfx_id": "default",
  "auto_optimize_image_prompts": true,
  "auto_rewrite_policy_prompt": true,
  "render_after_images": true,
  "text_config": {
    "provider": "gemini_web2api",
    "base_url": "http://127.0.0.1:8081/v1",
    "model": "gemini-3.5-flash-thinking",
    "api_key": "sk-local"
  },
  "image_config": {
    "provider": "openai",
    "base_url": "",
    "model": "",
    "api_key": ""
  },
  "tts_config": {}
}
```

响应：

```json
{
  "job": {}
}
```

### 查询任务

```text
GET /api/auto-pipeline/jobs/{project_id}/{job_id}
```

返回当前 job JSON 的公开字段。敏感字段如 API key 必须剔除。

### 取消任务

```text
POST /api/auto-pipeline/jobs/{project_id}/{job_id}/cancel
```

行为：

- 标记 auto job 为 `cancelled`。
- 如果有 active image job，调用 `cancel_image_job()`。
- 如果有 active render job，第一版可只标记取消，不强杀 ffmpeg；后续再补 render cancel。

### 恢复任务

```text
POST /api/auto-pipeline/jobs/{project_id}/{job_id}/resume
```

行为：

- 检查 lease。
- 从当前 state 和产物判断下一步。
- 重新提交 worker。

## 7. 前端设计

新增 Tab：`自动流水线`。

布局：

```text
左侧：输入和配置
右侧：任务状态和结果
```

输入区：

- 方向要求 textarea，可为空。
- 文案版本 select。
- 图片比例 select。
- 开头模板 select。
- TTS 模板 select。
- BGM select。
- 策略 checkbox。

状态区：

- 总状态：等待/运行/失败/完成/取消。
- 当前步骤。
- 步骤列表。
- 图片进度。
- 渲染进度。
- 错误详情。
- 完成后按钮：打开项目、播放视频。

前端轮询：

```text
running/waiting_child_job: 2s
failed/complete/cancelled: 停止轮询
```

刷新页面后：

- 读取当前项目 active auto job。
- 如果存在未完成任务，自动恢复状态展示，但不自动 resume。

## 8. 数据安全与敏感信息

job 文件不能保存明文 API key。

第一版建议：

- 创建任务时 API key 只存在内存 payload，用于当前 worker。
- job JSON 只保存 provider/base_url/model，不保存 key。
- 如果进程重启后 resume，需要前端再次提交当前设置里的 key，或使用环境变量。

如果需要无人值守恢复：

- 优先使用 `.env` 中的服务配置。
- 不建议把用户在页面输入的 key 明文写入项目文件。

## 9. 测试计划

单元测试：

- job JSON 原子写入和读取。
- step 状态转换。
- 空 brief 创建任务。
- 顶层 brief 透传到选题方向生成。
- 已有产物时跳过步骤。
- policy_error 触发提示词改写。

集成测试：

- mock LLM + mock image + mock render，跑完整自动流水线。
- 中途终止进程，重新 resume，确认不重复生成已完成步骤。
- 图片部分失败，低于阈值时继续渲染。
- 图片失败超过阈值时任务失败。
- 取消任务后不再创建新子任务。

手工 smoke：

```text
1. brief 为空，跑完整流程
2. brief = 猎奇，温馨
3. brief = 斗罗大陆世界观
4. 图片接口故意返回 prompt_policy
5. 渲染中断后 resume
```

## 10. 实施顺序

推荐按以下顺序写代码：

1. 抽 `job_store.py`，复用原子写盘。
2. 改造 render job 落盘。
3. 新增 `auto_pipeline_jobs.py` 的 job 创建、读取、取消、恢复。
4. 实现文本步骤：选题方向、选择方向、主题、口播、拆分镜。
5. 实现图片提示词优化和图片子任务等待。
6. 实现封面选择。
7. 接入 render job。
8. 新增前端 `自动流水线` Tab。
9. 加 smoke 脚本和 mock 测试。

第一版完成标准：

- 用户不输入也能跑完整流程。
- 用户输入顶层要求能影响候选方向和主题。
- 刷新页面不影响任务状态展示。
- 服务重启后可以手动 resume。
- 图片失败和合规失败有明确状态。
- 最终视频能回填到项目。
