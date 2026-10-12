"""
模块名称: Markdown 组装
文件名称: markdown.py
模块类型: 核心模块
功能描述: 把清洗后的源码正文按清单顺序连续拼接成汇总 md。
          默认**只含源码正文**（无标题、无统计列表、无 --- 分隔线）；
          --with-file-headers 插入的路径注释行与 --keep-header 的旧版头部均不计入统计口径。
"""

from dataclasses import dataclass, field

from .languages import FALLBACK, spec_for_path

# 读取失败时写入正文的占位行（一行，参与对账恒等式）
FAILED_TEMPLATE = "[文件读取失败：{path}]"
# 旧版头部标题（仅 --keep-header 时使用，D4 已裁定默认不写）
LEGACY_TITLE = "# 软件著作权源代码文档"


@dataclass
class BuiltDoc:
    """汇总文档的构建结果与对账所需的全部计数"""
    header: str = ""
    body: str = ""
    header_lines: int = 0
    body_lines: int = 0
    placeholder_lines: int = 0     # 读取失败占位行数
    separator_lines: int = 0       # --with-file-headers 插入的路径行数
    file_count: int = 0            # 参与拼接的条目数（含失败条目）
    failed: list[tuple[str, str]] = field(default_factory=list)

    def text(self) -> str:
        """最终写盘文本：旧版头部（可选）+ 源码正文 + 结尾换行"""
        if not self.header and not self.body:
            return ""
        return self.header + self.body + ("\n" if self.body else "")


def comment_prefix(path: str) -> str:
    """按语言表给路径分隔行挑注释前缀；未知语言用 #（方案 6.5）"""
    spec = spec_for_path(path)
    if spec is FALLBACK:
        return "#"
    if spec.line_comments:
        return spec.line_comments[0]
    if spec.block_comments:
        return spec.block_comments[0].start
    return "#"


def header_line(path: str) -> str:
    """生成路径分隔注释行（不计入统计）"""
    spec = spec_for_path(path)
    if spec is FALLBACK:
        return f"# {path}"
    if spec.line_comments:
        return f"{spec.line_comments[0]} {path}"
    if spec.block_comments:
        bc = spec.block_comments[0]
        return f"{bc.start} {path} {bc.end}"
    return f"# {path}"


def failed_placeholder(path: str) -> str:
    return FAILED_TEMPLATE.format(path=path)


def legacy_header(project_name: str, file_count: int, code_lines: int) -> str:
    """旧版头部（标题 + 统计列表 + 分隔线 + 空行），共 8 行，与历史产物逐行一致

    末尾空行（第 8 行）的换行符必须在头部内，否则正文首行会上移一行。
    """
    lines = [LEGACY_TITLE, ""]
    if project_name:
        lines.append(f"- **项目名称**：{project_name} V1.0  ")
    lines.append(f"- **文件总数**：{file_count}  ")
    lines.append(f"- **代码总行数**：{code_lines}（有效代码，已扣除注释和空行）  ")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


def _count_lines(text: str) -> int:
    """物理行数：末尾换行不计行、空串 0 行（与 loc 口径一致）"""
    if not text:
        return 0
    body = text[:-1] if text.endswith("\n") else text
    return body.count("\n") + 1


def build(pairs, project_name: str = "", with_file_headers: bool = False,
          keep_header: bool = False, legacy_code_lines: int = 0,
          legacy_file_count: int | None = None) -> BuiltDoc:
    """按清单顺序拼接正文

    pairs: 可迭代的 (relpath, cleaned_text | None)，text 为 None 表示读取失败
    """
    parts: list[str] = []
    placeholders = 0
    separators = 0
    failed: list[tuple[str, str]] = []
    count = 0
    for relpath, text in pairs:
        count += 1
        if with_file_headers:
            parts.append(header_line(relpath))
            separators += 1
        if text is None:
            parts.append(failed_placeholder(relpath))
            placeholders += 1
            failed.append((relpath, "读取失败"))
        elif text:
            parts.append(text)
    body = "\n".join(parts)
    doc = BuiltDoc(
        body=body,
        body_lines=_count_lines(body),
        placeholder_lines=placeholders,
        separator_lines=separators,
        file_count=count,
        failed=failed,
    )
    if keep_header:
        doc.header = legacy_header(project_name,
                                   legacy_file_count if legacy_file_count is not None else count,
                                   legacy_code_lines)
        doc.header_lines = _count_lines(doc.header)
    return doc
