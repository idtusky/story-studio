# 直接生成剪映草稿

导出脚本直接调用上游Python库 `pyJianYingDraft==0.3.1`，无需外部草稿技能。

## 初始化与目录

先按 [依赖初始化](../../../references/setup.md) 检查Python库、libmediainfo及ffmpeg/ffprobe。运行环境与本地配置在技能目录之外。

草稿根目录优先级：命令行 `--drafts-root` → `JY_PROJECTS_ROOT` → 用户runtime配置 → 剪映globalSetting中的草稿位置 → 唯一可确定且已经存在的标准目录。新安装由自动初始化创建标准目录；已有自定义设置仍无法读取时由Agent查看剪映设置核对，不先要求用户手动复制路径。

```sh
python "<story-studio目录>/modules/render-history-video/scripts/export_jianying.py" "<版本目录>/plan.json" --drafts-root "<剪映设置中的草稿目录>"
```

上述python应替换为初始化配置中记录的Python绝对路径；便携安装不要求全局PATH或py启动器。入口会自动使用已配置的Python环境。

## 写入行为

1. 校验plan与当前素材，复用已核验时间，不重新均分。
2. 在草稿根目录下新建本次专用暂存工程；复制素材到materials，以内容哈希命名，避免外部文件移动后媒体丢失。
3. 用原库的DraftFolder、TrackSpec、VideoSegment、AudioSegment和可选TextSegment编排工程。
4. 将共享运镜曲线按输出帧率采样成线性缩放/位移关键帧，表达缓入缓出与切点缩放，不传原库不支持的贝塞尔参数，不编码视频。
5. 保存原生draft_content.json，生成内容一致的draft_info.json入口副本，更新工程名称、时长、路径与时间元数据，再提交到最终目录。

默认拒绝同名草稿。明确使用--overwrite时，先将旧目录保留为同目录下的备份再提交新工程；失败的暂存工程会清理，不替换旧成果。

输出jianying_draft.json和resolved_plan.json；前者记录实际库版本、草稿路径、时长、轨道和字幕状态。不生成final.mp4。

## 验收

检查两份工程JSON内容一致、meta路径正确、素材全部存在且位于最终materials目录。检查轨道数量、连续时间、首镜从0开始、音频末尾覆盖、缩放/位移关键帧以及明确要求的字幕。

上游功能说明标注基础功能支持剪映10.8，但当前生成文件与结构检查不等于已经播放。需要在目标剪映中打开、预览并手动导出；不操作剪映UI自动导出。草稿列表未刷新时可重启剪映或进出旧工程刷新。

出错时检查库版本、系统libmediainfo、素材解析和目录权限；不要自动更换实现或修改其他技能。参考 [上游文档](https://github.com/GuanYixuan/pyJianYingDraft)。
