# 人生副本

一个最小可跑通的 AI 短视频工作台，用于把主题拆成分镜脚本，并生成配音、字幕和竖屏 MP4。

项目不绑定具体模型服务、不内置商业生图能力，只提供：

- OpenAI-compatible 文本接口
- OpenAI-compatible 图片接口
- 可选 Gemini WebAPI 文本/图片接口
- 可编辑 Story JSON
- 本地占位分镜渲染
- Edge TTS 配音
- SRT/ASS 字幕
- FFmpeg 合成竖屏 MP4

## Quick Start

```bash
cd 人生副本
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

如果要使用可选的 Gemini WebAPI 适配：

```bash
pip install -r requirements-gemini.txt
```

这部分能力基于开源项目 [HanaokaYuzu/Gemini-API](https://github.com/HanaokaYuzu/Gemini-API)。它需要用户自行提供 Gemini 网页 Cookie，属于可选实验适配；不要把 Cookie、API Key 或 `.env` 文件提交到公开仓库。

## 本机 Gemini 配置

后端启动时会自动读取项目根目录下的 `.env`。如果你想默认使用 Gemini WebAPI，可以这样配置：

```text
TEXT_PROVIDER=gemini_webapi
IMAGE_PROVIDER=gemini_webapi
GEMINI_SECURE_1PSID=your-browser-cookie
GEMINI_SECURE_1PSIDTS=your-browser-cookie
```

`GEMINI_SECURE_1PSIDTS` 有些账号可能没有，留空也可以先试。Cookie 需要从你已经登录 Gemini 的浏览器里复制，填好后重新启动服务。

## 固定提示词

文本生成固定提示词：

```text
prompts/story_shots.md
```

图片生成固定提示词：

```text
prompts/image_style.md
```

工作台调用接口时会自动拼接固定提示词。你可以直接改这两个文件来改变风格和输出 schema。

## 文本接口

后端调用标准 OpenAI-compatible endpoint：

```text
POST {LLM_BASE_URL}/v1/chat/completions
Authorization: Bearer {LLM_API_KEY}
```

你可以在网页里填写：

- Base URL
- Model
- API Key

也可以复制 `.env.example` 为 `.env` 后填写本地配置。后端启动时会自动读取项目根目录下的 `.env`。

### 可选 Gemini WebAPI 文本

选择 `Gemini WebAPI` 时，不使用 `Base URL / API Key`，而是使用 Gemini 网页 Cookie：

```text
__Secure-1PSID
__Secure-1PSIDTS
```

这一路径调用的是 `gemini_webapi.GeminiClient.generate_content()`。请只在本地环境填写这些值，不要写入示例文件、截图或 Issue。

## 图片接口

### OpenAI-compatible Images

后端调用：

```text
POST {IMAGE_BASE_URL}/v1/images/generations
Authorization: Bearer {IMAGE_API_KEY}
```

支持响应里的：

- `data[0].url`
- `data[0].b64_json`

### 可选 Gemini WebAPI 图片

选择 `Gemini WebAPI` 时，同样使用 Gemini 网页 Cookie。后端会调用 `generate_content()`，并保存返回的第一张图片。

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

`image_path` 和 `image_url` 是可选字段。为空时工作台会绘制占位分镜；接入生图服务时，后端会把生成后的本地路径和浏览器可访问 URL 写回每个 shot。

## API

```text
GET  /api/example
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

## Roadmap

- 接入异步任务队列
- 增加更多图片服务 adapter
- 增加视频服务 adapter
- 增加剪映/CapCut 草稿导出
- 增加项目保存/恢复

## 开源说明

本仓库只应包含源码、提示词、示例 JSON 和文档。请不要提交本地生成的 `outputs/`、`workspace/`、缓存文件、打包程序、第三方二进制目录或任何私有凭据。

## License

MIT
