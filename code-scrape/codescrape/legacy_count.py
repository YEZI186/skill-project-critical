"""
模块名称: 旧版行数算法快照（只读参考）
文件名称: legacy_count.py
模块类型: 参考模块
功能描述: 原 `processor.count_code_lines`（V1.6；源文件已随 P7 清理删除）的**原样快照**，
          仅供 `--legacy-report` 输出对照数字与差异归因使用。

【重要约束（D8 已定稿）】
  - 本模块**不参与任何正式产出**：四口径统计与汇总 md 一律走 `codescrape/loc.py`（新实现）；
  - **不提供**"按旧口径计数"的开关，本快照只读、只用于对照展示；
  - 已知缺陷原样保留（不修复），这些缺陷正是历史材料数字与新实现差异的来源：
      ① 字符串内部的 `/*`、`/**` 会被当成块注释开始，且无 `*/` 收尾时**吞掉文件后续所有行**；
      ② 注释规则按扩展名硬编码，`.wxml`/`.axml` 完全没有分支（HTML 注释被计为代码）；
      ③ `.vue` 只认 `<!-- -->`，`<script>` 内的 JS 行注释被计为代码；
      ④ `.sql` 只配了 `//`，不认 `--` 行注释；
      ⑤ 未建模的语言（如 `.yaml` 以外的配置语法、`.kt` 之外的新语言）无注释识别；
      ⑥ 多行字符串（Python 三引号/docstring）与混合行的判定与新实现口径不同。
"""


def count_code_lines(content: str, ext: str) -> int:
    """统计非注释有效代码行数（V1.6 原实现，原样保留）

    注意：入参 content 必须是**清洗后**（换行归一 + 空行压缩 + 行尾清理）的文本，
    才能与新版四口径的 code 数字可比。
    """
    ext = ext.lower()
    single_prefixes: list[str] = []
    multi_start = ""
    multi_end = ""

    if ext in (".java", ".c", ".cpp", ".h", ".hpp", ".js", ".ts", ".jsx", ".tsx",
               ".go", ".rs", ".cs", ".kt", ".swift", ".php", ".css", ".scss",
               ".less", ".m", ".mm", ".sql"):
        single_prefixes = ["//"]
        multi_start = "/*"
        multi_end = "*/"
    elif ext == ".py":
        single_prefixes = ["#"]
        multi_start = '"""'  # 同时处理 ''' 和 """
        multi_end = '"""'
    elif ext in (".rb", ".sh", ".bat", ".ps1", ".yaml", ".yml", ".toml"):
        single_prefixes = ["#"]
    elif ext == ".vb":
        single_prefixes = ["'"]
    elif ext in (".html", ".xml", ".vue"):
        single_prefixes = []
        multi_start = "<!--"
        multi_end = "-->"
    elif ext == ".json":
        return sum(1 for l in content.split("\n") if l.strip())

    lines = content.split("\n")
    count = 0
    in_multi = False

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 在多行注释内部
        if in_multi:
            end_pos = s.find(multi_end)
            if end_pos != -1:
                in_multi = False
                s = s[end_pos + len(multi_end):].strip()
                if not s:
                    continue
                # 同行继续处理剩余代码
            else:
                continue

        # Python 三引号多行处理
        if ext == ".py" and not in_multi:
            for q in ('"""', "'''"):
                pos = s.find(q)
                if pos != -1:
                    # 检查是否是独立的三引号行（纯注释）
                    before = s[:pos].strip()
                    if not before:
                        # 查找配对的结束三引号
                        end_pos = s.find(q, pos + 3)
                        if end_pos != -1:
                            after = s[end_pos + 3:].strip()
                            if after:
                                count += 1
                        else:
                            in_multi = True
                            multi_end = q
                        break
                    else:
                        # 三引号前有代码，查找其后是否有结束符
                        end_pos = s.find(q, pos + 3)
                        if end_pos == -1:
                            count += 1
                            in_multi = True
                            multi_end = q
                            break
                        else:
                            count += 1
                            break
            if in_multi:
                continue

        # 单行注释前缀
        if single_prefixes:
            if any(s.startswith(p) for p in single_prefixes):
                continue

        # 多行注释开始
        if multi_start and multi_start in s and not in_multi:
            idx = s.index(multi_start)
            before = s[:idx].strip()
            if not before:
                # 纯注释开头
                rest = s[idx + len(multi_start):]
                if multi_end and multi_end in rest:
                    after = rest[rest.index(multi_end) + len(multi_end):].strip()
                    if after:
                        count += 1
                else:
                    in_multi = True
                continue
            else:
                # 注释前有代码
                count += 1
                if multi_end and multi_end not in s[idx + len(multi_start):]:
                    in_multi = True
                continue

        count += 1

    return count
