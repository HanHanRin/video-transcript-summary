# 视频笔记 Skill · Video Transcript Summary

把一个视频链接，变成**可回查的文字稿、结构化总结和可离线阅读的 HTML 网页**。

以 Bilibili 为主要使用场景，支持完整链接、b23.tv 分享短链和含链接的分享文本。适合整理教程、知识分享、访谈和产品讲解，不必反复拖动视频查找重点。

> **请先确认运行环境**：这是由兼容 AI 助手编排的 Skill，不是一个独立视频网站、浏览器扩展或开箱即用的公共 ASR 服务。在线获取与转写依赖宿主提供的 `doubao-video-extract`、已认证的 `lark-cli` 及相应云端权限，本仓库不包含这些外部能力。仅安装 Python 包不能获得它们。已有文字稿的归档、校验、HTML 渲染和离线测试可使用本仓库代码完成；语义总结仍由助手提供。

## 能做什么

- **视频转文字稿**：通过已有云端 ASR 生成文字记录，保留来源链接和实际返回的时间戳；当前 B 站链路不是平台字幕抓取。
- **结构化总结**：输出一句话概括、核心结论、章节要点、关键论据、作者建议和核验提醒。
- **证据可回查**：重点附原稿段落和连续原文摘录，校验引文存在且覆盖全部原稿段落；语义正确性仍需助手复核。
- **美观 HTML 阅读页**：章节路线、纵向时间轴、展开引用、跳转完整原稿、全文搜索、原视频链接、打印 / 保存 PDF。
- **离线阅读**：HTML 内嵌全部文本、样式和脚本，无远程字体、第三方前端库、自动加载的媒体或追踪脚本。点击原视频链接才访问来源网站。
- **长稿分块**：保留原稿，按内容长度分块阅读，避免只总结前半段；无时间戳不会自行推算。
- **恢复已有任务**：读取已创建的转写结果，避免因结果读取失败而重复上传。
- **旧笔记补网页**：直接从已保存文稿生成 HTML，不重新下载、上传或转写；更新页面会备份旧版。
- **完成后清理本地媒体**：文稿和 HTML 均保存并通过完整性检查后，才清理本任务生成的临时音视频。

## 使用体验

在已安装并具备依赖能力的 AI 助手中输入：

> 用视频笔记 Skill 处理这个链接：粘贴你的 B 站链接。

默认完成：

1. 识别链接及分P，获取视频并交给已有云端能力转写。
2. 保存全文，分块阅读，生成有原文依据的总结。
3. 自动生成可视化 HTML 阅读页。
4. 校验文本、引用与文件完整性，并检查网页显示。
5. 清理本任务本地临时媒体，交付 HTML、文字稿和总结。

已有笔记只需说：

> 把这份已完成的视频笔记生成 HTML 阅读页，不要重新转写。

## 输出文件

每个任务使用独立目录，同名任务不会覆盖旧结果。

- `视频笔记.html`：主要阅读入口，可单独复制、发送和离线打开。
- `文字稿.md`：完整文字稿，保留实际时间戳和来源。
- `总结.md`：结构化总结及原文依据。
- `transcript.txt`：原始转写文本。
- `transcript.json`、`summary.json`：结构化原稿与总结，便于后续处理。
- `task.json`：任务状态、文件哈希与清理记录，是唯一状态来源。

HTML 是本次笔记的静态快照，不会自动联网更新历史价格、参数或其他事实。时间轴标记是引用段落起点，不是逐字字幕定位。

## 环境与安装

### 完整链接转写流程

需要：

- 能读取并执行 `SKILL.md` 的兼容 AI 助手及本地文件/命令能力。
- Python 3.10+；主要在 macOS 环境完成验收，Windows 完整链路未验证。
- 宿主已提供的视频提取后端与云端转写权限；本仓库不分发其实现或凭据。
- PyAV，用于已有后端的音频转换。其他下载依赖以该后端要求为准。

将仓库作为完整文件夹加载到助手的自定义 Skill 目录。`SKILL.md` 为入口，`scripts/` 和 `references/` 必须一起保留。默认发现同一工作区 `.skills/doubao-video-extract`；不同布局使用 `--backend-root` 指定真实目录。

如兼容宿主缺少 PyAV，可在 Skill 目录内安装隔离依赖：

```bash
python3 -m pip install --target .runtime/pythonlibs av
```

