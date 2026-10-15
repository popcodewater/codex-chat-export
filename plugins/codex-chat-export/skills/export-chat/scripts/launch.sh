#!/bin/bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
plugin_root="$(cd "$script_dir/../../.." && pwd)"
runtime_root="$HOME/.cache/codex-runtimes"
for chat_python in \
  "$plugin_root/.venv/bin/python3" \
  "$runtime_root/codex-primary-runtime/dependencies/python/bin/python3" \
  "$(command -v python3 || true)"; do
  if [[ -n "$chat_python" && -x "$chat_python" ]] && "$chat_python" -c 'import PIL, reportlab, pypdf, pdfplumber' >/dev/null 2>&1; then
    exec "$chat_python" -B "$script_dir/export_chat.py" "$@"
  fi
done
echo '缺少 Python 依赖。请在插件目录执行 bash setup.sh，或启用 Codex 配套运行环境。' >&2
exit 1
