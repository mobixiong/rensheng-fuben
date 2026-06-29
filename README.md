# 人生副本工作台

一个本地 AI 短视频工作台，用于把“人生副本”主题拆成分镜脚本，再生成图片、配音、字幕和竖屏 MP4。

项目不绑定具体模型服务，不内置商业生图能力，只提供可替换的接口层。

## Features

- 口播文案生成：OpenAI-compatible API
- 文案生成：可选 [Sophomoresty/gemini-web2api](https://github.com/Sophomoresty/gemini-web2api)
- 图片生成：OpenAI-compatible Images API
- 可编辑文案提示词：默认读取 `prompt.txt`
- 可编辑图片提示词：默认读取 `prompts/image_style.md`
- 可编辑分镜 JSON：默认示例读取 `examples/buffet_story.json`
- 分镜 JSON 生成：默认读取 `prompts/story_shots.md`
- 可编辑 Story JSON
- 图片批量生成和单张重抽
- Edge TTS 配音
- SRT/ASS 字幕
- FFmpeg 合成竖屏 MP4

## Quick Start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 7860
```

打开：

```text
http://127.0.0.1:7860
```

## Requirements

- Python 3.10+
- FFmpeg / FFprobe in PATH
- Python packages in `requirements.txt`

## Text API

普通 OpenAI-compatible 文本接口：

```text
POST {LLM_BASE_URL}/v1/chat/completions
Authorization: Bearer {LLM_API_KEY}
```

网页里填写：

- Provider: `OpenAI-compatible`
- Base URL
- Model
- API Key

也可以复制 `.env.example` 为 `.env` 后填写本地配置。后端启动时会自动读取项目根目录下的 `.env`。

## Prompts

7860 页面里可以直接编辑两类提示词：

- 文案提示词：用于“生成口播”，默认来自 `prompt.txt`。
- 图片提示词：用于“批量生成”和“重抽选中图片”，默认来自 `prompts/image_style.md`。

“生成分镜 JSON”仍然使用 `prompts/story_shots.md`，因为图片和视频流程依赖结构化 Story JSON。

## Gemini Web2API

Gemini 文本走 `gemini-web2api`，它本身提供 OpenAI-compatible API。

先单独启动 `gemini-web2api`：

```bash
pip install httpx
python gemini_web2api.py
```

默认服务地址：

```text
http://127.0.0.1:8081/v1
```

工作台里选择：

```text
Provider: Gemini Web2API
Base URL: http://127.0.0.1:8081/v1
Model: gemini-3.5-flash-thinking
API Key: sk-local
```

`.env` 示例：

```text
TEXT_PROVIDER=gemini_web2api
LLM_BASE_URL=http://127.0.0.1:8081/v1
LLM_MODEL=gemini-3.5-flash-thinking
LLM_API_KEY=sk-local
```

`gemini-web2api` 支持的常用模型包括：

```text
gemini-3.5-flash
gemini-3.5-flash-thinking
gemini-3.5-flash-thinking-lite
gemini-3.1-pro
gemini-auto
gemini-flash-lite
```

## Image API

图片接口目前只保留 OpenAI-compatible Images：

```text
POST {IMAGE_BASE_URL}/v1/images/generations
Authorization: Bearer {IMAGE_API_KEY}
```

支持响应：

- `data[0].url`
- `data[0].b64_json`

生成图片后，工作台会把每个 shot 更新为：

```json
{
  "image_path": "D:\\path\\to\\shot_01.png",
  "image_url": "/workspace/project_id/images/shot_01.png",
  "resolved_image_prompt": "final prompt sent to image model"
}
```

## Story JSON Schema

```json
{
  "title": "自助餐成瘾者回本哥的人生",
  "style_preset": "人生副本视觉风格",
  "shots": [
    {
      "id": 1,
      "voiceover": "今天体验的人生副本是：自助餐成瘾者回本哥的人生。",
      "visual": "他站在自助餐门口，像要参加一场命运审判。",
      "punch": "副本开启",
      "image_prompt": "English image prompt",
      "video_prompt": "English motion prompt",
      "image_path": "optional local image path",
      "image_url": "optional browser-accessible image URL"
    }
  ]
}
```

## API

```text
GET  /api/example
GET  /api/prompt/default
GET  /api/prompt/image
POST /api/text/generate-copy
POST /api/text/generate
POST /api/llm/generate
POST /api/image/generate-story
POST /api/image/regenerate-shot
POST /api/render
```

`/api/render` 会输出到：

```text
workspace/{project_id}/final.mp4
```

## Open Source Notes

不要提交 `.env`、API Key、本地生成的 `workspace/`、音频、字幕、视频或任何私有凭据。

## License

MIT