这只安装音频处理库，不购买或开通云端 ASR。云端额度、费用政策和访问权限由使用者自己的宿主服务决定，本项目不承诺无限免费转写。

### 无在线后端的本地使用

已有 SRT、VTT、普通文本或时间戳文字稿时，可以使用 `init`、`ingest`、`finalize`、`render-html` 等命令处理。总结 JSON 必须由助手按 [总结契约](references/summary-contract.md) 提供，`finalize` 本身不调用大模型生成总结。

## 命令速查

在仓库根目录查看参数：

```bash
python3 scripts/video_notes.py --help
python3 scripts/video_notes.py fetch --help
```

以下 `input.txt`、`笔记目录`、`已有文字稿.txt` 和 `总结草稿.json` 均为调用者实际准备的文件/目录；不要原样使用不存在的路径。

```bash
# input.txt 中放一个完整链接或分享文本；需要已配置在线后端
python3 scripts/video_notes.py fetch \
  --source-file input.txt --output-root ./视频笔记 --name "视频短标题"

# 从已创建的云端任务恢复，不重复上传
python3 scripts/video_notes.py recover --job "笔记目录"

# 已有文字稿：先建任务，再导入
python3 scripts/video_notes.py init \
  --source-file input.txt --output-root ./视频笔记 --name "视频短标题"
python3 scripts/video_notes.py ingest \
  --job "笔记目录" --transcript "已有文字稿.txt" --method provided_transcript

# 助手准备总结 JSON 后，生成总结和 HTML
python3 scripts/video_notes.py finalize \
  --job "笔记目录" --summary "总结草稿.json"

# 给旧任务补网页 / 重生成页面
python3 scripts/video_notes.py render-html --job "笔记目录"

# 校验并预览本地临时媒体清理计划
python3 scripts/video_notes.py verify --job "笔记目录"
python3 scripts/video_notes.py cleanup --job "笔记目录"

# 确认是本任务媒体后执行清理
python3 scripts/video_notes.py cleanup --job "笔记目录" --apply
```

`fetch` 完成转写后会进入 `needs_summary`，由助手继续阅读、总结、生成页面和清理；它不是一条无需助手参与就能自动完成语义总结的命令。

## 隐私与安全

- **本地清理不等于云端删除**。云端转写服务可能保留音频和妙记，本项目不承诺自动删除云端副本。
- 只删除本任务 `.work/media/` 中生成的媒体。任务外文件、用户原文件、陌生文件和符号链接不在自动删除范围。
- 没有完整文稿或 HTML、文件被修改、引用不匹配时，不执行完成清理。
- 失败或中断时保留恢复所需文件，不假报成功。
- 不绕过平台登录、会员、地区、私密内容或其他访问限制；仅处理你有权访问、转写和保存的内容。
- ASR 可能误识专名、型号、数字和否定词；作者观点、历史报价及参数不等于已核验事实。
- 分享 HTML 会同时分享内嵌完整文字稿，请先检查内容是否适合公开。
- 本仓库仅提交源码、规则与说明，不包含真实视频、个人笔记、云端任务记录、Cookie、密钥或本机依赖。

## 开发与验证

本地离线测试只需 Python 标准库：

```bash
python3 -B scripts/test_video_notes.py
```

当前包含 33 项回归测试，覆盖文本解析、长稿保真、引文覆盖、文件完整性、HTML 生成、旧版迁移、路径及清理保护、链接转义和防覆盖等。

开发时已用一个真实 B 站视频验证获取、转换、云端转写、恢复读取和文稿归档；HTML 在桌面 1440×900 与手机 390×844 下做过显示及交互检查。其他平台与全部操作系统尚未逐项验收，测试不代表全平台兼容或转写零误差。

## 源码导览

- [SKILL.md](SKILL.md)：助手工作流入口。
- [scripts/video_notes.py](scripts/video_notes.py)：任务编排、存档、引用校验、恢复与清理。
- [scripts/html_reader.py](scripts/html_reader.py)：单文件 HTML 阅读器生成。
- [scripts/test_video_notes.py](scripts/test_video_notes.py)：离线回归测试。
- [references/summary-contract.md](references/summary-contract.md)：结构化总结与证据约定。
- [references/html-reader.md](references/html-reader.md)：阅读页设计、事实和安全约定。
- [references/execution.md](references/execution.md)：执行与恢复边界。
