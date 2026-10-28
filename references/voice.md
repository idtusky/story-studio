# 语音配置（火山豆包 / 小米 MiMo）与后续制作

用于用户要求配音、文案转MP3，或完整口播流程尚无最终配音时。只维护技能时不合成音频；不复制其他技能的个人音色、凭据、草稿路径或画幅。

## 用户使用流程

文案定稿 → 选择TTS供应商（豆包 / 小米MiMo）或提供已有配音 → 配置并确认音色 → MP3 → Coli本地SRT与音文核对 → 带时间分镜 → 配图 → 剪映草稿。

保留写作、配图、剪映草稿三个主开关；配音是可独立调用的衔接步骤，记录voice_mode=doubao、mimo、provided或none。只写稿时交付稿件，并提示可继续配音，不发送付费请求；用户明确不要配音时不追问。

口播流程缺少可用的本期最终音频时，必须先执行[总入口的两条路径选择](../SKILL.md#缺少最终配音时必须先给出两条路径)：主动同时提供“配置TTS（豆包或小米MiMo）由Agent生成MP3”和“用户自备本期最终MP3”。仅说“缺音频，请提供MP3”不算完成引导；用户只要求配图与剪映草稿、没有点名配音，也应提示。用户已选方式或已有可用音频时不重复询问；仅维护技能时不触发配音选择。禁止复用旧素材的项目不使用旧配音。

选择TTS后进入配置步骤，不要求用户先在其他软件生成文件；选择自备配音后接收文件或路径，由Agent完成Coli转录。等待选择期间只继续不依赖音频的工作，不默认同意合成。已有最终MP3且允许用于本期时直接核验并转录，不重复付费合成。

## 供应商与第一次必须配置的内容

两个TTS供应商各自使用独立的API Key和音色参数，配置在同一个voice.json里但带provider字段区分；当前仅一个有效供应商配置。切换供应商需重新执行configure并写入该供应商参数。

| 配置项 | 豆包（火山引擎） | 小米 MiMo |
| --- | --- | --- |
| API Key 环境变量 | `DOUBAO_TTS_API_KEY` | `MIMO_API_KEY` |
| API Key 获取 | [豆包语音控制台API Key管理](https://console.volcengine.com/speech/new/setting/apikeys)，对应X-Api-Key | [MiMo 控制台](https://mimo.mi.com)的API Key，请求头传 `api-key` |
| 音色参数 | speaker ID（音色ID） + 模型资源 `resource_id`（普通2.0用 `seed-tts-2.0`，复刻2.0用 `seed-icl-2.0`） | 模型ID（`mimo-v2.5-tts` 预置音色、`mimo-v2.5-tts-voicedesign` 文本设计音色、`mimo-v2.5-tts-voiceclone` 样本复刻）+ 相应音色字段 |
| 预置音色 | 控制台音色库 | `mimo_default`（中国集群默认冰糖）、冰糖、茉莉、苏打、白桦（中文）、Mia、Chloe、Milo、Dean（英文） |
| 附加能力 | 语速与音量（-50..100）、复刻细分model | 发音风格/情绪/方言/唱歌等通过 style 描述注入 user 消息；voicedesign 用文本描述生成音色；voiceclone 用本地 mp3/wav 样本（base64 ≤10MB） |
| 计费提示 | 按合成计费，需开通语音服务 | 2026.07 文档显示限时免费，以控制台账单为准 |

“模型”字段两个供应商含义不同：豆包的resource_id决定服务资源，req_params.model是复刻音色的可选细分参数；MiMo的model字段直接指 `mimo-v2.5-tts` 系列模型ID。不要把Ark文本模型ID、App ID、字幕Key或音色ID当作豆包resource_id；不要求新版豆包API Key用户额外提供App ID或Access Token。

用户需自行开通对应语音服务并保证资源可用，Agent负责配置本地调用端。音色和资源是否匹配以其账号控制台及真实接口结果为准，不能仅凭名称保证匹配。首次不要默认克隆任何人的声音或创建复刻任务。

可使用这样的引导：

> 文案已定稿，可以继续生成配音。请选择语音服务：火山豆包 或 小米MiMo。对应地在语音控制台开通服务，并通过宿主的安全输入/密钥配置入口提供该服务的API Key；同时告诉我音色参数（豆包：speaker ID和模型资源；MiMo：模型ID与音色ID或音频样本）。我会配置并生成MP3，然后接续Coli转录、配图和剪映草稿。已有最终配音也可以直接复用。

## 配置由Agent完成

先按[初始化流程](setup.md)检查/配置features=tts；后面还需转录和草稿时用tts,asr,draft,images。缺少的Python、websockets和FFmpeg由Agent安装，不要求用户执行命令。依赖安装不需要语音Key，也不会发送收费测试。豆包V3走WebSocket需要`websockets==15.0.1`；MiMo走OpenAI兼容HTTP接口，仅用Python标准库即可。

API Key优先从宿主安全配置的环境变量读取（豆包 `DOUBAO_TTS_API_KEY`，MiMo `MIMO_API_KEY`）。只检查存在性，不显示值；不要要求在公开聊天中粘贴Key。若用户已经通过可用的保密渠道提供Key，且同意在当前电脑保存，Agent可用voice_settings.py的--key-stdin从标准输入写入该供应商专用凭据文件，不把Key放到命令参数、shell历史、项目JSON或日志。--prompt-key仅用于宿主能直接提供隐藏输入的交互终端，不要求用户自行打开终端。没有保密输入能力时引导到宿主密钥/环境变量面板，不能伪称已配置。

也支持**.env 文件形式**：把 `MIMO_API_KEY=sk-...`（或 `DOUBAO_TTS_API_KEY=...`）写入用户数据目录的 `.env` 文件——macOS/Linux 为 `~/.local/share/story-studio/.env`，Windows 为 `%LOCALAPPDATA%\story-studio\.env`（建议 chmod 600）。脚本读取Key时自动加载该文件；**真实环境变量优先级高于 .env**，.env 又优先于私密凭据文件。该文件在技能目录之外，不会进入仓库或安装包。

Agent使用初始化记录的Python绝对路径运行（configure省略provider时默认doubao；check省略provider时跟随已配置的供应商）：

```text
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" check
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" configure --provider doubao --speaker "<用户的speaker ID>" --resource-id "<用户选择的resource_id>"
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" configure --provider mimo --model mimo-v2.5-tts --voice "冰糖" [--style "沉稳克制、历史纪录片式旁白"]
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" configure --provider mimo --model mimo-v2.5-tts-voiceclone --voice-sample "<本地样本路径>"
```

复刻音色豆包侧明确需要细分模型时加--model（仅seed-icl-2.0）。若要保存已授权的Key，在configure命令加--key-stdin并通过进程标准输入传入；不能使用带实际密钥的--api-key参数。仅保存音色时缺少Key会返回未就绪状态，音色配置仍已保存。check不联网，只返回各供应商Key是否存在、非秘密的音色参数和network_verified=false。

音色参数保存到用户数据目录story-studio/voice.json（含provider字段），与runtime.json分开。各供应商Key保存到同一专用目录：Windows使用当前用户DPAPI加密文件，macOS/Linux是权限0600的本地私密文件，保存前说明这一点，用户不愿保存时直接复用宿主密钥环境变量。源码目录拒绝写入这些配置；发布、打包或提交代码时不包含用户数据目录。

## 本期确认与生成MP3

每个新项目在首次生成前展示准确的供应商参数：豆包为speaker ID、resource_id、可选model、语速（默认0）、音量（默认0）；MiMo为模型ID、音色ID或样本指纹、style（若有）。同时展示朗读范围。用户本次已明确确认上述参数用于生成时不重复询问；历史保存配置可作为候选，不能自动代替本期确认。确认后记录在项目voice.json，不含Key。只朗读定稿正文；source.txt保存原稿，narration.txt保存实际送入内容，标题、注释是否朗读按本次请求处理。

```text
"<配置的Python>" "<技能绝对路径>/scripts/doubao_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --dry-run
"<配置的Python>" "<技能绝对路径>/scripts/doubao_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --voice-confirmed
"<配置的Python>" "<技能绝对路径>/scripts/mimo_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --dry-run
"<配置的Python>" "<技能绝对路径>/scripts/mimo_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --voice-confirmed
```

dry-run仅核验本地文本和音色参数，不读取Key、不联网；成功不表示鉴权或额度已验证。只有实际获得确认才能加--voice-confirmed。豆包脚本使用V3双向WebSocket接口，MiMo脚本使用OpenAI兼容chat/completions接口（messages中assistant消息承载合成文本，audio.format=mp3，请求头api-key），均不静默切换其他服务、模型或音色。MiMo超长文案被拒或finish_reason=length时，需按句/段拆分后分次合成，用ffmpeg concat demuxer合并（不能二进制拼接），最终合并音频重新完整解码，Coli只识别最终版本。

两个脚本都以不丢字符的方式发送全文，等到完整音频后再用ffprobe和ffmpeg完整解码校验，保留失败的partial供排查；豆包等到SessionFinished才视为完成。输出MP3及同名.voice.json，记录文本哈希、供应商参数、协议、音频哈希和时长，不写Key。默认不覆盖已有MP3；同稿同音色先检查已有成功文件，避免再次收费。MiMo本地voiceclone样本路径不写入元数据，以样本哈希代替。

鉴权、额度、资源或音色错误时停在配音阶段，提示具体缺口，保留已完成文稿。网络超时或不完整流可能已计费，脚本不自动重试；Agent先核对partial、已有MP3及控制台请求状态，明确是否需要重新合成。MP3已成功但后续转录/生图失败时只续做下游。

## 接续转录、配图与草稿

1. 检查MP3完整解码、正文开头结尾、专名发音与漏读；未试听不称听过。再调用内置[配图模块](../modules/history-image/GUIDE.md)的Coli脚本，识别最终MP3，保留音频哈希与原始结果，对照文案修正错字。配音来源不影响后续链路；豆包和MiMo产出的MP3走完全相同的转录、分镜、配图流程。
2. 使用真实SRT与上下文确定分镜时间，重复句消歧，不按字数或镜数均分时长；实际生图仍需遵守本次配图开关、画风和数量选择。
3. 调用内置[草稿模块](../modules/render-history-video/GUIDE.md)，传同版MP3、核验SRT、分镜与实际图片，沿用本项目画幅；默认仍为9:16，不继承参考技能的16:9。字幕用于定位不等于上屏。

TTS只负责合成，始终enable_subtitle=false（豆包侧）。字幕使用本机Coli，不调用或恢复已停用的火山字幕API及其凭据。交付MP3、SRT、图片和草稿时区分实际生成、结构验证、试听和剪映预览范围。

协议及参数依据：[豆包V3双向WebSocket官方文档](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-text-to-speech-websocket?lang=zh)、[官方协议附件](https://portal.volccdn.com/obj/volcfe/cloud-universal-doc/upload_5ec6e28945592c909158dc1e2cf9a89c.zip)、[websockets客户端文档](https://websockets.readthedocs.io/en/15.0.1/reference/asyncio/client.html)、[MiMo语音合成文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)。本项目自行实现所需二进制帧与请求流程，不内嵌官方协议附件源码。