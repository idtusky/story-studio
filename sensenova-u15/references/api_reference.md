# SenseNova U1.5 API Reference

> Source: https://platform.sensenova.cn/docs (模型 → SenseNova U1.5 Lite / U1.5 Fast)

## Base Config

| Item | Value |
|------|-------|
| Base URL | `https://token.sensenova.cn/v1` |
| Auth | `Authorization: Bearer $SENSENOVA_API_KEY` |
| Protocol | OpenAI Compatible |
| Key Format | `sk-xxxxxxxxxx` |
| Key Platform | https://platform.sensenova.cn → 控制台 → API Keys |

## Models

| Model | Model ID | Description |
|-------|----------|-------------|
| SenseNova U1.5 Lite | `sensenova-u1.5-lite` | 新一代图片创作模型，基于 Neo-unify 架构，生成与编辑一体，支持参考图功能及灵活修改 |
| SenseNova U1.5 Fast | `sensenova-u1.5-fast` | 加速版，即时创作，高效修改，强化文字渲染与信息布局 |

---

## Text-to-Image

### Endpoint

```
POST /v1/images/generations
```

仅输入文本 prompt 生成图片，不支持图像输入。

### Request Example

```json
{
  "model": "sensenova-u1.5-lite",
  "prompt": "一只白色毛绒绒的海豹宝宝漂浮在平静海面上，柔和晨光，写实摄影风格",
  "n": 1,
  "size": "1024x1024",
  "output_format": "png",
  "response_format": "url",
  "watermark": true
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | string | ✅ | — | `sensenova-u1.5-lite` / `sensenova-u1.5-fast` |
| `prompt` | string | ✅ | — | 图像生成描述 |
| `size` | string | — | `auto` | `auto` / `2K` / `4K` 常量，或 `WIDTHxHEIGHT`（32 的倍数，512–4096，最大比例 3:1 或 1:3） |
| `n` | integer | — | 1 | 生成图片数量，仅支持 1 |
| `watermark` | boolean | — | `true` | 是否添加日日新官方 Logo 水印；`false` 公测期间免费 |
| `response_format` | string | — | `b64_json` | `b64_json`（返回 Base64）或 `url`（24 小时有效期临时下载地址）；二者不同时返回 |
| `output_format` | string | — | `png` | `png` / `jpeg` / `webp`；不控制 Base64 还是 URL 返回 |
| `prompt_extend` | boolean | — | `true` | 提示词自动润色优化开关，扩写失败时自动使用原始 prompt |

### Recommended Resolutions

| Size | Ratio | Tier |
|------|-------|------|
| 2048x2048 | 1:1 | 2K |
| 2720x1536 | 16:9 | 2K |
| 1536x2720 | 9:16 | 2K |
| 1664x2496 | 2:3 | 2K |
| 2496x1664 | 3:2 | 2K |
| 4096x4096 | 1:1 | 4K |

### Response

```json
{
  "created": 1788849614,
  "data": [
    { "url": "https://cdn.sensenova.dev/gen/..." }
  ],
  "output_format": "png",
  "size": "1024x1024",
  "usage": {
    "input_tokens": 1540,
    "input_tokens_details": { "image_tokens": 0, "text_tokens": 1540 },
    "output_tokens": 4096,
    "total_tokens": 5636,
    "images_count": 1
  }
}
```

`data[]` 内为 `{ "url": ... }` 或 `{ "b64_json": ... }`，取决于 `response_format`。

---

## Image Editing (img2img)

### Endpoint

```
POST /v1/images/edits
```

输入参考图片 + 编辑提示词，完成图生图 / 图片改写。必须传入至少一张图片。

### Request Example

```json
{
  "model": "sensenova-u1.5-lite",
  "images": [
    { "image_url": "https://www.sensenova.cn/images/little-seal.png" }
  ],
  "prompt": "背景换成在一望无际的冰川上",
  "watermark": true,
  "prompt_extend": true,
  "size": "auto",
  "response_format": "url"
}
```

### Parameters

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `model` | string | ✅ | — | `sensenova-u1.5-lite` / `sensenova-u1.5-fast` |
| `images` | array | ✅ | — | 图片对象数组，每项含 `image_url`；第 1 张为主编辑图；至多 5 张参考图 |
| `images[].image_url` | string | ✅ | — | 公网 URL 或完整 Data URL `data:image/{format};base64,{data}`（不支持纯 Base64 字符串） |
| `prompt` | string | ✅ | — | 编辑指令，描述期望最终画面；尽量保留未指定修改的主体元素 |
| `size` | string | — | `auto` | 同生成接口；`auto` 自动适配主图 |
| `n` | integer | — | 1 | 仅支持 1 |
| `watermark` | boolean | — | `true` | 同生成接口 |
| `response_format` | string | — | `b64_json` | 同生成接口 |
| `output_format` | string | — | `png` | `png` / `jpg` / `jpeg` / `webp` |
| `prompt_extend` | boolean | — | `true` | 同生成接口 |

### Response

同生成接口。编辑请求的 `usage.input_tokens_details.image_tokens` 反映参考图消耗（如 8192）。

---

## Usage Limits

1. 使用独立的图像生成/编辑接口，**不是 Chat Completions**
2. `response_format=url` 的链接为临时地址，**有效期固定 24 小时**，超时失效
3. 文生图接口不支持图像输入；图片编辑接口必须传入至少一张图片
4. `n` 仅支持 1
5. 无水印生成（`watermark=false`）当前免费公测，后续将转为付费功能；建议调用时显式传入 `watermark` 参数
6. 图片输入格式校验严格：链接无法访问、非有效图片、Base64 解码失败都会被直接拒绝
7. size 为 `WIDTHxHEIGHT` 时必须是 32 的倍数，最小 512，最大 4096，最大宽高比 3:1 / 1:3

## cURL Quick Test

```bash
curl https://token.sensenova.cn/v1/images/generations \
  -H "Authorization: Bearer $SENSENOVA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sensenova-u1.5-fast",
    "prompt": "一只白色毛绒绒的海豹宝宝漂浮在平静海面上，柔和晨光，写实摄影风格",
    "n": 1,
    "size": "1024x1024",
    "output_format": "png",
    "response_format": "url",
    "watermark": false
  }'
```
