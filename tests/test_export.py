import json
import sys
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins/codex-chat-export/skills/export-chat/scripts"))
import export_chat as exporter


def message(role, text, **extra):
    return {"type": "response_item", "payload": {"type": "message", "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}], **extra}}


class ExportTests(unittest.TestCase):
    def test_hidden_content_and_duplicates(self):
        records = [message("system", "SYSTEM_SECRET"), message("user", "你好"),
                   message("assistant", "ANALYSIS_SECRET", channel="analysis"),
                   message("assistant", "可见回复", id="same"),
                   message("assistant", "可见回复", id="same"),
                   message("user", "<environment_context>HOST_SECRET</environment_context>正文")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.jsonl"
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n")
            messages, _ = exporter.read_messages(path)
        self.assertEqual([row["text"] for row in messages], ["你好", "可见回复", "正文"])

    def test_corrupt_middle_record_stops_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.jsonl"
            path.write_text(json.dumps(message("user", "hello")) + "\nBROKEN\n{}\n")
            with self.assertRaises(exporter.ExportError):
                exporter.read_messages(path)

    def test_appshot_wrapper_preserves_request(self):
        text = "# Applications mentioned by the user:\n<appshot>HOST_SECRET</appshot>\n## My request:保留正文"
        self.assertEqual(exporter.visible_text(message("user", text)["payload"]), "保留正文")

    def test_chinese_pdf_pagination_and_links(self):
        messages = [{"number": 1, "role": "user", "text": "中文导出测试"},
                    {"number": 2, "role": "assistant", "text":
                     "# 测试标题\n\n**加粗** 与 [示例链接](https://example.com)\n\n"
                     "|项目|结果|\n|---|---|\n|导出|成功|\n\n```python\nprint('hello')\n```\n\n" +
                     "\n\n".join("测试段落：中文正文应完整分页。" for _ in range(30))}]
        with tempfile.TemporaryDirectory() as directory:
            files = exporter.render_pdf_export(messages, "fixture-test", directory, page_height=900)
            reader = PdfReader(files[0])
            self.assertGreater(len(reader.pages), 1)
            self.assertIn("中文导出测试", "".join(page.extract_text() for page in reader.pages))
            links = [item.get_object().get("/A", {}).get("/URI") for page in reader.pages for item in page.get("/Annots", [])]
            self.assertIn("https://example.com", links)


if __name__ == "__main__":
    unittest.main()
