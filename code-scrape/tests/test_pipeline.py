"""
模块名称: 汇总链路单元测试
文件名称: test_pipeline.py
模块类型: 测试
功能描述: 覆盖 reader（编码链/换行归一）、cleaner（空行压缩/行尾清理）、
          markdown（仅正文/分隔行/旧版头部/失败占位）、report（四口径/对账/JSON）
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codescrape import cleaner, legacy_count, loc, markdown, reader, report  # noqa: E402


class LegacySnapshotTest(unittest.TestCase):
    """V1.6 只读快照必须保留旧缺陷（这正是 --legacy-report 差异的来源）"""

    def test_wxml_html_comment_counted_as_code_by_legacy(self):
        text = "<view>a</view>\n<!-- 注释 -->\n<view>b</view>"
        self.assertEqual(legacy_count.count_code_lines(text, ".wxml"), 3)
        self.assertEqual(loc.count_text(text, ext=".wxml").code, 2)

    def test_string_containing_block_comment_swallows_following_lines(self):
        text = 'String sql = "/* hint";\nint a = 1;\nint b = 2;'
        self.assertEqual(legacy_count.count_code_lines(text, ".java"), 1)
        self.assertEqual(loc.count_text(text, ext=".java").code, 3)

    def test_sql_double_dash_not_recognized_by_legacy(self):
        text = "-- 注释\nSELECT 1;"
        self.assertEqual(legacy_count.count_code_lines(text, ".sql"), 2)
        self.assertEqual(loc.count_text(text, ext=".sql").code, 1)

    def test_vue_script_comment_not_recognized_by_legacy(self):
        text = "<script>\n// 注释\nconst a = 1\n</script>"
        self.assertGreater(legacy_count.count_code_lines(text, ".vue"),
                           loc.count_text(text, ext=".vue").code)


class LegacyCompareTest(unittest.TestCase):
    def _stats(self):
        return [
            report.FileStat(path="a/WebConfig.java", ext=".java", phys=47, comment=0, code=47),
            report.FileStat(path="pages/index.wxml", ext=".wxml", phys=3, comment=1, code=2),
            report.FileStat(path="same.py", ext=".py", phys=1, comment=0, code=1),
            report.FileStat(path="bad.py", ext=".py", failed=True),
        ]

    def test_compare_totals_groups_and_reasons(self):
        legacy = report.legacy_compare(self._stats(),
                                       {"a/WebConfig.java": 26, "pages/index.wxml": 3,
                                        "same.py": 1, "bad.py": 0})
        self.assertEqual(legacy["old_total"], 30)
        self.assertEqual(legacy["new_total"], 50)
        self.assertEqual(legacy["delta"], 20)
        self.assertEqual(legacy["changed_files"], 2)
        self.assertEqual(legacy["compared_files"], 3)      # 失败文件不参与对照
        reasons = {g["reason"] for g in legacy["groups"]}
        self.assertIn("旧算法把字符串内的注释符当作注释开始，吞掉后续行", reasons)
        self.assertIn("旧算法未识别 HTML 注释（<!-- -->）", reasons)
        # 差异大的排前面
        self.assertEqual(legacy["rows"][0]["path"], "a/WebConfig.java")
        self.assertEqual(legacy["rows"][0]["delta"], 21)

    def test_console_renders_legacy_lines_when_enabled(self):
        doc = markdown.build([("same.py", "x = 1")])
        legacy = report.legacy_compare(self._stats(), {"same.py": 1})
        stats = report.build_stats(root="/tmp/x", project_name="演示",
                                   project_name_source="cwd", listing_info={},
                                   file_stats=self._stats(), doc=doc, legacy=legacy)
        text = "\n".join(report.console_lines(stats, verbose=True, root="/tmp/x"))
        self.assertIn("[旧版对照]", text)
        self.assertNotIn("[旧版对照]", "\n".join(
            report.console_lines(report.build_stats(
                root="/tmp/x", project_name="演示", project_name_source="cwd",
                listing_info={}, file_stats=self._stats(), doc=doc), root="/tmp/x")))


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data: bytes) -> str:
        p = os.path.join(self.root, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_crlf_and_cr_normalized(self):
        p = self._write("a.java", "class A {\r\n  int a = 1;\r  int b = 2;\r\n}\r\n".encode("utf-8"))
        rr = reader.read_file(p)
        self.assertTrue(rr.ok)
        self.assertNotIn("\r", rr.text)
        self.assertEqual(rr.text, "class A {\n  int a = 1;\n  int b = 2;\n}\n")

    def test_utf8_bom_reported(self):
        p = self._write("a.py", "\ufeff# 注释\nx = 1\n".encode("utf-8"))
        rr = reader.read_file(p)
        self.assertEqual(rr.encoding, "utf-8-sig")
        self.assertEqual(rr.text, "# 注释\nx = 1\n")

    def test_gb18030_fallback(self):
        p = self._write("a.java", "// 中文注释\nclass A {}\n".encode("gb18030"))
        rr = reader.read_file(p)
        self.assertTrue(rr.ok)
        self.assertIn("中文注释", rr.text)
        self.assertIn(rr.encoding, ("gb18030", "gbk"))

    def test_latin1_last_resort_warns(self):
        p = self._write("a.bin", b"\x80\x80\x80\x80")
        rr = reader.read_file(p)
        self.assertTrue(rr.ok)
        self.assertEqual(rr.encoding, "latin-1")
        self.assertIn("latin-1", rr.warning)

    def test_missing_file_fails(self):
        rr = reader.read_file(os.path.join(self.root, "nope.java"))
        self.assertFalse(rr.ok)
        self.assertIn("读取失败", rr.warning)


class CleanerTest(unittest.TestCase):
    def test_remove_all_blank_lines_default(self):
        text = "a\n\n\nb\n\n\n"
        self.assertEqual(cleaner.clean_text(text, max_empty_lines=0), "a\nb")

    def test_keep_one_blank_line(self):
        text = "a\n\n\n\nb\n"
        self.assertEqual(cleaner.clean_text(text, max_empty_lines=1), "a\n\nb")

    def test_keep_two_blank_lines(self):
        text = "a\n\n\n\nb\n"
        self.assertEqual(cleaner.clean_text(text, max_empty_lines=2), "a\n\n\nb")

    def test_leading_blank_lines_dropped(self):
        self.assertEqual(cleaner.clean_text("\n\n\na\nb\n", max_empty_lines=2), "a\nb")

    def test_trailing_whitespace_trimmed_indent_kept(self):
        text = "    def f():   \n\t\treturn 1 \n"
        self.assertEqual(cleaner.clean_text(text), "    def f():\n\t\treturn 1")

    def test_line_count_matches_loc(self):
        text = "a\nb\nc\n"
        self.assertEqual(cleaner.line_count(text), loc.count_text(text, ext=".py").phys)
        self.assertEqual(cleaner.line_count(""), 0)


class MarkdownTest(unittest.TestCase):
    def test_body_only_no_header(self):
        doc = markdown.build([("a.java", "class A {}"), ("b.py", "x = 1")])
        self.assertEqual(doc.header, "")
        self.assertEqual(doc.header_lines, 0)
        self.assertEqual(doc.text(), "class A {}\nx = 1\n")
        self.assertEqual(doc.body_lines, 2)

    def test_separator_lines_not_counted_in_body_stats(self):
        doc = markdown.build([("a.java", "class A {}"), ("b.py", "x = 1")],
                             with_file_headers=True)
        self.assertEqual(doc.separator_lines, 2)
        self.assertEqual(doc.body_lines, 4)          # 2 源码行 + 2 分隔行
        self.assertIn("// a.java", doc.body)
        self.assertIn("# b.py", doc.body)

    def test_separator_comment_prefix_by_language(self):
        self.assertEqual(markdown.header_line("a.java"), "// a.java")
        self.assertEqual(markdown.header_line("a.py"), "# a.py")
        self.assertEqual(markdown.header_line("a.wxml"), "<!-- a.wxml -->")
        self.assertEqual(markdown.header_line("a.vue"), "<!-- a.vue -->")
        self.assertEqual(markdown.header_line("a.sql"), "-- a.sql")
        self.assertEqual(markdown.header_line("a.unknown-ext"), "# a.unknown-ext")

    def test_failed_placeholder_counts_one_line(self):
        doc = markdown.build([("a.java", "class A {}"), ("b.py", None)])
        self.assertEqual(doc.placeholder_lines, 1)
        self.assertEqual(doc.body_lines, 2)
        self.assertIn("[文件读取失败：b.py]", doc.body)

    def test_empty_file_contributes_zero_lines(self):
        doc = markdown.build([("a.java", "class A {}"), ("b.py", "")])
        self.assertEqual(doc.body_lines, 1)
        self.assertEqual(doc.placeholder_lines, 0)

    def test_legacy_header_is_eight_lines(self):
        doc = markdown.build([("a.java", "class A {}")], project_name="演示系统",
                             keep_header=True, legacy_code_lines=1, legacy_file_count=1)
        self.assertEqual(doc.header_lines, 8)
        self.assertIn("# 软件著作权源代码文档", doc.header)
        self.assertIn("- **文件总数**：1", doc.header)
        self.assertTrue(doc.text().startswith("# 软件著作权源代码文档"))

    def test_empty_doc_text_is_empty(self):
        doc = markdown.build([])
        self.assertEqual(doc.text(), "")
        self.assertEqual(doc.body_lines, 0)


class ReportTest(unittest.TestCase):
    def _doc_and_stats(self):
        pairs = [("a.java", "class A {}"), ("b.py", None)]
        doc = markdown.build(pairs)
        stats = [
            report.FileStat(path="a.java", ext=".java", encoding="utf-8",
                            phys=1, blank=0, comment=0, code=1, language="Java"),
            report.FileStat(path="b.py", ext=".py", failed=True),
        ]
        return doc, stats

    def test_reconcile_identity_holds(self):
        doc, file_stats = self._doc_and_stats()
        rec = report.reconcile(doc, file_stats)
        self.assertEqual(rec["md_body_lines"], 2)
        self.assertEqual(rec["sum_file_phys"], 1)
        self.assertEqual(rec["placeholder_lines"], 1)
        self.assertTrue(rec["ok"])

    def test_reconcile_detects_mismatch(self):
        doc = markdown.build([("a.java", "class A {}\nclass B {}")])
        rec = report.reconcile(doc, [report.FileStat(path="a.java", ext=".java", phys=1)])
        self.assertFalse(rec["ok"])

    def test_build_stats_schema_and_totals(self):
        doc, file_stats = self._doc_and_stats()
        stats = report.build_stats(root="/tmp/x", project_name="演示",
                                   project_name_source="--project-name",
                                   listing_info={"path": "/tmp/x/out/核心代码名称.md",
                                                 "entries": 2, "matched": 1,
                                                 "missing": [], "invalid": [],
                                                 "backend": 1, "frontend": 0},
                                   file_stats=file_stats, doc=doc, md_path="/tmp/x/out/源代码-演示.md")
        self.assertEqual(stats["schema"], "codescrape/stats@1")
        self.assertEqual(stats["totals"]["files"], 1)
        self.assertEqual(stats["totals"]["md_lines"], 2)
        self.assertEqual(stats["totals"]["pages"], round(2 / 50, 1))
        self.assertEqual(stats["by_language"][0]["ext"], ".java")
        self.assertTrue(stats["reconcile"]["ok"])

    def test_console_lines_contain_key_sections(self):
        doc, file_stats = self._doc_and_stats()
        stats = report.build_stats(root="/tmp/x", project_name="演示",
                                   project_name_source="--project-name",
                                   listing_info={"path": "/tmp/x/out/核心代码名称.md",
                                                 "entries": 2, "matched": 1, "missing": [],
                                                 "invalid": [], "backend": 1, "frontend": 0},
                                   file_stats=file_stats, doc=doc)
        text = "\n".join(report.console_lines(stats, root="/tmp/x"))
        for token in ("[完成]", "[清单]", "[统计]", "[语言]", "[输出]", "[提示]"):
            self.assertIn(token, text)
        self.assertIn("有效代码行 1", text)
        quiet = "\n".join(report.console_lines(stats, quiet=True, root="/tmp/x"))
        self.assertEqual(quiet.count("\n"), 0)
        self.assertIn("[输出]", quiet)

    def test_write_json_roundtrip(self):
        doc, file_stats = self._doc_and_stats()
        stats = report.build_stats(root="/tmp/x", project_name="演示",
                                   project_name_source="cwd", listing_info={},
                                   file_stats=file_stats, doc=doc)
        with tempfile.TemporaryDirectory() as tmp:
            path = report.write_json(stats, os.path.join(tmp, "stats.json"))
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        self.assertEqual(loaded["schema"], "codescrape/stats@1")
        self.assertTrue(loaded["reconcile"]["ok"])


if __name__ == "__main__":
    unittest.main()
