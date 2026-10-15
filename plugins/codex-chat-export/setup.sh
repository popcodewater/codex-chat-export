#!/bin/bash
# Explicit installation only: exporting never downloads dependencies.
set -euo pipefail
plugin_root="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo '当前版本仅支持 macOS。' >&2; exit 1
fi
for dependency in python3 node npm; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "缺少 $dependency。请先安装 Python 3.10+ 和 Node.js 20+（含 npm）。" >&2; exit 1
  fi
done
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10+"'
node -e 'if(Number(process.versions.node.split(".")[0])<20){console.error("需要 Node.js 20+");process.exit(1)}'
python3 -m venv "$plugin_root/.venv"
"$plugin_root/.venv/bin/python3" -m pip install -r "$plugin_root/requirements.txt"
npm install --prefix "$plugin_root" --ignore-scripts --no-audit --no-fund
bash "$plugin_root/skills/export-chat/scripts/launch.sh" --help >/dev/null
echo '依赖已安装到插件目录，可运行 launch.sh 导出。'
