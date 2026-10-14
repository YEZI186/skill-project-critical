"""
模块名称: 语言定义表
文件名称: languages.py
模块类型: 基础数据模块
功能描述: 定义各编程语言的注释与字符串规则（行注释、需词边界的行注释、块注释、
          普通字符串、跨行字符串、heredoc、行首块注释、SFC 分块等），
          供 loc.py 的词法扫描使用；未识别的扩展名走通用兜底规则
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BlockComment:
    """块注释定界符

    nestable        支持嵌套（Rust/Swift/Kotlin/Haskell/Nim/F# 等）
    line_start_only 仅行首有效（Ruby =begin/=end、Perl =pod/=cut）
    """
    start: str
    end: str
    nestable: bool = False
    line_start_only: bool = False


@dataclass(frozen=True)
class LangSpec:
    """单种语言（或语言族）的注释/字符串规则"""
    name: str
    line_comments: tuple[str, ...] = ()            # 行注释前缀
    word_comments: tuple[str, ...] = ()            # 需词边界的行注释（VB/bat 的 REM）
    block_comments: tuple[BlockComment, ...] = ()  # 块注释
    strings: tuple[tuple[str, str], ...] = ()      # 普通字符串 (开始, 结束)
    multiline_strings: tuple[tuple[str, str], ...] = ()  # 跨行字符串；续行按注释计（口径见方案 7.1）
    escape: str | None = "\\"                      # 转义符；None 表示不处理转义
    raw_prefixes: tuple[str, ...] = ()             # 原样字符串前缀（r/R），其内部不处理转义
    heredoc: bool = False                          # 支持 <<TAG / <<-TAG / <<'TAG' / <<~TAG
    sfc: bool = False                              # 按 SFC 分块处理（vue/svelte/astro）
    notes: str = ""                                # 已知简化说明


# ============================ 常用定界符 ============================

_C_BLOCK = BlockComment("/*", "*/")
_C_BLOCK_NEST = BlockComment("/*", "*/", nestable=True)
_TRIPLE_DQ = BlockComment('"""', '"""')
_TRIPLE_SQ = BlockComment("'''", "'''")
_HASKELL_BLOCK = BlockComment("{-", "-}", nestable=True)
_ML_BLOCK = BlockComment("(*", "*)", nestable=True)
_PASCAL_BRACE = BlockComment("{", "}")
_PASCAL_PAREN = BlockComment("(*", "*)")
_PY_DOC = (_TRIPLE_DQ, _TRIPLE_SQ)
_SQ_DQ = (('"', '"'), ("'", "'"))
_BACKTICK = (("`", "`"),)

FALLBACK = LangSpec(
    "Unknown",
    line_comments=("//", "#", "--"),
    block_comments=(_C_BLOCK, BlockComment("<!--", "-->")),
    strings=_SQ_DQ,
    notes="通用兜底：同时认 //、#、-- 三种行注释与两种块注释",
)


def _c_like(name: str, *, nestable: bool = False, extra_blocks: tuple[BlockComment, ...] = (),
            multiline: tuple[tuple[str, str], ...] = (), line: tuple[str, ...] = ("//",),
            sfc: bool = False, notes: str = "") -> LangSpec:
    """构造 C 系语言规则（// + /* */ + 单双引号字符串）"""
    blocks = ((_C_BLOCK_NEST if nestable else _C_BLOCK),) + tuple(extra_blocks)
    return LangSpec(name, line_comments=line, block_comments=blocks,
                    strings=_SQ_DQ, multiline_strings=multiline, sfc=sfc, notes=notes)


# ============================ 扩展名映射 ============================

_LANGS: dict[str, LangSpec] = {}


def _reg(spec: LangSpec, *exts: str) -> LangSpec:
    for e in exts:
        _LANGS[e] = spec
    return spec


