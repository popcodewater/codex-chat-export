# Codex 聊天导出

在 macOS 本机将 Codex 聊天的可见文字正文导出为 PDF。支持中文、Markdown 标题、粗体、列表、引用、代码块、表格、可复制文字和可点击网页链接。

这是个人开发的第三方插件，与 OpenAI 无隶属关系。

## 支持范围

- macOS；需要本机保存的 Codex JSONL 会话记录（默认 `~/.codex/sessions`）。
- 导出用户消息和助手可见文字回复，不包含内部指令、推理、工具日志、图片附件和隐藏窗口描述。
- 仅云端保存、没有本地记录的聊天不支持。会话日志格式变化可能影响兼容性。
- 导出脚本不调用模型 API，不联网；通过 Codex 调用插件仍属于正常的模型交互。
- 使用 macOS 系统字体，不分发字体文件；缺少所需字体时会报错。

## 在 Codex 中安装

需要支持插件市场的 Codex CLI 和桌面客户端。

```bash
codex plugin marketplace add popcodewater/codex-chat-export
```

重启桌面客户端，在插件目录中选择“Codex 聊天导出”来源，安装 `codex-chat-export`。添加来源不会自动安装插件。

在新聊天中调用插件，例如：“导出当前聊天的全部正文为 PDF。”

如果 Codex 已提供完整的配套 Python／Node 运行环境，可以直接使用。缺少依赖时，在**实际运行的插件目录**执行 `bash setup.sh`；客户端通常将安装副本放在 `~/.codex/plugins/cache/`，在仓库副本安装依赖不会自动同步到缓存副本。重新安装或升级插件后，可能需要重装依赖。

插件市场机制参考：[OpenAI 官方说明](https://developers.openai.com/plugins/build/plugins)。

## 独立使用（不调用模型）

从本仓库下载 ZIP 并解压，或：

```bash
git clone https://github.com/popcodewater/codex-chat-export.git
cd codex-chat-export/plugins/codex-chat-export
```

若没有完整的 Codex 配套环境，先安装 Python 3.10+ 和 Node.js 20+（含 npm），再执行：

```bash
bash setup.sh
```

安装脚本会从 PyPI 和 npm 下载依赖，仅写入插件目录内的 `.venv` 和 `node_modules`，不使用 sudo。PNG 兼容模式另需 `pdftoppm`（Poppler）。

导出最近更新的本地聊天：

```bash
bash skills/export-chat/scripts/launch.sh --latest --output "$HOME/Documents/Codex Chat Exports"
```

也可以双击“打开聊天导出.command”。若网页上传或 ZIP 解压后丢失执行权限，先运行 `chmod +x 打开聊天导出.command`，或直接使用上面的 bash 命令。此入口选择最近更新的聊天，可能与桌面当前显示的聊天不同。

指定聊天或文件：

```bash
bash skills/export-chat/scripts/launch.sh --thread 聊天ID --output ./outputs
bash skills/export-chat/scripts/launch.sh --session-file /完整路径/会话.jsonl --output ./outputs
```

更多参数：`bash skills/export-chat/scripts/launch.sh --help`。PNG 兼容模式加 `--format png`。

## 数据与隐私

- 只读取本机选中的会话文件，不修改原始记录，不上传聊天，不包含遥测。
- 排版过程中会创建临时正文和解析文件，正常退出时清理；异常终止时可能残留在系统临时目录。
- 输出保留原文内容，不会自动遮盖原文中的姓名、账号或密钥。请自行决定是否分享导出文件。
- PDF 默认保存到运行目录下 `outputs/chat-images`；独立双击入口保存到 `~/Documents/Codex Chat Exports`。
- `.gitignore` 排除了常见会话记录、导出物、凭据及依赖目录，提交代码前仍应检查文件清单。

## 故障排查

- 无法识别当前聊天：使用 `--thread` 或 `--session-file`；独立入口使用 `--latest`。
- 没有本地记录：确认聊天在本机保存，或用 `--codex-home` 指向实际 Codex 数据目录。
- 缺少依赖：在实际运行的插件目录执行 `bash setup.sh`。
- 找不到 Marked：重装依赖，或通过 `CHAT_EXPORT_NODE_MODULES` 指定含 `marked/` 的 node_modules 目录。
- 文件访问被拒绝：按客户端提示授予对所选会话目录和输出目录的访问权限。
- macOS 阻止独立入口运行：可在终端用 `bash` 执行上面的命令。

## 验证

```bash
bash plugins/codex-chat-export/skills/export-chat/scripts/launch.sh --help
# 在仓库根目录，使用已装依赖的 Python 执行：
python3 -B -m unittest discover -s tests -v
```

测试使用虚构消息，验证正文过滤、错误处理、中文 PDF、链接和分页；仓库不附带真实聊天记录。

## 授权

作者尚未选择开源许可证。公开仓库不代表授予任意修改、再分发或商业使用的许可；第三方依赖按各自许可证授权。本仓库不打包第三方依赖或系统字体。
