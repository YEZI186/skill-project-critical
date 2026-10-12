"""
模块名称: 文本读取
文件名称: reader.py
模块类型: 核心模块
功能描述: 二进制读取 + 编码候选链识别 + 换行归一（\\r\\n / \\r → \\n）。
          零第三方依赖：不引入 chardet，按 UTF-8 → GB18030 → GBK → Big5 → latin-1 依次尝试。
          统计对象与写入 md 的文本同源，因此读取结果直接进入清洗与统计链路。
"""

import codecs
import os
from dataclasses import dataclass, field

# 编码候选链（顺序即优先级；latin-1 永不失败，作为兜底）
ENCODINGS = ("utf-8", "gb18030", "gbk", "big5")

# 单文件读取上限（防御性，不作为正常路径）：256 MB
HARD_READ_LIMIT = 256 * 1024 * 1024


@dataclass(frozen=True)
class ReadResult:
    """单个文件的读取结果"""
    text: str | None            # 换行归一后的文本；None 表示读取/解码失败
    encoding: str               # 最终采用的编码
    warning: str                # 告警（空串表示无）
    size: int                   # 字节数
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.text is not None


def normalize_newlines(text: str) -> str:
    """换行归一：CRLF / CR → LF（不做其它任何改写）"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_bytes(raw: bytes) -> tuple[str | None, str, str]:
    """按候选链解码，返回 (文本, 编码, 告警)；全部失败返回 (None, "", 原因)"""
    if raw.startswith(codecs.BOM_UTF8):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig", ""
        except UnicodeDecodeError:
            pass
    elif raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        enc = "utf-16-le" if raw.startswith(codecs.BOM_UTF16_LE) else "utf-16-be"
        try:
            return raw.decode(enc), enc + "(BOM)", ""
        except UnicodeDecodeError:
            pass
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc, ""
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("latin-1"), "latin-1", "非 UTF-8/GB18030/Big5 文本，已按 latin-1 兜底解码（可能乱码）"
    except Exception as e:  # pragma: no cover - latin-1 理论无失败分支
        return None, "", f"解码失败：{type(e).__name__}: {e}"


def read_file(path: str, max_size_mb: int | float = 50) -> ReadResult:
    """读取单个文件：返回换行归一后的文本 + 最终编码 + 告警"""
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return ReadResult(None, "", f"读取失败：{type(e).__name__}: {e}", 0)
    warnings: list[str] = []
    if max_size_mb and size > float(max_size_mb) * 1024 * 1024:
        warnings.append(f"文件 {size / 1048576:.1f} MB，超过 {max_size_mb} MB 阈值")
    if size > HARD_READ_LIMIT:
        return ReadResult(None, "", f"读取失败：文件 {size / 1048576:.1f} MB 超过 {HARD_READ_LIMIT // 1048576} MB 硬上限", size)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return ReadResult(None, "", f"读取失败：{type(e).__name__}: {e}", size)
    text, enc, warn = decode_bytes(raw)
    if warn:
        warnings.append(warn)
    if text is None:
        return ReadResult(None, enc, warn, size, warnings)
    return ReadResult(normalize_newlines(text), enc, "; ".join(warnings), size, warnings)