# ---- C 系 ----
_reg(_c_like("C"), ".c", ".h")
_reg(_c_like("C++"), ".cpp", ".hpp", ".cc", ".cxx")
_reg(_c_like("Objective-C"), ".mm")
_reg(_c_like("Java", extra_blocks=(_TRIPLE_DQ,)), ".java")
_reg(_c_like("C#", extra_blocks=(_TRIPLE_DQ,), notes="未建模 @\"...\" verbatim 字符串"), ".cs")
_reg(_c_like("JavaScript", multiline=_BACKTICK), ".js", ".mjs", ".cjs", ".jsx")
_reg(_c_like("TypeScript", multiline=_BACKTICK), ".ts", ".tsx")
_reg(_c_like("Go", multiline=_BACKTICK), ".go")
_reg(_c_like("Rust", nestable=True), ".rs")
_reg(_c_like("Kotlin", extra_blocks=(_TRIPLE_DQ,)), ".kt", ".kts")
_reg(_c_like("Swift", nestable=True, extra_blocks=(_TRIPLE_DQ,)), ".swift")
_reg(_c_like("Dart", extra_blocks=(_TRIPLE_DQ, _TRIPLE_SQ)), ".dart")
_reg(_c_like("Scala", extra_blocks=(_TRIPLE_DQ,)), ".scala")
_reg(_c_like("Groovy", extra_blocks=(_TRIPLE_DQ, _TRIPLE_SQ)), ".groovy")
_reg(_c_like("PHP", line=("//", "#")), ".php")
_reg(_c_like("CSS", line=(), notes="CSS 标准无行注释，仅 /* */"), ".css")
_reg(_c_like("SCSS"), ".scss")
_reg(_c_like("Less"), ".less")
_reg(_c_like("Stylus"), ".styl")

# ---- 脚本类 ----
_reg(LangSpec("Python", line_comments=("#",), block_comments=_PY_DOC,
              strings=_SQ_DQ, raw_prefixes=("r", "R")), ".py", ".pyw")
_reg(LangSpec("Ruby", line_comments=("#",),
              block_comments=(BlockComment("=begin", "=end", line_start_only=True),),
              strings=_SQ_DQ, heredoc=True), ".rb")
_reg(LangSpec("Shell", line_comments=("#",), strings=_SQ_DQ, heredoc=True), ".sh", ".bash", ".zsh")
_reg(LangSpec("PowerShell", line_comments=("#",), block_comments=(BlockComment("<#", "#>"),),
              strings=_SQ_DQ, heredoc=True), ".ps1")
_reg(LangSpec("Batch", line_comments=("::",), word_comments=("REM",),
              strings=(('"', '"'),), escape=None), ".bat", ".cmd")
_reg(LangSpec("Perl", line_comments=("#",),
              block_comments=(BlockComment("=pod", "=cut", line_start_only=True),),
              strings=_SQ_DQ, heredoc=True), ".pl", ".pm")
_reg(LangSpec("Lua", line_comments=("--",), block_comments=(BlockComment("--[[", "]]"),),
              strings=_SQ_DQ, multiline_strings=(("[[", "]]"),)), ".lua")
_reg(LangSpec("R", line_comments=("#",), strings=_SQ_DQ), ".r", ".R")

# ---- .NET / 函数式 ----
_reg(LangSpec("VisualBasic", line_comments=("'",), word_comments=("REM",), strings=(('"', '"'),)), ".vb")
_reg(LangSpec("FSharp", line_comments=("//",), block_comments=(_ML_BLOCK,), strings=_SQ_DQ), ".fs")
_reg(LangSpec("Haskell", line_comments=("--",), block_comments=(_HASKELL_BLOCK,), strings=_SQ_DQ), ".hs")
_reg(LangSpec("Elm", line_comments=("--",), block_comments=(_HASKELL_BLOCK,), strings=_SQ_DQ), ".elm")
_reg(LangSpec("Erlang", line_comments=("%",), strings=(('"', '"'),)), ".erl")
_reg(LangSpec("Elixir", line_comments=("#",), strings=_SQ_DQ, heredoc=True), ".ex", ".exs")
_reg(LangSpec("Clojure", line_comments=(";",), strings=(('"', '"'),)), ".clj")
_reg(LangSpec("Pascal", line_comments=("//",), block_comments=(_PASCAL_BRACE, _PASCAL_PAREN),
              strings=(("'", "'"),)), ".pas")
_reg(LangSpec("Fortran", line_comments=("!",), strings=_SQ_DQ), ".f90")
_reg(LangSpec("Nim", line_comments=("#",), block_comments=(BlockComment("#[", "]#", nestable=True),),
              strings=_SQ_DQ), ".nim")
_reg(LangSpec("Matlab", line_comments=("%",), block_comments=(BlockComment("%{", "%}"),),
              strings=_SQ_DQ), ".m-matlab")

