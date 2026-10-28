---
name: sensenova-u15
description: Generates and edits images using SenseTime SenseNova U1.5 (日日新) image models: sensenova-u1.5-lite (quality) and sensenova-u1.5-fast (speed). Text-to-image generation and image editing with reference images. Invoke when user mentions 商汤, 日日新, SenseNova, U1.5, or wants image generation via SenseNova.
---

# SenseNova U1.5 — Image Generation & Editing

This skill generates and edits images using SenseTime's [SenseNova](https://platform.sensenova.cn) U1.5 image models via the OpenAI-compatible API at `https://token.sensenova.cn/v1`.

## When to Invoke

- User asks to generate/create an image and mentions "商汤", "日日新", "SenseNova", "sensenova", "U1.5"
- User wants high-quality Chinese-style image creation (U1.5 excels at 中文语义理解与文字渲染)
- User wants to edit/modify an existing image (URL or local file) with a text instruction
- User needs text-heavy posters or infographics (U1.5 强化文字渲染与信息布局)

## Supported Models

| Model | Model ID | Description | Best For |
|-------|----------|-------------|----------|
| SenseNova U1.5 Lite | `sensenova-u1.5-lite` | 新一代图片创作模型，生成与编辑一体 | 质量优先，成图交付（默认） |
| SenseNova U1.5 Fast | `sensenova-u1.5-fast` | 加速版，即时创作，高效修改 | 快速迭代、草稿、批量尝试 |

## Prerequisites

