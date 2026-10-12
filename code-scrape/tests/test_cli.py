"""
模块名称: CLI 端到端测试
文件名称: test_cli.py
模块类型: 测试
功能描述: 在临时项目上跑通 run/list/pack/stat/scan：清单产出、仅正文 md、
          对账恒等式、stats-json、退出码（1/2/3）与参数覆盖
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codescrape import cli, listing, reader  # noqa: E402

PROJECT_NAME = "演示系统"

FILES = {
    "backend/src/main/java/com/demo/DemoApplication.java":
        "package com.demo;\n\npublic class DemoApplication {\n"
        "    public static void main(String[] args) {\n        System.out.println(1);\n    }\n}\n",
    "backend/src/main/java/com/demo/service/UserService.java":
        "package com.demo.service;\n\npublic class UserService {\n"
        "    /* 说明\n       多行注释 */\n    public int add(int a, int b) {\n"
        "        return a + b; // 相加\n    }\n}\n",
    "frontend/src/main.js":
        "// 前端入口\nimport { createApp } from 'vue'\n\ncreateApp({}).mount('#app')\n",
    "pages/index/index.js": "Page({\n  data: {},\n})\n",
    "pages/index/index.wxml": "<view class=\"box\">\n  <!-- 首页 -->\n  <text>首页</text>\n</view>\n",
    "frontend/package.json": "{\n  \"name\": \"demo\"\n}\n",
    "backend/__init__.py": "",
    "README.md": "# 说明\n\n文档\n",
}

EXPECTED_ENTRIES = {
    "backend/src/main/java/com/demo/DemoApplication.java",
    "backend/src/main/java/com/demo/service/UserService.java",
    "frontend/src/main.js",
    "pages/index/index.js",
    "pages/index/index.wxml",
}


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for rel, text in FILES.items():
            p = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def read(self, *parts, encoding="utf-8"):
        with open(self.path(*parts), "r", encoding=encoding) as f:
            return f.read()

    def run_project(self, *extra):
        return self.run_cli(["run", "-r", self.root, "--project-name", PROJECT_NAME, *extra])


class RunCommandTest(CliBase):
    def test_run_produces_listing_and_body_only_md(self):
        code, out = self.run_project("--stats-json", "out/stats.json")
        self.assertEqual(code, 0, out)
        listing_text = self.read("out", "核心代码名称.md")
        entries = listing.parse_listing(listing_text)
        self.assertEqual(set(entries), EXPECTED_ENTRIES)
        self.assertEqual(entries[0], "backend/src/main/java/com/demo/DemoApplication.java")

        md = self.read("out", f"源代码-{PROJECT_NAME}.md")
        self.assertTrue(md.startswith("package com.demo;"))
        for token in ("软件著作权源代码文档", "文件总数", "代码总行数", "\n---\n"):
            self.assertNotIn(token, md)
        self.assertIn("[统计]", out)
        self.assertIn("[输出]", out)

        stats = json.loads(self.read("out", "stats.json"))
        self.assertEqual(stats["schema"], "codescrape/stats@1")
        self.assertEqual(stats["listing"]["entries"], len(entries))
        self.assertEqual(stats["listing"]["matched"], len(entries))
        self.assertEqual(stats["listing"]["missing"], [])
        self.assertTrue(stats["reconcile"]["ok"], stats["reconcile"])
        self.assertEqual(stats["totals"]["md_lines"], stats["md"]["body_lines"])
        self.assertEqual(stats["root"], self.root)

    def test_md_line_count_matches_stats(self):
        self.run_project("--stats-json", "out/stats.json")
        md = self.read("out", f"源代码-{PROJECT_NAME}.md")
        stats = json.loads(self.read("out", "stats.json"))
        body = md[:-1] if md.endswith("\n") else md
        self.assertEqual(body.count("\n") + 1, stats["md"]["body_lines"])

    def test_config_and_empty_package_and_docs_excluded(self):
        self.run_project()
        entries = set(listing.parse_listing(self.read("out", "核心代码名称.md")))
        for excluded in ("frontend/package.json", "backend/__init__.py", "README.md"):
            self.assertNotIn(excluded, entries)

    def test_reproducible_bytes(self):
        self.run_project()
        first = self.read("out", f"源代码-{PROJECT_NAME}.md")
        self.run_project()
        self.assertEqual(first, self.read("out", f"源代码-{PROJECT_NAME}.md"))

    def test_max_empty_lines_one_keeps_blank_and_identity(self):
        code, out = self.run_project("-k", "1", "--stats-json", "out/stats.json")
        self.assertEqual(code, 0, out)
        stats = json.loads(self.read("out", "stats.json"))
        self.assertGreater(stats["totals"]["blank"], 0)
        self.assertTrue(stats["reconcile"]["ok"], stats["reconcile"])
        self.assertEqual(stats["totals"]["phys"],
                         stats["totals"]["blank"] + stats["totals"]["comment"] + stats["totals"]["code"])

    def test_keep_header_writes_eight_legacy_lines(self):
        self.run_project("--keep-header")
        md = self.read("out", f"源代码-{PROJECT_NAME}.md")
        self.assertTrue(md.startswith("# 软件著作权源代码文档\n"))
        self.assertIn("- **文件总数**：5", md)
        self.assertIn("\n---\n", md)

    def test_with_file_headers_identity_still_holds(self):
        code, out = self.run_project("--with-file-headers", "--stats-json", "out/stats.json")
        self.assertEqual(code, 0, out)
        stats = json.loads(self.read("out", "stats.json"))
        self.assertEqual(stats["reconcile"]["separator_lines"], 5)
        self.assertTrue(stats["reconcile"]["ok"], stats["reconcile"])
        md = self.read("out", f"源代码-{PROJECT_NAME}.md")
        self.assertIn("// backend/src/main/java/com/demo/DemoApplication.java", md)
        self.assertIn("<!-- pages/index/index.wxml -->", md)

    def test_legacy_report_does_not_change_output(self):
        self.run_project()
        base = self.read("out", f"源代码-{PROJECT_NAME}.md")
        code, out = self.run_project("--legacy-report", "--stats-json", "out/stats.json")
        self.assertEqual(code, 0, out)
        self.assertIn("[旧版对照]", out)
        self.assertEqual(base, self.read("out", f"源代码-{PROJECT_NAME}.md"))
        stats = json.loads(self.read("out", "stats.json"))
        self.assertIsNotNone(stats["legacy"])
        self.assertEqual(stats["legacy"]["new_total"], stats["totals"]["code"])
        self.assertGreaterEqual(stats["legacy"]["changed_files"], 1)

    def test_dry_run_writes_nothing(self):
        code, out = self.run_project("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.path("out", "核心代码名称.md")))
        self.assertFalse(os.path.exists(self.path("out", f"源代码-{PROJECT_NAME}.md")))
        self.assertIn("dry-run", out)


class OtherCommandsTest(CliBase):
    def test_list_only_does_not_write_md(self):
        code, out = self.run_cli(["list", "-r", self.root, "--project-name", PROJECT_NAME])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(self.path("out", "核心代码名称.md")))
        self.assertFalse(os.path.exists(self.path("out", f"源代码-{PROJECT_NAME}.md")))

    def test_pack_without_listing_exits_1(self):
        code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME])
        self.assertEqual(code, 1)
        self.assertIn("清单不存在", out)

    def test_pack_auto_list_generates_listing(self):
        code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME,
                                  "--auto-list"])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(self.path("out", "核心代码名称.md")))
        self.assertTrue(os.path.exists(self.path("out", f"源代码-{PROJECT_NAME}.md")))

    def test_stat_does_not_write_md_but_writes_json(self):
        self.run_cli(["list", "-r", self.root, "--project-name", PROJECT_NAME])
        code, out = self.run_cli(["stat", "-r", self.root, "--project-name", PROJECT_NAME,
                                  "--stats-json", "out/stats.json"])
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.path("out", f"源代码-{PROJECT_NAME}.md")))
        stats = json.loads(self.read("out", "stats.json"))
        self.assertTrue(stats["reconcile"]["ok"])

    def test_scan_reports(self):
        code, out = self.run_cli(["scan", "-r", self.root, "--project-name", PROJECT_NAME])
        self.assertEqual(code, 0, out)
        for token in ("[扫描]", "[规则]", "[采集]", "[清单]", "[校验]"):
            self.assertIn(token, out)

    def test_missing_root_exits_1(self):
        code, out = self.run_cli(["run", "-r", self.path("no-such-dir")])
        self.assertEqual(code, 1)
        self.assertIn("项目根目录不存在", out)

    def test_empty_project_exits_1(self):
        with tempfile.TemporaryDirectory() as empty:
            code, out = self.run_cli(["run", "-r", empty])
            self.assertEqual(code, 1)
            self.assertIn("未采集到任何核心代码文件", out)


class ExitCodeTest(CliBase):
    def _prepare_listing_with_missing_entry(self):
        self.run_project()
        os.remove(self.path("backend", "src", "main", "java", "com", "demo", "service", "UserService.java"))

    def test_missing_entry_without_strict_warns_and_skips(self):
        self._prepare_listing_with_missing_entry()
        code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME,
                                  "--stats-json", "out/stats.json"])
        self.assertEqual(code, 0, out)
        stats = json.loads(self.read("out", "stats.json"))
        self.assertEqual(len(stats["listing"]["missing"]), 1)
        self.assertTrue(stats["reconcile"]["ok"], stats["reconcile"])

    def test_missing_entry_with_strict_exits_2_and_writes_nothing(self):
        self._prepare_listing_with_missing_entry()
        # 清掉上一轮 run 留下的文档，确认 --strict 被阻止时不会重新产出
        os.remove(self.path("out", f"源代码-{PROJECT_NAME}.md"))
        code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME,
                                  "--strict"])
        self.assertEqual(code, 2)
        self.assertIn("--strict", out)
        self.assertFalse(os.path.exists(self.path("out", f"源代码-{PROJECT_NAME}.md")))

    def test_unreadable_file_exits_3_with_placeholder(self):
        self.run_cli(["list", "-r", self.root, "--project-name", PROJECT_NAME])
        original = reader.read_file

        def fake_read(path, max_size_mb=50):
            if path.endswith("UserService.java"):
                return reader.ReadResult(None, "", "读取失败：PermissionError: 拒绝访问", 0)
            return original(path, max_size_mb)

        with mock.patch.object(cli.reader, "read_file", side_effect=fake_read), \
                mock.patch.object(reader, "read_file", side_effect=fake_read):
            code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME,
                                      "--stats-json", "out/stats.json"])
        self.assertEqual(code, 3, out)
        md = self.read("out", f"源代码-{PROJECT_NAME}.md")
        self.assertIn("[文件读取失败：backend/src/main/java/com/demo/service/UserService.java]", md)
        stats = json.loads(self.read("out", "stats.json"))
        self.assertEqual(stats["reconcile"]["placeholder_lines"], 1)
        self.assertTrue(stats["reconcile"]["ok"], stats["reconcile"])

    def test_unreadable_file_with_allow_partial_exits_0(self):
        self.run_cli(["list", "-r", self.root, "--project-name", PROJECT_NAME])
        original = reader.read_file

        def fake_read(path, max_size_mb=50):
            if path.endswith("UserService.java"):
                return reader.ReadResult(None, "", "读取失败：PermissionError", 0)
            return original(path, max_size_mb)

        with mock.patch.object(cli.reader, "read_file", side_effect=fake_read):
            code, out = self.run_cli(["pack", "-r", self.root, "--project-name", PROJECT_NAME,
                                      "--allow-partial"])
        self.assertEqual(code, 0, out)


class NamingTest(unittest.TestCase):
    def test_default_name_keeps_chinese_only(self):
        name, source = cli.resolve_project_name(r"E:\x\11- 星海验收系统 V2.0")
        self.assertEqual(name, "星海验收系统")
        self.assertIn("目录名", source)

    def test_fallback_name_when_no_chinese(self):
        name, _ = cli.resolve_project_name(r"E:\x\demo-app")
        self.assertEqual(name, "项目")

    def test_override_used_verbatim_and_sanitized(self):
        name, source = cli.resolve_project_name(r"E:\x\demo", "星海棉花收购系统 V1.0")
        self.assertEqual(name, "星海棉花收购系统 V1.0")
        self.assertIn("--project-name", source)
        name2, _ = cli.resolve_project_name(r"E:\x\demo", '有/非法:字符*')
        self.assertEqual(name2, "有_非法_字符_")


if __name__ == "__main__":
    unittest.main()