# ---- 标记 / 前端 ----
_MARKUP = LangSpec("Markup", block_comments=(BlockComment("<!--", "-->"),), strings=_SQ_DQ, escape=None)
_reg(_MARKUP, ".html", ".htm", ".xml", ".svg", ".wxml", ".axml", ".xaml")
_reg(LangSpec("JSP", block_comments=(BlockComment("<!--", "-->"), BlockComment("<%--", "--%>")),
              strings=_SQ_DQ, escape=None), ".jsp", ".asp")
_reg(LangSpec("Template", line_comments=("//",), block_comments=(BlockComment("<!--", "-->"),),
              strings=_SQ_DQ), ".ejs", ".hbs")
_SFC = LangSpec("SFC", block_comments=(BlockComment("<!--", "-->"),), strings=_SQ_DQ, escape=None, sfc=True)
_reg(_SFC, ".vue", ".svelte", ".astro")

# ---- 数据 / 配置 ----
_reg(LangSpec("SQL", line_comments=("--", "#"), block_comments=(_C_BLOCK,),
              strings=(("'", "'"), ('"', '"'))), ".sql")
_reg(LangSpec("YAML", line_comments=("#",), strings=_SQ_DQ), ".yaml", ".yml")
_reg(LangSpec("TOML", line_comments=("#",), strings=_SQ_DQ), ".toml")
_reg(LangSpec("INI", line_comments=(";", "#"), strings=_SQ_DQ), ".ini", ".conf", ".properties")
_reg(LangSpec("JSON", line_comments=("//",), block_comments=(_C_BLOCK,),
              strings=(('"', '"'),)), ".json", ".jsonc")
_reg(LangSpec("Dockerfile", line_comments=("#",), strings=(('"', '"'),)), ".dockerfile")
_reg(LangSpec("Makefile", line_comments=("#",), strings=_SQ_DQ), ".mk")

# 文件名特判（无扩展名或特殊命名）
_FILENAMES: dict[str, LangSpec] = {
    "dockerfile": _LANGS[".dockerfile"],
    "makefile": _LANGS[".mk"],
    "gnumakefile": _LANGS[".mk"],
    ".gitignore": LangSpec("GitIgnore", line_comments=("#",)),
    ".gitattributes": LangSpec("GitAttributes", line_comments=("#",)),
    ".env": LangSpec("DotEnv", line_comments=("#",), strings=_SQ_DQ),
}

# MATLAB 与 Objective-C 共用 .m：按内容嗅探（默认 Objective-C）
_MATLAB = _LANGS[".m-matlab"]
_OBJC = _c_like("Objective-C-M", notes=".m 默认按 Objective-C")
_OBJC_HINTS = ("#import", "@interface", "@implementation", "@property", "NSString", "NSObject")
_MATLAB_HINTS = ("function ", "end\n", "end\r\n", "%%", "%{")


def _looks_like_matlab(sample: str | None) -> bool:
    """按内容特征区分 .m 是 MATLAB 还是 Objective-C（样本不足时保守判为 ObjC）"""
    if not sample:
        return False
    head = sample[:4000]
    if any(h in head for h in _OBJC_HINTS):
        return False
    if any(h in head for h in _MATLAB_HINTS):
        return True
    return False


def spec_for_ext(ext: str, sample: str | None = None) -> LangSpec:
    """按扩展名取规则；未识别返回 FALLBACK"""
    e = (ext or "").lower()
    if e == ".m":
        return _MATLAB if _looks_like_matlab(sample) else _OBJC
    return _LANGS.get(e, FALLBACK)


def spec_for_path(path: str, sample: str | None = None) -> LangSpec:
    """按路径取规则：先看文件名特判，再看扩展名"""
    import os
    name = os.path.basename(path or "")
    lowered = name.lower()
    if lowered in _FILENAMES:
        return _FILENAMES[lowered]
    ext = os.path.splitext(lowered)[1]
    return spec_for_ext(ext, sample)


def known_extensions() -> list[str]:
    """已建模的扩展名列表（不含 .m-matlab 这类内部键）"""
    return sorted(e for e in _LANGS if not e.startswith(".m-"))


def known_language_count() -> int:
    """已建模的语言种数（按 LangSpec.name 去重）"""
    return len({s.name for s in _LANGS.values()})


def embedded_specs() -> tuple[LangSpec, LangSpec]:
    """SFC 分块用：脚本区与样式区规则"""
    return _LANGS[".ts"], _LANGS[".scss"]