1. **API Key**: Register at [platform.sensenova.cn](https://platform.sensenova.cn), create a `sk-` key in 控制台 → API Keys
2. Set environment variable: `export SENSENOVA_API_KEY="sk-xxxxxx"` or add to `.env`
3. Image generation consumes 积分 (TokenPlan credits)

## Workflow

### Step 1: Analyze Request Type

- **Text-to-Image**: User describes a scene, no input image → plain `image` call
- **Image Editing**: User provides an image (URL or local path) + edit instruction → `image` call with `--images`
- **Multi-image compositing**: Up to 5 reference images; the first is the primary

### Step 2: Optimize Prompt

Pattern: `[Subject] + [Scene] + [Style] + [Lighting] + [Composition] + [Quality]`

- U1.5 has built-in prompt auto-polish (`prompt_extend=true` by default) — a clear, complete description is enough; no need to over-engineer
- For text-heavy posters: quote the exact text to render, e.g. 画面标题为"春日茶会"，字体为书法风格
- For edits: describe the desired final look; explicitly say what to keep (尽量保留未指定修改的主体元素)

Examples:
```
用户: 画一只可爱的柴犬
→ 优化: "一只可爱的柴犬坐在草地上，自然光线，写实摄影风格，高细节"
```
```
用户: 一张中秋海报
→ 优化: "中秋节日海报，画面中央是一轮金色圆月和玉兔剪影，标题文字为"花好月圆"，深蓝夜空背景，国风插画风格，高级质感"
```
```
用户: 把这张照片背景换成海滩 (提供图片)
→ 优化: "将背景替换为金色沙滩与日落海景，保持人物面部特征与姿态不变，光线与人物协调"
```

### Step 3: Select Model

| Use Case | Model | Rationale |
|----------|-------|-----------|
| Final deliverable / quality-critical | `sensenova-u1.5-lite` | Better detail, composition, texture |
| Quick drafts / iteration | `sensenova-u1.5-fast` | Faster response, easy to retry |
| Image editing | either | Both support the same edits endpoint |

### Step 4: Generate Image

> In all commands below, `<skill-dir>` is the absolute path of **this skill's directory** (`sensenova-u15`). Derive it from the SKILL.md path listed in the Available Skills index of the system prompt (strip the trailing `/SKILL.md`).

**Text-to-Image (default 2K square, no watermark):**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "OPTIMIZED_PROMPT"
```

**With aspect ratio preset (2K tier):**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "OPTIMIZED_PROMPT" \
  --ratio 9:16
```

**With explicit size (WxH, multiples of 32):**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "OPTIMIZED_PROMPT" \
  --size 2720x1536
```

**Fast model for drafts:**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "OPTIMIZED_PROMPT" \
  --model sensenova-u1.5-fast
```

**Custom output location:**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "OPTIMIZED_PROMPT" \
  --output-dir ./outputs --filename "poster.png"
```

### Step 5: Edit an Existing Image

**Local file (auto-converted to base64 data URL):**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "背景换成一望无际的冰川" \
  --images ./photo.png
```

**Public URL:**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "改成水彩画风格，柔和的蓝色调" \
  --images "https://example.com/photo.png"
```

**Multiple reference images (max 5, first = primary):**
```bash
uv run <skill-dir>/scripts/sensenova_generate.py image \
  --prompt "参考图二的服装风格重绘图一的人物" \
  --images ./person.png ./outfit.png
```

Edit mode defaults `size=auto` (auto-adapts to the primary image).

### Step 6: Return Result

The script outputs JSON with `local_path`:

```json
{
  "local_path": "/tmp/sensenova_1758168000.png",
  "model": "sensenova-u1.5-lite",
  "size": "2048x2048",
  "usage": {"input_tokens": 1540, "output_tokens": 4096, "total_tokens": 5636, "images_count": 1}
}
```

Report the saved local path to the user.

## Technical Specifications

### Size Rules

- `WIDTHxHEIGHT`: both must be **multiples of 32**, range **512–4096**, max ratio **3:1 / 1:3**
- Constants: `auto` (API decides), `2K` (=2048x2048), `4K` (=4096x4096)
- Script auto-corrects invalid WxH values to the nearest valid size

### Recommended Resolutions (2K tier)

| Size | Ratio | Use Case |
|------|-------|----------|
| `2048x2048` | 1:1 | Default, general purpose |
| `2720x1536` | 16:9 | Landscapes, widescreen, video covers |
| `1536x2720` | 9:16 | Portraits, mobile wallpapers, 小红书 |
| `1664x2496` | 2:3 | Posters, book covers |
| `2496x1664` | 3:2 | Photography style |
| `4096x4096` | 1:1 | 4K square, max detail |

### Quality Markers / Styles (work well with U1.5)

- **Photorealistic**: 写实摄影，真实光影，高细节纹理
- **Chinese ink wash**: 水墨画风格，写意山水，留白
- **Guofeng**: 国风，古风，工笔画，丹青
- **Anime**: 动漫风格，赛璐璐着色，新海诚风格
- **Oil painting**: 油画风格，厚重笔触，帆布纹理
- **3D Render**: 3D渲染，C4D，Blender材质
- **Lighting**: 黄金时刻，柔光箱，电影级布光，逆光轮廓光
- **Composition**: 特写/中景/远景，俯视/仰视，三分法，对称构图

## Parameter Reference

| Argument | Alias | Default | Description |
|----------|-------|---------|-------------|
| `--prompt` | `-p` | (required) | Image description / edit instruction |
| `--model` | `-m` | `sensenova-u1.5-lite` | `sensenova-u1.5-lite` or `sensenova-u1.5-fast` |
| `--size` | `-s` | `2048x2048` | `auto` / `2K` / `4K` / `WIDTHxHEIGHT`; edit mode defaults `auto` |
| `--ratio` | `-r` | none | Preset ratio (1:1, 16:9, 9:16, 2:3, 3:2) at 2K tier; overrides `--size` |
| `--images` | `-i` | none | Reference image(s): URL or local path, max 5 → switches to edit mode |
| `--output-format` | - | `png` | `png` / `jpeg` / `webp` |
| `--response-format` | - | `b64_json` | `b64_json` (reliable) or `url` (24h link, auto-downloaded) |
| `--watermark` | - | off | Add SenseNova logo watermark (off = clean image, free in beta) |
| `--no-extend` | - | off | Disable prompt auto-polish |
| `--output-dir` | `-o` | `/tmp` | Save directory |
| `--filename` | `-f` | auto | Output filename (auto-creates subdirs) |
| `--no-save` | - | off | Don't download, only return URL |

## Important Constraints

1. **Standalone image API**: `/v1/images/generations` and `/v1/images/edits` — NOT Chat Completions. Generation does not accept image input; editing requires at least one image.
2. **URL expiry**: `response_format=url` links expire after **24 hours** — always download locally (script does this automatically; default `b64_json` avoids the issue entirely).
3. **n = 1 only**: Each request generates exactly one image.
4. **Watermark**: API default is `watermark=true`; this skill defaults to `false` (free during public beta). Pass `--watermark` if the official logo is wanted.
5. **Edit input formats**: public URL (http/https) or complete Data URL `data:image/{format};base64,{data}` — bare base64 strings are rejected. Local files are converted automatically.
6. **Prompt polish**: `prompt_extend=true` by default (auto-expands the prompt; falls back to the original on failure).

## API Configuration

### Way 1: `.env` file (recommended)

Add to the project `.env` (scripts auto-detect it by searching upward from the current directory):

```bash
SENSENOVA_API_KEY=sk-xxxxxxxxxx
```

### Way 2: Environment variable

```bash
export SENSENOVA_API_KEY="sk-xxxxxxxxxx"
```

## Endpoints

| Mode | Endpoint |
|------|----------|
| Text-to-Image | `POST https://token.sensenova.cn/v1/images/generations` |
| Image Editing | `POST https://token.sensenova.cn/v1/images/edits` |

Auth header: `Authorization: Bearer $SENSENOVA_API_KEY`

## Example Interactions

**Text-to-Image:**
```
User: 用商汤的模型画一只白色毛绒绒的海豹宝宝
→ Category: Text-to-Image
→ Optimize: "一只白色毛绒绒的海豹宝宝漂浮在平静海面上，柔和晨光，写实摄影风格，高细节"
→ Run: uv run scripts/sensenova_generate.py image --prompt "一只白色毛绒绒的海豹宝宝漂浮在平静海面上，柔和晨光，写实摄影风格，高细节"
```

**Poster with text:**
```
User: 做一张"春日茶会"的竖版海报
→ Category: Text-to-Image
→ Optimize: "春日茶会海报，竖版构图，粉色樱花与青瓷茶具，标题文字"春日茶会"用书法字体，底部小字"四月八日 · 南山小院"，柔和春日光线，国风插画风格"
→ Run: uv run scripts/sensenova_generate.py image --prompt "..." --ratio 2:3
```

**Image Editing (local file):**
```
User: 把这张照片的背景换成冰川
→ Category: Image Editing
→ Optimize: "将背景替换为一望无际的冰川与冰蓝色湖面，保持主体人物不变，光线协调"
→ Run: uv run scripts/sensenova_generate.py image --prompt "将背景替换为..." --images ./photo.png
```

## Resources

- [references/api_reference.md](references/api_reference.md) — 完整 API 参考文档（参数表、响应结构、限制）
- [references/style-guide.md](references/style-guide.md) — 风格/构图/光线/色彩词汇与中文场景模板（生成与编辑通用，按需取用）

## Notes

- U1.5 的核心优势：生成与编辑统一链路、参考图创作、中文文字渲染能力强
- Chinese and English prompts both work; Chinese prompts are first-class
- Images consume TokenPlan credits; 4K costs more than 2K
- The API is OpenAI-compatible — you can also use the `openai` Python SDK with `base_url="https://token.sensenova.cn/v1"`
