---
name: export-chat
description: 在 macOS 本机将当前 Codex 聊天的全部正文直接导出为 PDF。用于导出聊天 PDF、文档或截图，需要本地会话记录，无须网页或范围选择。
---

# 直接导出全部聊天

运行本技能目录下的 `bash scripts/launch.sh --export --output "$PWD/outputs/chat-images"`。脚本通过 `CODEX_THREAD_ID` 定位当前聊天，一次性导出全部正文并渲染 Markdown 格式，返回 PDF 文件路径和消息数量。完成后提供可点击的本地 PDF 文件链接。PDF 保留文字层，网页链接可点击。

直接执行脚本，不打开网页，不询问起止范围，不把聊天文件或消息列表读进模型上下文。脚本在本机完成读取、分页和文档排版，以减少 token 消耗。

正文包括用户消息和 Codex 的可见文字回复；内部指令、推理、工具日志、图片附件及 Appshot 附带的隐藏窗口/控件描述不在正文范围。输出是正文排版 PDF，需要本机保存的 JSONL 记录、Python、Pillow、ReportLab、pypdf、pdfplumber、Node、Marked和中文字体。缺少当前聊天 ID 或记录不可读时，转述脚本错误，不猜测其他聊天或用摘要替代原文。

独立入口“打开聊天导出.command”直接导出最近更新的本地聊天，不调用模型。它与 Codex 内导出当前聊天的定位方式不同。`scripts/launch.sh --help` 可查看指定聊天 ID 或会话文件的参数。

Markdown 使用本地解析器和文档排版渲染，支持标题、粗体、列表、链接、引用、代码块和表格。整个过程不调用浏览器或网络；缺少运行环境时明确报错，不退回未渲染的文本。

默认只导出 PDF，无需询问格式。若用户明确要求 PNG，脚本仍支持 `--format png`；此兼容模式需要 Pillow 和 PDF 转图工具。旧 PNG 版完整包已单独备份，以便按用户要求回滚。

首次使用缺少依赖时，告知用户可在插件目录执行 `bash setup.sh` 安装。该安装需要网络；导出本身不联网。不要在导出失败时自动下载依赖。
