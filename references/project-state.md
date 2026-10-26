# 项目记录与版本

在用户项目目录保存 `STORY_PROJECT.json`。这份记录用于接续和定位素材，不要求用户手填，不是自动执行计划。已有分镜格式和用户目录不迁移、不重命名；在本文件引用即可。

## 建议结构

```json
{
  "schema_version": 1,
  "project_name": "本期项目名",
  "track": "biography",
  "content_mode": "factual",
  "writing_profile": "yuling-characterstory",
  "style_id": null,
  "aspect_ratio": "9:16",
  "voice_mode": null,
  "last_request": {
    "stages": {"write": true, "illustrate": false, "draft": false},
    "image_mode": null,
    "scope": "本次明确要求的产物或镜号"
  },
  "artifacts": {
    "manuscript": null,
    "facts": null,
    "audio": null,
    "srt": null,
    "storyboard": null,
    "semantic_review": null,
    "plan": null,
    "draft_result": null
  },
  "progress": {},
  "issues": []
}
```

- 空路径用 null，不把预期文件名填成现有产物。实际 artifact 可为 `{ "path": "manuscript.txt", "sha256": "实际文件哈希" }`；只填实际计算过的哈希。路径相对于项目目录或使用绝对路径，保持一致。
- `last_request.stages` 仅描述本次操作范围，下次不自动继承。用户没有提出新的阶段时，从其“继续/补图/重做草稿”意图解析；只保留项目设置与可复用成果。
- progress 按需记录 writing、voice、storyboard、images、timing、semantic_review、draft；可用 pending、draft、verified、needs_review、blocked。写清已完成范围，例如已生成镜号；没有实际核验不能写 verified。
- voice_mode可为doubao、provided、none。音色参数、确认依据、正文与音频哈希保存在项目voice.json或音频同名.voice.json，artifacts.audio只引用真实生成或已提供的文件；不保存API Key或凭据文件副本。
- track 与 writing_profile 分别表示题材与写法；style_id 是图片画风。关闭写作时允许前两项为空，关闭配图且只复用图片时无需重新询问画风。
- content_mode 区分 factual、legend、fictionalized、fiction；民间故事有多个版本时记录所用版本和改编范围。
- 已有上游 timing_basis、text_audio_review、storyboard_status、逐镜 observed_content 等仍保存在原 STORYBOARD.json / semantic_alignment.json 中，本文件引用它们，不另维护一套切点。

## 改动失效范围

| 改动 | 必须重新核对 |
| --- | --- |
| 定稿或最终配音变化 | 音文差异、字幕来源、分镜边界及下游草稿；事实新增另补核 |
| SRT纠错或时间变化 | 对应 token/cue 与切点；不按新字符数重分时间 |
| 单镜图片替换 | 该镜语义、时代人物、构图与相邻切点，更新实际图片哈希 |
| 镜头边界变化 | 相邻镜原文覆盖、时间证据、图片适用范围、运镜和草稿 |
| 仅封面变化 | 封面检查；无需重做正文时间轴 |

改动时保留旧素材与旧草稿，使用新的 transcription/edit 版本目录。用户明确要求覆盖指定文件时才覆盖，不把相同文件名视为相同版本。

## 阶段衔接

- 只有写作：正文和事实记录即可，不创建虚假的 SRT、分镜或草稿状态。
- 只有配图：接受现成定稿和最终配音；纯文本请求按 text_only 完成，未对齐草稿不冒充已可用于口播生图。
- 只有草稿：接受外部提供的图片与分镜；核对来源、音文和实际图像后补证据，无需原写作模块先“完成”。缺封面记为可选事项，不阻断。
- 全流程：写完若没有最终配音，按[豆包配音](doubao-voice.md)引导配置并确认音色，生成MP3后再推进真实时间轴；配音尚未就绪时保留正文、可做的分镜草稿与缺口。已有MP3时复用，不重复收费，不按估算时间制作“精确草稿”。
- 指定关闭某阶段却缺该阶段产物：报告具体文件/镜号缺口，停止依赖该缺口的后续动作，继续独立工作。不重新询问已经明确的开关。

交付时区分本次完成、沿用已有与尚待处理，不要求用户理解内部 JSON 字段。
