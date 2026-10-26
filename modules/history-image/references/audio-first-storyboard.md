# 先转录音频，再定稿分镜，再生图

这是历史口播视频配图的默认顺序，适用于全部画风、指定 N 张和自动决定数量两种方式。优先于旧的“先按文稿拆镜生图，剪辑时再补对齐”做法。不引入配音生成，不自动授权生图或渲染。

## 执行顺序

1. **确定数量方式与素材。** 用户指定 N 张则锁定 N；用户要求根据全文自动拆分则先读全文形成初步镜数，实际分配在时间轴核验后完成，无须要求用户另选 N。读取完整定稿与对应最终配音，区分正文、标题及不朗读备注；已有明确素材路径直接使用。画风选择可同步进行，不妨碍转录。
2. **先用本机 Coli 转录，完全不依赖分镜表。** 在新版本目录运行：

   `py -3.11 "<story-studio目录>/modules/history-image/scripts/transcribe_with_coli.py" --audio "<最终配音>" --out-dir "<项目>/transcription/<版本>" --model sensevoice --language zh`

   输出原始 coli_asr.json、transcript.srt、transcript_timing.json，保留音频及字幕哈希。脚本从真实 token 起点分组字幕；字幕结束使用下一 token 起点或音频结束，是字幕显示边界，不冒充精确发声结束。没有标点时分组只为可读性，不能认为一条 SRT 就是一个完整句子或一个分镜。原始 tokens/timestamps 保留供句内事件定位。只接受可用时间戳，不按字数猜测。不得调用火山字幕 API 或恢复其凭据。
3. **核对 SRT 与全文。** 比较全文顺序、人物、年份、否定词、重复语句及漏句。转录错字可依据原稿和实际音频纠正，并保存原始记录；真实口播与定稿不同则记录版本差异，不能把未读的原稿文字硬塞进字幕。纠错后需要维护文字与原始 token 时间的对应关系，不按新字符数重分时间。字幕及音频来源相同且已核验时复用，不重复转录；用户指定重新 Coli 转录时照做。无来源或只凭文件名不能认定是当前配音的字幕。
4. **依据已核验时间轴拆分全文。** 每个完整语义单元先绑定原文范围、SRT cue IDs 和有证据的起止时间，再在全篇规划 N 个镜头。邻近同事件可合并，多事件长句可在有 token 时间证据的位置拆开；不按每条字幕一图，不等分秒数。优先保持画面与当前人物、时空、动作、事件阶段一致，再尽量平衡各镜停留时间。固定数量导致冲突时说明具体段落与可行取舍，不偷偷增减。
5. **先定稿带时间的分镜表。** 每镜写原文全文片段、语义概述、实际显示 start/end、发声起点 audio_start、时间证据、cue_ids、画面必须表现的具体内容、不能提前出现的后续事件、完整提示词及图片编号。第一张图 start=0，真实首字发声可以更晚。一般镜头 end 等于下一镜 start，末镜覆盖整段配音；停顿默认留在上一镜。只做分镜的请求在此停止，不生图。
6. **核验通过后才按表生图。** 项目 storyboard_status=ready_for_images、timing_status=aligned，并已完成 text_audio_review；这表示文本和时间已核验，不表示图片已验收。生图逐镜使用本表 narration、description、prompt，不能另凭全文自由构思另一组场景。实际图片生成后打开核对本镜口播与画面，错图按当前授权修正；记录图片路径、observed_content、image_semantic_status。
7. **按同一张表剪辑。** 下游继承本表 start/end 和图片映射，只做帧量化与核验，不重新均分或模糊匹配找切点。重新配音、改稿、改边界后相应分镜回到待核验，不能沿用旧时间表。旧脚本 align_with_coli.py 可复用原始 Coli JSON 对定稿边界做保守复核，不作为先有分镜才能转录的前置条件；它输出的 coli_aligned.srt 是按镜诊断文件，不能代替原始转录字幕。

## 没有音频时

对口播视频配图，先执行[总入口的两条路径选择](../../../SKILL.md#缺少最终配音时必须先给出两条路径)，主动提示“配置豆包并生成MP3 / 自备本期最终MP3”；不得仅报告缺音频或只要求用户提供MP3便结束。用户已选方式时不重问；配音生成与配置由总入口衔接，本模块不自行发送合成请求。

等待期间可先做全文分析、数量建议、人物时代与分镜草稿，但标记 storyboard_status=draft_waiting_audio、timing_status=unavailable、时间字段为空；不把它作为已定稿生图表。用户无需手动制作 SRT。用户明确只做独立插图、封面、静态图文或明确选择不依赖音频的文本分镜时，可以按该范围完成，不强加配音要求，记录 workflow=text_only。已有镜头补图/改图复用当前已核验表，不重跑整期转录。

## 数据与验证

口播工作流项目记录 workflow=audio_first、storyboard_status、timing_basis（音频/SRT/原始 Coli 路径及哈希）、text_audio_review（status、差异与处理证据）。逐镜追加 start/end、cue_ids、timing_evidence、visual_onset_anchor、semantic_event、must_depict、must_not_anticipate；audio_end 若只有显示上界，应记录 audio_end_basis=display_boundary，不能称词尾时间。JSON 与 Markdown 由同一结果输出。

交付前核对：全文无遗漏无重复、N 张数量正确、每镜切点有字幕/token 证据、所有 start/end 连续、图片内容未提前/滞后、时长异常已处理。有时间轴时文字量告警只是辅助，不能为了消除字数告警移动已正确的语义切点。保存语义核验结果供下游，不能因为已有 SRT 文件就将 text_audio_review 写成 verified。
