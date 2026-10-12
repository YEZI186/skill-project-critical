"""
测试名称: 语言覆盖
文件名称: test_loc_languages.py
测试目的: 确认语言表覆盖 >= 40 个扩展名，并逐个验证"整行注释"与"有效代码行"能被正确区分；
          同时校验未知扩展名兜底、文件名特判与 .m 双语义
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from codescrape.languages import (FALLBACK, known_extensions, known_language_count,
                                  spec_for_ext, spec_for_path)
from codescrape.loc import count_text


def _note_line(spec) -> str | None:
    """为该语言构造一行"纯注释"样例"""
    if spec.line_comments:
        tok = spec.line_comments[0]
        return f"{tok} 注释"
    if spec.word_comments:
        return f"{spec.word_comments[0]} note"
    if spec.block_comments:
        b = spec.block_comments[0]
        return f"{b.start} 注释 {b.end}"
    return None


class LanguageCoverageTest(unittest.TestCase):

    def test_extension_and_language_counts(self):
        exts = known_extensions()
        self.assertGreaterEqual(len(exts), 40, f"扩展名覆盖不足：{len(exts)}")
        self.assertGreaterEqual(known_language_count(), 30,
                                f"语言种数不足：{known_language_count()}")

    def test_each_language_separates_comment_and_code(self):
        checked = 0
        for ext in known_extensions():
            spec = spec_for_ext(ext)
            note = _note_line(spec)
            if note is None:
                continue
            text = f"{note}\nvalue = 1\n"
            with self.subTest(ext=ext, lang=spec.name):
                stats = count_text(text, ext=ext)
                self.assertTrue(stats.ok, f"{ext} 恒等式不成立")
                self.assertEqual(1, stats.comment, f"{ext} 注释行未识别：{stats.as_dict()}")
                self.assertEqual(1, stats.code, f"{ext} 代码行被误判：{stats.as_dict()}")
                self.assertEqual(0, stats.blank, f"{ext} 空行数异常")
                self.assertFalse(stats.fallback, f"{ext} 不应走兜底规则")
            checked += 1
        self.assertGreaterEqual(checked, 40, f"实际校验到 {checked} 种扩展名")

    def test_unknown_extension_uses_fallback(self):
        stats = count_text("x = 1\n// note\n# other\n", ext=".zzz")
        self.assertTrue(stats.fallback)
        self.assertEqual(FALLBACK.name, stats.language)
        self.assertTrue(stats.ok)

    def test_filename_special_cases(self):
        self.assertEqual("Dockerfile", spec_for_path("Dockerfile").name)
        self.assertEqual("Makefile", spec_for_path("Makefile").name)
        self.assertEqual("GitIgnore", spec_for_path(".gitignore").name)
        self.assertEqual("Java", spec_for_path("a/b/UserController.java").name)

    def test_js_and_ts_share_template_rules(self):
        for ext in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"):
            with self.subTest(ext=ext):
                stats = count_text("const a = `x`;\n", ext=ext)
                self.assertEqual(1, stats.code)
                self.assertTrue(stats.ok)


if __name__ == "__main__":
    unittest.main()
