"""
测试名称: 黄金样例（fixtures + expected.json）
文件名称: test_loc_fixtures.py
测试目的: 用人工逐行核对过期望值的真实语言样例，锁定四口径统计结果与恒等式
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from codescrape.loc import classify_lines, count_text
from codescrape.languages import spec_for_path

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class FixtureGoldenTest(unittest.TestCase):
    """fixtures 目录下的语言样例必须与 expected.json 完全一致"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIXTURES, "expected.json"), encoding="utf-8") as f:
            cls.expected = json.load(f)

    def _read(self, name):
        with open(os.path.join(FIXTURES, name), encoding="utf-8-sig") as f:
            return f.read()

    def test_expected_table_not_empty(self):
        self.assertGreaterEqual(len(self.expected), 6)

    def test_four_metrics_match_expectation(self):
        for name, want in self.expected.items():
            with self.subTest(fixture=name):
                text = self._read(name)
                stats = count_text(text, path=os.path.join(FIXTURES, name))
                got = {"phys": stats.phys, "blank": stats.blank,
                       "comment": stats.comment, "code": stats.code}
                self.assertEqual(want, got, f"{name}: {stats.as_dict()}")
                self.assertTrue(stats.ok, f"{name} 恒等式不成立")

    def test_every_fixture_has_code(self):
        for name in self.expected:
            with self.subTest(fixture=name):
                stats = count_text(self._read(name), path=name)
                self.assertGreater(stats.code, 0)
                self.assertFalse(stats.fallback, f"{name} 不应走兜底规则")
                self.assertEqual([], stats.warnings, f"{name} 不应有警告")

    def test_java_string_does_not_swallow_following_lines(self):
        """回归防护：Java 字符串里的 /** 不得把后续行当成块注释"""
        text = self._read("UserController.java")
        kinds = classify_lines(text, spec_for_path("UserController.java"))[0]
        markers = [ln for ln in text.split("\n")]
        idx = next(i for i, ln in enumerate(markers) if '"/api/**"' in ln)
        self.assertEqual("code", kinds[idx])
        self.assertEqual("code", kinds[idx + 1], "字符串内的 /** 之后的行被吞掉了")

    def test_vue_script_comment_is_comment(self):
        """回归防护：.vue 的 <script> 区块内 // 必须算注释行"""
        text = self._read("ProfileCard.vue")
        kinds = classify_lines(text, spec_for_path("ProfileCard.vue"))[0]
        lines = text.split("\n")
        idx = next(i for i, ln in enumerate(lines) if ln.strip() == "// 组件逻辑")
        self.assertEqual("comment", kinds[idx])
        tpl_idx = next(i for i, ln in enumerate(lines) if "<!-- 卡片标题 -->" in ln)
        self.assertEqual("comment", kinds[tpl_idx])

    def test_wxml_html_comment_is_comment(self):
        text = self._read("detail.wxml")
        kinds = classify_lines(text, spec_for_path("detail.wxml"))[0]
        lines = text.split("\n")
        idx = next(i for i, ln in enumerate(lines) if "<!--" in ln)
        self.assertEqual("comment", kinds[idx])

    def test_sql_double_dash_is_comment(self):
        text = self._read("report.sql")
        kinds = classify_lines(text, spec_for_path("report.sql"))[0]
        lines = text.split("\n")
        idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("--"))
        self.assertEqual("comment", kinds[idx])


if __name__ == "__main__":
    unittest.main()
