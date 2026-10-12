"""
模块名称: 文本清洗
文件名称: cleaner.py
模块类型: 核心模块
功能描述: 写入 md 前的文本清洗：空行压缩（0/1/2）、行尾空白清理、保留行首缩进。
          清洗后的文本即行数统计的唯一输入（统计与产物同源，见方案 6.5 对账口径）。
"""

from .reader import normalize_newlines


def clean_text(text: str, max_empty_lines: int = 0,
               trim_trailing: bool = True) -> str:
    """清洗文本，返回换行归一 + 空行压缩 + 行尾清理后的结果

    max_empty_lines: 保留的连续空行数（0 = 不留空行）；文件首尾空行一律不计
    trim_trailing  : 仅去行尾空白，行首缩进原样保留
    """
    text = normalize_newlines(text)
    if not text:
        return ""
    keep = max(0, int(max_empty_lines))
    out: list[str] = []
    pending_blank = 0
    for line in text.split("\n"):
        s = line.rstrip() if trim_trailing else line
        if not s.strip():
            pending_blank += 1
            continue
        if pending_blank and out:
            out.extend([""] * min(pending_blank, keep))
        pending_blank = 0
        out.append(s)
    return "\n".join(out)


def line_count(text: str) -> int:
    """物理行数：与 loc 口径一致（末尾换行不计行、空文本 0 行）"""
    if not text:
        return 0
    body = text[:-1] if text.endswith("\n") else text
    return body.count("\n") + 1
