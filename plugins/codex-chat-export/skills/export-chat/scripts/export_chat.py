#!/usr/bin/env python3
"""Export all visible text in the current local Codex chat to PDF by default (no model calls)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import sys
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image, ImageChops
from markdown_pdf import render_pdf

SCRIPT_DIR = Path(__file__).resolve().parent
BODY_KINDS = {"user.text", "user_text", "unknown"}
HIDDEN_TAGS = (
    "environment_context", "recommended_plugins", "external_codex_apps_open_page",
    "external_codex_apps_selected_text", "system_reminder",
)


class ExportError(Exception):
    pass


def clean_user_text(text):
    # Older logs lack item-kind metadata. Strip host-added wrappers, not ordinary XML.
    for tag in HIDDEN_TAGS:
        text = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", "", text, flags=re.S)
    return text.strip()


def strip_appshot_context(text):
    # Appshot UI trees can be embedded in a user.text item rather than separate metadata.
    # Recognize the complete host envelope, keeping literal tags/code in ordinary messages.
    prefix = re.match(r'\A\s*# Applications mentioned by the user:\s*\n', text)
    if not prefix:
        return text
    context, separator, request = text[prefix.end():].partition('\n## My request:')
    if separator and re.fullmatch(r'\s*(?:<appshot\b[^>]*>[\s\S]*?</appshot>\s*)+', context):
        return request.strip()
    return text


def visible_text(payload):
    role = payload.get("role")
    if role not in ("user", "assistant") or payload.get("channel") in ("analysis", "summary"):
        return ""
    meta = payload.get("internal_chat_message_metadata_passthrough") or {}
    kinds = meta.get("content_item_kinds") or []
    parts = []
    for n, item in enumerate(payload.get("content") or []):
        if not isinstance(item, dict) or item.get("type") not in ("input_text", "output_text", "text"):
            continue
        if role == "user" and n < len(kinds) and kinds[n] not in BODY_KINDS:
            continue
        text = item.get("text", "")
        if not isinstance(text, str):
            continue
        if role == 'user':
            text = strip_appshot_context(text)
        has_user_metadata = n < len(kinds) and kinds[n] in ("user.text", "user_text")
        parts.append(clean_user_text(text) if role == "user" and not has_user_metadata else text.strip())
    return "\n\n".join(p for p in parts if p).strip()


def read_messages(path):
    messages = []
    seen_ids = set()
    thread_id = None
    saw_message = False
    # Reading a byte snapshot prevents an actively appended partial line becoming corruption.
    snapshot = Path(path).read_bytes()
    lines = snapshot.splitlines()
    for index, raw in enumerate(lines):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            if index == len(lines) - 1 and not snapshot.endswith(b"\n"):
                continue
            raise ExportError(f"会话记录第 {index + 1} 行无法识别，已停止导出。")
        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "session_meta":
            thread_id = payload.get("id") or payload.get("session_id")
        if record.get("type") != "response_item" or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role not in ("user", "assistant"):
            continue
        saw_message = True
        # Never include analysis even in older recordings with an explicit channel.
        if payload.get("channel") in ("analysis", "summary"):
            continue
        message_id = payload.get("id")
        if message_id and message_id in seen_ids:
            continue
        text = visible_text(payload)
        if text:
            messages.append({"number": len(messages) + 1, "role": role, "text": text})
            if message_id:
                seen_ids.add(message_id)
    if not messages:
        detail = "没有可导出的文字正文" if saw_message else "当前记录不是受支持的完整消息格式"
        raise ExportError(f"{detail}。请确认这段聊天已保存到本机。")
    return messages, thread_id or Path(path).stem[-36:]


def session_paths(codex_home):
    root = Path(codex_home) / "sessions"
    if not root.is_dir():
        raise ExportError("没有找到本地 Codex 会话目录。云端聊天或未保存到本机的聊天暂不支持。")
    return sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def find_session(codex_home, thread_id):
    matches = [p for p in session_paths(codex_home) if p.stem.endswith(thread_id)]
    if len(matches) != 1:
        raise ExportError("无法唯一定位当前聊天的本地记录，请确认该聊天已保存到本机。")
    return matches[0]


def rendering_runtime(require_raster=True):
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
    node = bundled / "node/bin/node"
    if not node.is_file():
        node = Path(shutil.which("node") or "/missing-node")
    plugin_root = SCRIPT_DIR.parents[2]
    module_candidates = [plugin_root / "node_modules", bundled / "node/node_modules"]
    configured_modules = os.environ.get("CHAT_EXPORT_NODE_MODULES")
    modules = Path(configured_modules).expanduser() if configured_modules else next(
        (item for item in module_candidates if (item / "marked").is_dir()), module_candidates[0])
    raster = bundled / "bin/override/pdftoppm"
    if not raster.is_file():
        raster = Path(shutil.which("pdftoppm") or "/missing-pdftoppm")
    if not node.is_file() or (require_raster and not raster.is_file()) or not (modules / "marked").is_dir():
        raise ExportError("缺少 Markdown 排版运行环境（Node、Marked 或 PDF 转图工具）。请运行插件目录中的 setup.sh，或启用 Codex 配套运行环境。")
    env = dict(os.environ)
    env["CHAT_EXPORT_NODE_MODULES"] = str(modules)
    return str(node), str(raster), env


def create_chat_pdf(messages, short_id, start, end, destination, page_height):
    node, _, env = rendering_runtime(require_raster=False)
    try:
        with tempfile.TemporaryDirectory(prefix="codex-chat-pdf-") as temporary:
            temporary = Path(temporary)
            data, tokens = temporary / "messages.json", temporary / "tokens.json"
            data.write_text(json.dumps({"messages":messages[start-1:end], "short_id":short_id,
                                       "start":start, "end":end}, ensure_ascii=False))
            result = subprocess.run([node, str(SCRIPT_DIR / "render_markdown.mjs"), str(data), str(tokens)],
                                    env=env, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise ExportError(result.stderr.strip()[:1800] or "Markdown 排版失败。")
            try:
                render_pdf(json.loads(tokens.read_text()), destination, page_height)
            except Exception as error:
                raise ExportError("Markdown 排版失败：" + str(error)[:800]) from error
    except subprocess.TimeoutExpired:
        raise ExportError("Markdown 排版超时，未完成导出。")


def render_pdf_export(messages, thread_id, output, page_height=8000):
    if not messages:
        raise ExportError("没有有效的聊天正文可导出。")
    output = Path(output).expanduser().resolve()
    run_name = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    folder = output / run_name
    folder.mkdir(parents=True, exist_ok=False)
    short_id = re.sub(r"[^A-Za-z0-9-]", "", str(thread_id))[:8] or "chat"
    destination = folder / f"chat-{short_id}-1-{len(messages)}.pdf"
    create_chat_pdf(messages, short_id, 1, len(messages), destination, page_height)
    # Match the PNG's trimmed whitespace while preserving PDF text and link annotations.
    import pdfplumber
    from pypdf import PdfReader, PdfWriter
    with pdfplumber.open(destination) as document:
        bottoms = []
        for page in document.pages:
            objects = page.chars + page.rects + page.lines + page.curves
            used_bottom = max((item['bottom'] for item in objects), default=page.height)
            bottoms.append(max(0, page.height - used_bottom - 30))
    reader = PdfReader(destination)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page, bottom in zip(writer.pages, bottoms):
        if bottom > 0:
            lower = float(page.mediabox.bottom) + bottom
            page.cropbox.lower_left = (page.mediabox.left, lower)
            page.mediabox.lower_left = (page.mediabox.left, lower)
    trimmed = destination.with_suffix('.tmp.pdf')
    with trimmed.open('wb') as handle:
        writer.write(handle)
    trimmed.replace(destination)
    return [destination]


def render_pngs(messages, thread_id, start, end, output, page_height=8000):
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise ExportError("消息编号必须是整数。")
    if not 1 <= start <= end <= len(messages):
        raise ExportError("没有有效的聊天正文可导出。")
    if not 700 <= page_height <= 16000:
        raise ExportError("分页高度必须在 700 到 16000 像素之间。")
    node, raster, env = rendering_runtime()
    output = Path(output).expanduser().resolve()
    run_name = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    folder = output / run_name
    folder.mkdir(parents=True, exist_ok=False)
    short_id = re.sub(r"[^A-Za-z0-9-]", "", str(thread_id))[:8] or "chat"
    prefix = f"chat-{short_id}-{start}-{end}"
    files = []
    try:
        with tempfile.TemporaryDirectory(prefix="codex-chat-markdown-") as temporary:
            temporary = Path(temporary)
            pdf = temporary / "chat.pdf"
            create_chat_pdf(messages, short_id, start, end, pdf, page_height)
            converted = subprocess.run([raster, "-png", "-r", "96", str(pdf), str(temporary / "page")],
                                       capture_output=True, text=True, timeout=120)
            if converted.returncode:
                raise ExportError("Markdown 图片生成失败：" + converted.stderr.strip()[:500])
            pages = sorted(temporary.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
            if not pages:
                raise ExportError("没有生成有效的 Markdown 图片。")
            for number, page in enumerate(pages, 1):
                with Image.open(page) as image:
                    image = image.convert("RGB")
                    box = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
                    height = min(image.height, box[3] + 40) if box else image.height
                    filename = folder / f"{prefix}-{number:02d}.png"
                    image.crop((0, 0, image.width, height)).save(filename, "PNG")
                    files.append(filename)
        if len(files) > 1:
            archive = folder / f"{prefix}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for path in files:
                    z.write(path, path.name)
            files.append(archive)
        return files
    except subprocess.TimeoutExpired:
        raise ExportError("Markdown 排版超时，未完成导出。")


def main():
    parser = argparse.ArgumentParser(description="直接导出当前 Codex 聊天的全部正文为 PDF。")
    parser.add_argument("--export", action="store_true", help="导出全部正文（默认行为）")
    parser.add_argument("--format", choices=("pdf", "png"), default="pdf", help="导出格式，默认 pdf；png 为兼容模式")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--thread", help="聊天 ID；默认取 CODEX_THREAD_ID")
    target.add_argument("--session-file", help="指定一个本地 JSONL 会话文件")
    target.add_argument("--latest", action="store_true", help="独立启动：自动导出最近更新的本地聊天")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--output", default=str(Path.cwd() / "outputs" / "chat-images"))
    args = parser.parse_args()
    try:
        if args.session_file:
            path = Path(args.session_file).expanduser()
        elif args.latest:
            paths = session_paths(args.codex_home)
            if not paths:
                raise ExportError("没有找到可导出的本地聊天。")
            path = paths[0]
        else:
            thread = args.thread or os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
            if not thread:
                raise ExportError("无法识别当前聊天，请在 Codex 中调用插件，或使用独立入口导出最近更新的聊天。")
            path = find_session(args.codex_home, thread)
        messages, thread_id = read_messages(path)
        files = render_pdf_export(messages, thread_id, args.output) if args.format == "pdf" else render_pngs(messages, thread_id, 1, len(messages), args.output)
        print(json.dumps({"thread_id": thread_id, "message_count": len(messages), "format": args.format,
                          "files": [str(p) for p in files]}, ensure_ascii=False))
    except (ExportError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
