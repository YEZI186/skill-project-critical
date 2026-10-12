"""
测试名称: 边界行为用例
文件名称: test_loc_boundaries.py
测试目的: 覆盖会暴露旧实现缺陷的边界场景：字符串内注释符、嵌套块注释、行首块注释、
          heredoc、跨行字符串、未闭合容错、混合行、CRLF、空文件、纯注释文件等
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from codescrape.loc import BLANK, CODE, COMMENT, classify_lines, count_text
from codescrape.languages import spec_for_ext, spec_for_path

# (用例名, 扩展名, 文本, 期望 (phys, blank, comment, code))
CASES = [
    ("java-string-opens-block", ".java",
     'String sql = "/* hint";\nint a = 1;\nint b = 2;\n', (3, 0, 0, 3)),
    ("java-ant-path-in-string", ".java",
     'registry.addMapping("/**")\n.allowedMethods("GET")\n;\n', (3, 0, 0, 3)),
    ("wxml-html-comment", ".wxml",
     '<view>a</view>\n<!-- note -->\n<view>b</view>\n', (3, 0, 1, 2)),
    ("vue-script-comment", ".vue",
     '<script>\n// note\nexport default {}\n</script>\n', (4, 0, 1, 3)),
    ("sql-double-dash", ".sql",
     'SELECT 1; -- note\n-- full\nSELECT 2;\n', (3, 0, 1, 2)),
    ("python-docstring", ".py",
     'def f():\n    """doc\n    more"""\n    return 1\n', (4, 0, 2, 2)),
    ("rust-nested-block", ".rs",
     '/* a /* b */ c */\nlet x = 1;\n', (2, 0, 1, 1)),
    ("unclosed-block-comment", ".c",
     'int a = 1; /* never closed\nint b = 2;\n', (2, 0, 1, 1)),
    ("shell-heredoc", ".sh",
     'cat <<EOF\nhello\nEOF\necho done\n', (4, 0, 2, 2)),
    ("empty-file", ".py", "", (0, 0, 0, 0)),
    ("blank-lines", ".py",
     'a = 1\n\n\nb = 2\n', (4, 2, 0, 2)),
    ("python-inline-comment-line", ".py",
     'x = 1  # note\n# full\n', (2, 0, 1, 1)),
    ("html-attr-contains-comment-token", ".html",
     '<a title="<!--x-->">y</a>\n', (1, 0, 0, 1)),
    ("kotlin-triple-quote", ".kt",
     'val s = """\nabc\n"""\nval n = 1\n', (4, 0, 2, 2)),
    ("js-template-single-line", ".js",
     'const t = `a${b}c`;\n', (1, 0, 0, 1)),
    ("js-template-multi-line", ".js",
     'const t = `\nline\n`;\n', (3, 0, 1, 2)),
    ("ruby-begin-end", ".rb",
     'x = 1\n=begin\nnote\n=end\ny = 2\n', (5, 0, 3, 2)),
    ("batch-rem-word-boundary", ".bat",
     'REM note\necho hi\n:: other\nREMOTE=1\n', (4, 0, 2, 2)),
    ("unknown-extension-fallback", ".zzz",
     'x = 1\n// note\n# other\n', (3, 0, 2, 1)),
    ("yaml-hash", ".yml",
     'a: 1\n# note\n', (2, 0, 1, 1)),
    ("comment-only-file", ".java",
     '// a\n/* b\n c */\n', (3, 0, 3, 0)),
    ("crlf-input-tolerated", ".java",
     'int a = 1;\r\n// note\r\nint b = 2;\r\n', (3, 0, 1, 2)),
    ("java-doc-comment", ".java",
     '/**\n * 说明\n */\npublic class A {}\n', (4, 0, 3, 1)),
    ("python-raw-string-escape", ".py",
     'p = r"C:\\path\\"\nprint(p)\n', (2, 0, 0, 2)),
    ("shell-heredoc-quoted", ".sh",
     "cat <<'EOF'\n$a literal\nEOF\n", (3, 0, 2, 1)),
]


class BoundaryTest(unittest.TestCase):

    def test_all_cases(self):
        for name, ext, text, want in CASES:
            with self.subTest(case=name):
                stats = count_text(text, ext=ext)
                got = (stats.phys, stats.blank, stats.comment, stats.code)
                self.assertEqual(want, got, f"{name}: {stats.as_dict()}")
                self.assertTrue(stats.ok, f"{name} 恒等式不成立")

    def test_classify_line_kinds(self):
        kinds, _ = classify_lines('int a = 1; // c\n// b\n\n', spec_for_ext(".java"))
        self.assertEqual([CODE, COMMENT, BLANK], kinds)

    def test_unclosed_block_records_warning(self):
        stats = count_text('int a = 1; /* never closed\n', ext=".c")
        self.assertTrue(stats.warnings)
        self.assertTrue(stats.ok)

    def test_unclosed_single_line_string_recovers(self):
        """未闭合单行字符串：按行收尾，后续行不得被吞"""
        stats = count_text('x = "unterminated\nint b = 2;\n', ext=".java")
        self.assertTrue(stats.warnings)
        self.assertEqual(2, stats.phys)
        self.assertEqual(2, stats.code, "未闭合字符串吞掉了后续行")

    def test_matlab_objc_sniffing(self):
        objc = '#import <Foundation/Foundation.h>\n@interface A\n@end\n'
        matlab = 'function y = f(x)\n% 注释\ny = x + 1;\nend\n'
        self.assertEqual("Objective-C-M", count_text(objc, ext=".m").language)
        self.assertEqual("Matlab", count_text(matlab, ext=".m").language)

    def test_sfc_keeps_template_and_style_lines(self):
        text = ("<template>\n  <div>a</div>\n</template>\n"
                "<script>\n// c\nlet x = 1;\n</script>\n"
                "<style>\n.a { color: red; }\n</style>\n")
        stats = count_text(text, ext=".vue")
        self.assertEqual(10, stats.phys)
        self.assertEqual(1, stats.comment)
        self.assertEqual(9, stats.code)
        self.assertTrue(stats.ok)


if __name__ == "__main__":
    unittest.main()
