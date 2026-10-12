"""
模块名称: 忽略规则解析
文件名称: ignore_rules.py
模块类型: 工具模块
功能描述: 解析 .gitignore 语法规则文件，供扫描与清单生成时过滤文件与目录。
          CLI 侧全程只读：找不到规则文件就按「无规则」处理，绝不在项目根生成文件。
"""

import os
import re
from dataclasses import dataclass

# 脚本目录（code-scrape/）：默认规则文件的兜底位置
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 默认规则内容：仅用于「缺失时的参考文本」与旧版兼容，CLI 不写盘
DEFAULT_RULES = """# 软著源码整理工具 - 忽略规则
# 语法与 .gitignore 一致：
#   # 注释
#   node_modules/   忽略任意层级的该目录
#   *.log           通配文件（* 匹配任意字符，? 匹配单个字符）
#   !keep.py        取反：重新包含
#   /build          仅忽略根目录下的 build
# 新增规则直接写在本文件，下次运行生效

# ---- 版本控制 ----
.git/
.svn/
.hg/

# ---- 依赖与构建产物 ----
node_modules/
__pycache__/
target/
build/
dist/
vendor/
venv/
.venv/
env/
.idea/
.vscode/
*.egg-info/

# ---- 编译产物 ----
*.pyc
*.class
*.o
*.obj
"""


@dataclass
class IgnoreRule:
    """单条已编译的忽略规则"""
    negate: bool          # 取反规则（! 开头）
    dir_only: bool        # 仅匹配目录（结尾带 /）
    anchored: bool        # 锚定到扫描根目录（模式内部含 /）
    regex: re.Pattern     # 预编译正则


def _glob_to_regex(seg: str) -> str:
    """把单个 glob 段转成正则片段；* ? 不跨 /，** 跨任意层级"""
    out = []
    i = 0
    n = len(seg)
    while i < n:
        ch = seg[i]
        if ch == "*":
            if i + 1 < n and seg[i + 1] == "*":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "".join(out)


def _compile_rule(pattern: str) -> IgnoreRule | None:
    """将一行规则编译为 IgnoreRule；空规则返回 None

    前导空格在 .gitignore 语义里属于模式本身（需 \\  转义才是空格），这里原样保留。
    """
    negate = pattern.startswith("!")
    if negate:
        pattern = pattern[1:]
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]
    if not pattern:
        return None
    if pattern.startswith("**/"):
        pattern = pattern[3:]
    if not pattern:
        return None
    anchored = False
    if pattern.startswith("/"):
        anchored = True
        pattern = pattern[1:]
    if not pattern:
        return None
    anchored = anchored or "/" in pattern
    segs = [_glob_to_regex(s) for s in pattern.split("/")]
    body = "/".join(segs)
    if anchored:
        regex = re.compile("^" + body + "(?:/|$)")
    else:
        regex = re.compile("(?:^|/)" + body + "(?:/|$)")
    return IgnoreRule(negate=negate, dir_only=dir_only, anchored=anchored, regex=regex)


class IgnoreRules:
    """已解析的忽略规则集合"""

    def __init__(self, lines: list[str]):
        self.rules: list[IgnoreRule] = []
        for raw in lines:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            rule = _compile_rule(line)
            if rule is not None:
                self.rules.append(rule)
        self.has_negate = any(r.negate for r in self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    def is_ignored(self, relpath: str, is_dir: bool = False) -> bool:
        """判断相对路径是否被忽略；多条规则命中时以最后一条为准（git 语义）"""
        candidates = [relpath]
        if not is_dir:
            parts = relpath.split("/")
            candidates.extend("/".join(parts[:i]) for i in range(1, len(parts)))
        ignored = False
        for rule in self.rules:
            for cand in candidates:
                if rule.regex.search(cand):
                    ignored = not rule.negate
                    break
        return ignored

    def should_prune(self, dir_relpath: str) -> bool:
        """目录级剪枝判断：目录被忽略且不存在取反规则时才整棵剪掉"""
        if self.has_negate:
            return False
        return self.is_ignored(dir_relpath, is_dir=True)


def rules_file_path() -> str:
    """脚本目录下的默认规则文件路径"""
    return os.path.join(SCRIPT_DIR, "忽略规则.gitignore")


def resolve_rules_file(root: str, explicit: str | None = None) -> tuple[str | None, str]:
    """确定要使用的规则文件，返回 (路径 或 None, 来源说明)

    优先级：`--rules` 显式指定 > 项目根「忽略规则.gitignore」 > 脚本目录兜底。
    只使用已存在的文件，任何情况下都不创建文件。
    """
    if explicit:
        p = os.path.abspath(explicit)
        if os.path.isfile(p):
            return p, "命令行 --rules"
        return None, f"命令行 --rules 指定的文件不存在：{p}（已按无规则处理）"
    cand = os.path.join(root, "忽略规则.gitignore")
    if os.path.isfile(cand):
        return cand, "项目根"
    cand = rules_file_path()
    if os.path.isfile(cand):
        return cand, "脚本目录（回退）"
    return None, "未找到规则文件（按无规则处理）"


def load_rules(path: str | None = None) -> IgnoreRules:
    """读取并编译规则文件；path 为空或读取失败时返回空规则集（不写盘）"""
    if not path or not os.path.isfile(path):
        return IgnoreRules([])
    lines: list[str] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        try:
            with open(path, "r", encoding="gbk") as f:
                lines = f.readlines()
        except Exception:
            lines = []
    return IgnoreRules(lines)
