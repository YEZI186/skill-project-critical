"""
模块名称: 行数统计
文件名称: loc.py
模块类型: 核心模块
功能描述: 用单遍词法状态机统计文本的「物理行 / 空行 / 注释行 / 有效代码行」四口径。
          关键规则：只在代码态识别注释与字符串起始（因此字符串内的 /* 、/** 不会吞行）；
          支持嵌套块注释、行首块注释、转义与原样字符串、跨行字符串、heredoc、SFC 分块。
          附带恒等式自检：phys == blank + comment + code
"""

import re
from dataclasses import dataclass, field

from .languages import FALLBACK, LangSpec, embedded_specs, spec_for_ext, spec_for_path

BLANK = "blank"
COMMENT = "comment"
CODE = "code"

# heredoc 起始：<<TAG / <<-TAG / <<~TAG / <<'TAG' / <<"TAG"
_HEREDOC_RE = re.compile(r"<<[-~]?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# SFC（Vue/Svelte/Astro）区块标签
_SFC_SCRIPT_OPEN = re.compile(r"^\s*<script\b", re.I)
_SFC_SCRIPT_CLOSE = re.compile(r"^\s*</script\s*>", re.I)
_SFC_STYLE_OPEN = re.compile(r"^\s*<style\b", re.I)
_SFC_STYLE_CLOSE = re.compile(r"^\s*</style\s*>", re.I)


@dataclass
class LocStats:
    """单文件/整体统计结果（四口径）"""
    phys: int = 0
    blank: int = 0
    comment: int = 0
    code: int = 0
    language: str = ""
    fallback: bool = False                 # 是否走了通用兜底规则
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """恒等式自检：物理行 = 空行 + 注释行 + 有效代码行"""
        return self.phys == self.blank + self.comment + self.code

    def as_dict(self) -> dict:
        return {
            "phys": self.phys,
            "blank": self.blank,
            "comment": self.comment,
            "code": self.code,
            "language": self.language,
            "fallback": self.fallback,
            "reconcile_ok": self.ok,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _Opener:
    """代码态可开启的定界符（块注释或字符串）"""
    start: str
    kind: str            # "block" | "string"
    end: str
    nestable: bool = False
    line_start_only: bool = False
    is_multi: bool = False


def _split_lines(text: str) -> list[str]:
    """物理行切分：末尾换行不额外计行；空文本为 0 行"""
    if text == "":
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


class _Scanner:
    """单遍字符扫描器：产出每行是否含代码 / 注释"""

    def __init__(self, text: str, spec: LangSpec):
        self.text = text
        self.spec = spec
        self.lines = _split_lines(text)
        self.n = len(self.lines)
        self.has_code = [False] * self.n
        self.has_note = [False] * self.n
        self.warnings: list[str] = []

        self.line_comments = tuple(sorted(spec.line_comments, key=len, reverse=True))
        self.word_comments = tuple(spec.word_comments)

        openers: list[_Opener] = []
        for b in spec.block_comments:
            openers.append(_Opener(b.start, "block", b.end, b.nestable, b.line_start_only, False))
        for s in spec.multiline_strings:
            openers.append(_Opener(s[0], "string", s[1], False, False, True))
        for s in spec.strings:
            openers.append(_Opener(s[0], "string", s[1], False, False, False))
        openers.sort(key=lambda o: len(o.start), reverse=True)
        self.openers = tuple(openers)

    # ---------------- 辅助判断 ----------------

    def _at_line_start(self, i: int) -> bool:
        """i 之前是否只有行首空白（用于 line_start_only 的块注释）"""
        j = i - 1
        text = self.text
        while j >= 0 and text[j] in " \t":
            j -= 1
        return j < 0 or text[j] == "\n"

    def _match_line_comment(self, i: int):
        for tok in self.line_comments:
            if self.text.startswith(tok, i):
                return tok
        if self.word_comments:
            for tok in self.word_comments:
                seg = self.text[i:i + len(tok)]
                if seg.upper() != tok.upper():
                    continue
                j = i + len(tok)
                if j >= len(self.text) or not (self.text[j].isalnum() or self.text[j] == "_"):
                    return tok
        return None

    def _match_opener(self, i: int):
        for op in self.openers:
            if self.text.startswith(op.start, i):
                if op.line_start_only and not self._at_line_start(i):
                    continue
                return op
        return None

    def _is_raw_string(self, i: int) -> bool:
        """判断字符串是否带原样前缀（如 Python 的 r"..."），原样字符串内不处理转义"""
        if not self.spec.raw_prefixes or i == 0:
            return False
        prev = self.text[i - 1]
        if prev not in self.spec.raw_prefixes:
            return False
        before = self.text[i - 2] if i >= 2 else ""
        return not (before.isalnum() or before == "_")

    # ---------------- 主扫描 ----------------

    def scan(self) -> None:
        text = self.text
        spec = self.spec
        length = len(text)
        i = 0
        line = 0
        state = CODE
        end_tok = ""
        block_start = ""
        nestable = False
        is_multi = False
        raw_string = False
        depth = 0
        str_start_line = 0
        heredoc_tag = ""
        heredoc_line = -1
        escape = spec.escape

        while i < length:
            ch = text[i]

            # ---- heredoc：结束标记行按注释计，其余内容行按注释计 ----
            if state == "heredoc":
                if ch == "\n":
                    nxt_start = i + 1
                    nxt_end = text.find("\n", nxt_start)
                    if nxt_end < 0:
                        nxt_end = length
                    nxt = text[nxt_start:nxt_end]
                    if nxt.strip() == heredoc_tag:
                        self.has_note[line + 1] = True
                        line += 1
                        i = nxt_end
                        state = CODE
                        continue
                    self.has_note[line + 1] = True
                    line += 1
                    i += 1
                    continue
                if line > heredoc_line:
                    self.has_note[line] = True
                i += 1
                continue

            # ---- 通用换行 ----
            if ch == "\n":
                if state == "string" and not is_multi:
                    self.warnings.append(
                        f"第 {line + 1} 行附近单行字符串未闭合，已按行收尾（不影响后续行统计）")
                    state = CODE
                line += 1
                i += 1
                continue

            # ---- 块注释内部 ----
            if state == "block":
                self.has_note[line] = True
                if nestable and block_start and text.startswith(block_start, i):
                    depth += 1
                    i += len(block_start)
                    continue
                if end_tok and text.startswith(end_tok, i):
                    depth -= 1
                    i += len(end_tok)
                    if depth <= 0:
                        state = CODE
                    continue
                i += 1
                continue

            # ---- 字符串内部 ----
            if state == "string":
                if line > str_start_line:
                    self.has_note[line] = True
                if not raw_string and escape and ch == escape:
                    i += 2
                    continue
                if end_tok and text.startswith(end_tok, i):
                    i += len(end_tok)
                    state = CODE
                    continue
                i += 1
                continue

            # ---- 代码态：识别 heredoc / 行注释 / 块与字符串起始 ----
            if spec.heredoc and ch == "<" and text.startswith("<<", i):
                m = _HEREDOC_RE.match(text, i)
                if m:
                    heredoc_tag = m.group(2)
                    heredoc_line = line
                    self.has_code[line] = True
                    state = "heredoc"
                    i = m.end()
                    continue

            hit = self._match_line_comment(i)
            if hit is not None:
                self.has_note[line] = True
                nl = text.find("\n", i)
                i = length if nl < 0 else nl
                continue

            opener = self._match_opener(i)
            if opener is not None:
                state = "block" if opener.kind == "block" else "string"
                end_tok = opener.end
                nestable = opener.nestable
                block_start = opener.start
                if opener.kind == "block":
                    depth = 1
                    self.has_note[line] = True
                else:
                    is_multi = opener.is_multi
                    raw_string = self._is_raw_string(i)
                    str_start_line = line
                    self.has_code[line] = True
                i += len(opener.start)
                continue

            if not ch.isspace():
                self.has_code[line] = True
            i += 1

        # 文件结束时仍未闭合：容错收尾并记警告（绝不吞行、绝不抛错）
        if state == "block":
            self.warnings.append(f"第 {line + 1} 行：文件结束时块注释未闭合，已按文件末尾收尾")
        elif state == "string" and is_multi:
            self.warnings.append(f"第 {line + 1} 行：文件结束时跨行字符串未闭合，已按文件末尾收尾")
        elif state == "heredoc":
            self.warnings.append(f"第 {line + 1} 行：文件结束时 heredoc 未闭合，已按文件末尾收尾")

    # ---------------- 结果聚合 ----------------

    def kinds(self) -> list[str]:
        out = []
        for idx, ln in enumerate(self.lines):
            if self.has_code[idx]:
                out.append(CODE)
            elif self.has_note[idx] or ln.strip():
                out.append(COMMENT)
            else:
                out.append(BLANK)
        return out


def _aggregate(kinds: list[str]) -> tuple[int, int, int]:
    return (sum(1 for k in kinds if k == BLANK),
            sum(1 for k in kinds if k == COMMENT),
            sum(1 for k in kinds if k == CODE))


def _sfc_line_specs(lines: list[str], base: LangSpec, script: LangSpec, style: LangSpec) -> list[LangSpec]:
    """按行切分 SFC 区块：<script> → 脚本规则，<style> → 样式规则，其余用标记规则"""
    specs: list[LangSpec] = []
    cur = base
    for ln in lines:
        if _SFC_SCRIPT_OPEN.match(ln):
            specs.append(base)
            cur = script
            continue
        if _SFC_SCRIPT_CLOSE.match(ln):
            specs.append(cur)
            cur = base
            continue
        if _SFC_STYLE_OPEN.match(ln):
            specs.append(base)
            cur = style
            continue
        if _SFC_STYLE_CLOSE.match(ln):
            specs.append(cur)
            cur = base
            continue
        specs.append(cur)
    return specs


def classify_lines(text: str, spec: LangSpec) -> tuple[list[str], list[str]]:
    """返回 (每行类别, 警告列表)"""
    lines = _split_lines(text)
    if not lines:
        return [], []
    if not spec.sfc:
        sc = _Scanner(text, spec)
        sc.scan()
        return sc.kinds(), sc.warnings

    script, style = embedded_specs()
    line_specs = _sfc_line_specs(lines, spec, script, style)
    kinds: list[str] = [BLANK] * len(lines)
    warnings: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and line_specs[j + 1] is line_specs[i]:
            j += 1
        chunk = "\n".join(lines[i:j + 1])
        sc = _Scanner(chunk, line_specs[i])
        sc.scan()
        kinds[i:j + 1] = sc.kinds()
        warnings.extend(sc.warnings)
        i = j + 1
    return kinds, warnings


def count_text(text: str, path: str | None = None, ext: str | None = None,
               spec: LangSpec | None = None) -> LocStats:
    """统计一段文本的四口径

    text  已做过换行归一与清洗的文本（统计对象 = 即将写入 md 的同一文本）
    path  用于按扩展名/文件名判定语言；ext 可单独指定
    """
    if spec is None:
        if path:
            spec = spec_for_path(path, text)
        else:
            spec = spec_for_ext(ext or "", text)
    kinds, warnings = classify_lines(text, spec)
    blank, comment, code = _aggregate(kinds)
    return LocStats(phys=len(kinds), blank=blank, comment=comment, code=code,
                    language=spec.name, fallback=(spec is FALLBACK), warnings=warnings)
