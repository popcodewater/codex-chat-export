#!/bin/bash
set -euo pipefail
chat_plugin_dir="$(cd "$(dirname "$0")" && pwd)"
bash "$chat_plugin_dir/skills/export-chat/scripts/launch.sh" --export --latest --output "$HOME/Documents/Codex Chat Exports"
