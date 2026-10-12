"""
模块名称: 核心代码清单生成
文件名称: listing.py
模块类型: 核心模块
功能描述: 按 project-critical skill 的规则完成「采集候选 → 剔除空包/样式/配置/文档脚本
          → 前后端归类 → 入口优先排序 → 小程序 js↔wxml 成对校验 → 渲染纯路径清单」，
          产出 out/核心代码名称.md。规则常量集中在文件顶部，并标注对应 SKILL.md 章节。
"""

import os
import re
from dataclasses import dataclass, field

from .scanner import FileInfo, iter_files, read_text

LISTING_TITLE = "# 核心代码文件清单"
LISTING_FILENAME = "核心代码名称.md"
DEFAULT_LISTING_DIR = "out"

# ============================ 采集扩展名（SKILL.md Step 1）============================

BACKEND_EXTS = frozenset({
    ".java", ".py", ".pyw", ".go", ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".kt", ".kts", ".rs", ".scala", ".groovy", ".swift", ".dart", ".m", ".mm", ".vb", ".fs",
    ".rb", ".lua", ".pl", ".pm", ".ex", ".exs", ".erl", ".hs", ".clj", ".pas", ".f90", ".nim", ".r",
    ".ts", ".js", ".mjs", ".cjs",              # 后端也会用 JS/TS（Express/NestJS/Egg 等）
    ".prisma",                                  # 数据模型定义（Prisma），与 entity/model 同级保留
})
FRONTEND_EXTS = frozenset({
    ".vue", ".tsx", ".jsx", ".svelte", ".astro",
    ".ts", ".js", ".mjs", ".cjs",
    # 注意：SKILL.md Step 2 明确剔除 .html（纯模板），因此这里不采集 .html
})
MINIPROGRAM_EXTS = frozenset({".wxml", ".axml"})
COLLECT_EXTS = BACKEND_EXTS | FRONTEND_EXTS | MINIPROGRAM_EXTS

# ============================ 一律剔除（SKILL.md Step 2）============================

STYLE_EXTS = frozenset({".css", ".scss", ".less", ".sass", ".styl", ".wxss"})
CONFIG_EXTS = frozenset({
    ".json", ".jsonc", ".xml", ".yml", ".yaml", ".toml", ".ini", ".conf", ".properties",
    ".gradle", ".lock", ".cfg", ".env", ".editorconfig", ".iml", ".gitignore",
})
DOC_SCRIPT_EXTS = frozenset({".md", ".txt", ".sql", ".sh", ".bash", ".bat", ".cmd", ".ps1", ".log"})
BUILD_ARTIFACT_MARKERS = (".min.js", ".min.css", ".bundle.js", ".chunk.js", "-lock.json")

CONFIG_FILE_RE = tuple(re.compile(p, re.I) for p in (
    r"^vite\.config\.", r"^vue\.config\.", r"^webpack\.config\.", r"^rollup\.config\.",
    r"^tsconfig.*\.json$", r"^jsconfig\.json$", r"^\.eslintrc", r"^\.prettierrc",
    r"^babel\.config\.", r"^\.babelrc", r"^jest\.config\.", r"^postcss\.config\.",
    r"^tailwind\.config\.", r"^next\.config\.", r"^nuxt\.config\.", r"^vitest\.config\.",
    r"^\.env", r"^application.*\.ya?ml$", r"^application.*\.properties$", r"^settings\.py$",
    r"^pom\.xml$", r"^build\.gradle.*$", r"^package(-lock)?\.json$", r"^dockerfile$",
    r"^docker-compose.*$", r"^app\.json$", r"^project\.config\.json$",
    r"^project\.private\.config\.json$", r"^sitemap\.json$", r"^manifest\.json$",
    r"^\.gitignore$", r"^\.gitattributes$", r"^\.dockerignore$", r"^\.npmrc$",
    r"^env\.(js|ts|mjs|cjs|json)$", r"^next-env\.d\.ts$", r"^vue-env\.d\.ts$",
))

# 数据脚本（演示数据/迁移脚本）：不是软件功能实现，按 SKILL.md「mock 仅 mock 数据」的精神剔除
DATA_SCRIPT_RE = tuple(re.compile(p, re.I) for p in (
    r"^seed.*\.(py|js|ts|mjs|cjs)$",
    r"^generate_data.*\.(py|js|ts)$",
    r"^demo_data.*\.(py|js|ts)$",
    r"^.*migrat(e|ion).*\.(py|js|ts)$",
))

# ============================ 归类与排序（SKILL.md Step 3）============================

BACKEND_HINTS = ("/backend/", "/server/", "/src/main/java/", "/app/backend/", "/api/src/",
                 "/service/", "/serviceimpl/", "/dao/", "/mapper/", "/entity/", "/domain/")
FRONTEND_HINTS = ("/frontend/", "/client/", "/web/", "/webapp/", "/uni_modules/", "/src/views/",
                  "/src/pages/", "/src/components/", "/src/api/", "/src/store/", "/src/router/",
                  "/src/utils/", "/src/hooks/", "/pages/", "/components/", "/static/")

# 入口文件名（SKILL.md Step 3：入口/启动类最前）
ENTRY_NAMES = frozenset({
    "main.py", "app.py", "run.py", "main.go", "program.cs",
    "index.js", "index.ts", "server.js", "main.ts", "app.ts", "main.js",
    "app.vue", "app.tsx", "app.js", "main.tsx", "main.jsx", "index.tsx",
    "_app.tsx", "_app.js", "_document.tsx", "_document.js",
    # 启动类脚本（SKILL.md「入口/启动类最前」）
    "start_server.py", "start_server.js", "start.py", "server.py",
    "bootstrap.py", "bootstrap.ts", "bootstrap.js",
    # 微信/支付宝小程序全局入口（SKILL.md Step 3 前端第 1 条）
    "app.wxml", "app.axml",
})
# 框架管理脚本：D11 裁定「不入清单」（Django 的 manage.py 属脚手架，不算业务实现）
FRAMEWORK_ADMIN_FILES = frozenset({"manage.py"})

# 入口分档：档位数字越小越靠前，档内按字典序（严格对应 SKILL.md Step 3 的列举顺序）
BACKEND_ENTRY_TIERS = (
    ("main.py", 1), ("app.py", 1), ("run.py", 1), ("manage.py", 1),
    ("start_server.py", 1), ("start.py", 1), ("server.py", 1), ("bootstrap.py", 1),
    ("main.go", 2),
    ("program.cs", 3),
    ("index.js", 4), ("server.js", 4),
)
FRONTEND_ENTRY_TIERS = (
    ("main.ts", 0), ("main.js", 0), ("index.ts", 0), ("index.js", 0),
    ("app.vue", 1), ("app.tsx", 1),
)
# 小程序全局入口：SKILL.md「app.js + 全局 app.wxml（若有）排前」
MINIPROGRAM_ENTRY_NAMES = ("app.js", "app.wxml", "app.axml")

# 演示/模拟设施目录：D13 裁定「不入清单」（与 mock/ 同类；产品本体为模拟器类时用 --keep-path 覆盖）
# 注意：**不匹配裸 `demo/`** —— `com/demo/`、`app/demo/` 是常见包名，误杀会丢核心代码；
# 只认明确表示演示设施的命名：*_simulator / *_emulator / *_demo / demo_data / demos / samples / fixtures
DEMO_DIR_RE = re.compile(
    r"(^|/)(?:[^/]*_simulator|[^/]*_emulator|[^/]*_demo|demo_data|demos"
    r"|simulator|emulator|samples?|fixtures?)(/|$)", re.I)
ENTRY_SUFFIX = "application.java"
# 框架约定的页面目录入口（Next.js），不受 NON_ENTRY_DIRS 限制
FRAMEWORK_PAGE_ENTRIES = frozenset({"_app.tsx", "_app.js", "_document.tsx", "_document.js"})
# 这些目录里的同名文件是页面/组件，不是入口
NON_ENTRY_DIRS = ("/pages/", "/components/", "/views/", "/utils/", "/hooks/",
                  "/store/", "/static/", "/assets/")

# 后端类别权重（数字越小越靠前）——严格对应 SKILL.md Step 3：
#   业务 config → controller → service → service/impl → mapper/repository → entity/model → dto → util
# 含 "/" 的模式按子串匹配，比单词模式更具体；括号内为常见别名/复数形式
BACKEND_CATEGORIES = (
    ("config", 10), ("configs", 10), ("configuration", 10), ("settings", 10),
    ("database", 10),                                 # 数据库装配属基础设施配置层
    ("controller", 20), ("controllers", 20), ("api", 20), ("apis", 20),
    ("handler", 20), ("handlers", 20), ("router", 20), ("routers", 20),
    ("route", 20), ("routes", 20), ("url", 20), ("urls", 20),   # Django urls.py = 路由层
    ("endpoint", 20), ("endpoints", 20),
    ("view", 20), ("views", 20),                      # Django views.py = 接口层
    ("service", 30), ("services", 30), ("usecase", 30), ("usecases", 30),
    ("service/impl", 40), ("services/impl", 40),
    ("mapper", 50), ("mappers", 50), ("repository", 50), ("repositories", 50),
    ("dao", 50), ("daos", 50), ("dal", 50),
    ("entity", 60), ("entities", 60), ("model", 60), ("models", 60),
    ("domain", 60), ("domains", 60), ("po", 60), ("pojo", 60),
    ("dto", 70), ("dtos", 70), ("vo", 70), ("vos", 70),
    ("schema", 70), ("schemas", 70), ("serializer", 70), ("serializers", 70),
    ("form", 70), ("forms", 70),
    ("util", 80), ("utils", 80), ("helper", 80), ("helpers", 80),
    ("common", 80), ("shared", 80),
)
# 前端类别权重——严格对应 SKILL.md Step 3：api → store → views/pages → components → utils/hooks
FRONTEND_CATEGORIES = (
    ("api", 10), ("apis", 10), ("service", 10), ("services", 10),
    ("store", 20), ("stores", 20), ("state", 20), ("pinia", 20), ("vuex", 20),
    ("router", 20), ("routers", 20), ("route", 20), ("routes", 20),
    ("view", 30), ("views", 30), ("page", 30), ("pages", 30), ("screens", 30),
    ("component", 40), ("components", 40), ("widgets", 40),
    ("util", 50), ("utils", 50), ("hook", 50), ("hooks", 50),
    ("composables", 50), ("helper", 50), ("helpers", 50),
)
OTHER_WEIGHT = 90
BACKEND_OTHER_WEIGHT = 90
FRONTEND_OTHER_WEIGHT = 60

# ============================ 文件名后缀归类（NestJS 等）============================
# 这类框架把"层次"体现在文件名而非目录上（auth.controller.ts / auth.service.ts），
# 归类结果仍严格映射到 SKILL.md Step 3 的层次次序，**不做业务模块分组**。
# 未列出的后缀（.module./.guard./.strategy./.decorator./.interceptor./.filter./.pipe./
# .middleware. 等装配与横切关注点）落"其它"，排在已归类条目之后。

SUFFIX_WEIGHTS = {
    ".controller.": 20, ".resolver.": 20,
    ".service.": 30,
    ".repository.": 50,
    ".entity.": 60, ".model.": 60,
    ".dto.": 70,
}


@dataclass(frozen=True)
class Entry:
    """清单条目"""
    relpath: str
    section: int        # 0 = 后端，1 = 前端
    category: str       # 命中的类别名（便于自检与报告）
    weight: int


@dataclass
class ListingResult:
    """清单生成结果"""
    root: str = ""
    entries: list[Entry] = field(default_factory=list)
    content: str = ""
    stats: dict = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)   # 违禁类型命中（应为空）
    pairing_issues: list[str] = field(default_factory=list)  # 小程序 js↔wxml 缺对
    is_miniprogram: bool = False

    @property
    def paths(self) -> list[str]:
        return [e.relpath for e in self.entries]

    @property
    def backend(self) -> list[str]:
        return [e.relpath for e in self.entries if e.section == 0]

    @property
    def frontend(self) -> list[str]:
        return [e.relpath for e in self.entries if e.section == 1]


# ============================ 小程序辨识 ============================

def is_miniprogram(root: str) -> bool:
    """存在小程序特征文件/目录即判定为小程序工程"""
    marks = ("app.json", "project.config.json", "project.private.config.json", "sitemap.json")
    if any(os.path.isfile(os.path.join(root, m)) for m in marks):
        return True
    if os.path.isdir(os.path.join(root, "miniprogram")):
        return True
    if (os.path.isfile(os.path.join(root, "app.js"))
            and os.path.isfile(os.path.join(root, "app.wxss"))):
        return True
    return False


# ============================ 剔除判定 ============================

def _p(path: str) -> str:
    return "/" + path.replace("\\", "/").lower()


def exclude_reason(fi: FileInfo) -> str | None:
    """按文件名/扩展名/路径段判定是否剔除，返回原因；不剔除返回 None"""
    name = os.path.basename(fi.relpath).lower()
    ext = fi.ext
    if name in FRAMEWORK_ADMIN_FILES:
        return "框架管理脚本"
    if DEMO_DIR_RE.search("/" + fi.relpath.replace("\\", "/")):
        return "演示/模拟设施"
    if any(marker in name for marker in BUILD_ARTIFACT_MARKERS):
        return "构建产物"
    if ext in STYLE_EXTS:
        return "样式"
    if ext in DOC_SCRIPT_EXTS:
        return "文档/脚本"
    if ext in CONFIG_EXTS or any(r.match(name) for r in CONFIG_FILE_RE):
        return "配置"
    if any(r.match(name) for r in DATA_SCRIPT_RE):
        return "数据脚本"
    if ext not in COLLECT_EXTS:
        return "非代码"
    return None


def _is_reexport_only(text: str) -> bool:
    """仅由 docstring / import / 纯 re-export 构成 → 视为空包

    注意：`export const/function/class/default …` 是**实际声明**，不算 re-export；
    只有 `export *`、`export { … }`（可带 `from`）这类不产生新代码的语句才可忽略。
    """
    in_all = False
    in_brace = False
    for raw in text.split("\n"):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith(('"""', "'''", '"', "'")):
            continue
        if in_all:
            if "]" in s:
                in_all = False
            continue
        if in_brace:
            if "}" in s:
                in_brace = False
            continue
        if s.startswith("__all__"):
            if "]" not in s:
                in_all = True
            continue
        if s.startswith("import ") or s.startswith("from "):
            continue
        if s.startswith("export "):
            rest = s[len("export "):].strip()
            if rest.startswith("type "):
                rest = rest[len("type "):].strip()
            if rest.startswith("{"):
                if "}" not in rest:
                    in_brace = True
                continue
            if rest.startswith("*"):
                continue
            return False
        if s in (")", "]", "}", ","):
            continue
        return False
    return True


def is_empty_package(fi: FileInfo, text: str | None) -> bool:
    """空包：空文件、纯 import/__all__ 的 __init__.py、仅 package 声明的 package-info.java、纯 re-export 的 index"""
    name = os.path.basename(fi.relpath).lower()
    if fi.size == 0:
        return True
    if text is None:
        return False
    if name == "__init__.py":
        if not text.strip():
            return True
        return _is_reexport_only(text)
    if name == "package-info.java":
        body = re.sub(r"^\s*package\s+[\w.*]+\s*;", "", text.strip())
        return not body.strip()
    if name in ("index.ts", "index.js", "index.tsx", "index.jsx") and fi.size < 50:
        return _is_reexport_only(text)
    return False


VARIANT_RE = re.compile(r"^(?P<base>.+?)(?P<num>\d+)\.(?P<ext>py|pyw|js|ts|mjs|cjs|jsx|tsx|java|go|cs|php)$", re.I)

# 只有这些文件名才可能被判为「空包」，生成清单时无需读取其它文件内容（等价且省 IO）
_EMPTY_CHECK_NAMES = frozenset({"__init__.py", "package-info.java",
                                "index.ts", "index.js", "index.tsx", "index.jsx"})


def variant_removals(candidates: list[FileInfo]) -> set[str]:
    """同目录存在去掉数字后缀的同名文件时，视为旧版/变体（如 start_server2.py vs start_server.py）"""
    names = {f.relpath for f in candidates}
    out: set[str] = set()
    for f in candidates:
        m = VARIANT_RE.match(os.path.basename(f.relpath))
        if not m:
            continue
        alt = os.path.dirname(f.relpath)
        alt_path = f"{m.group('base')}.{m.group('ext')}"
        alt_rel = f"{alt}/{alt_path}" if alt else alt_path
        if alt_rel in names:
            out.add(f.relpath)
    return out


# ============================ 归类 ============================

def classify_section(relpath: str, ext: str, miniprogram: bool) -> int:
    """判前后端：0 后端 / 1 前端"""
    low = _p(relpath)
    if any(dh in low for dh in BACKEND_HINTS):
        return 0
    if any(dh in low for dh in FRONTEND_HINTS):
        return 1
    if miniprogram and (ext in MINIPROGRAM_EXTS or low.endswith(".js") or low.endswith(".wxml")):
        return 1
    if ext in (".java", ".go", ".cs", ".php", ".rs", ".kt", ".rb", ".py", ".pyw", ".c", ".cpp", ".hpp", ".h"):
        return 0
    if ext in (".vue", ".tsx", ".jsx", ".svelte", ".astro", ".wxml", ".axml"):
        return 1
    return 1 if ext in (".ts", ".js", ".mjs", ".cjs") else 0


def _is_entry(relpath: str) -> bool:
    low = _p(relpath)
    name = os.path.basename(low)
    if name.endswith(ENTRY_SUFFIX):
        return True
    if name in FRAMEWORK_PAGE_ENTRIES:
        return True    # Next.js 的 pages/_app.tsx、_document.tsx 属框架入口
    if name not in ENTRY_NAMES:
        return False
    return not any(d in low for d in NON_ENTRY_DIRS)


def _entry_tier(relpath: str, section: int, miniprogram: bool) -> int:
    """入口分档（数字越小越靠前），严格按 SKILL.md Step 3 的列举顺序；档内字典序"""
    low = _p(relpath)
    name = os.path.basename(low)
    if miniprogram and section == 1 and name in MINIPROGRAM_ENTRY_NAMES:
        return -1          # 小程序全局入口 app.js / app.wxml / app.axml 排最前
    if section == 0:
        if name.endswith(ENTRY_SUFFIX):
            return 0       # *Application.java
        for entry_name, tier in BACKEND_ENTRY_TIERS:
            if name == entry_name:
                return tier
        return 5
    if name.startswith("index.") and "/router/" in low:
        return 2           # router/index.*（先于通用 index.* 判定）
    for entry_name, tier in FRONTEND_ENTRY_TIERS:
        if name == entry_name:
            return tier
    if name in FRAMEWORK_PAGE_ENTRIES:
        return 3           # Next.js 框架页面入口
    return 4


def _match_category(relpath: str, section: int) -> tuple[str, int]:
    low = _p(relpath)
    name = os.path.basename(low)
    stem = os.path.splitext(name)[0]
    table = BACKEND_CATEGORIES if section == 0 else FRONTEND_CATEGORIES
    best: tuple[str, int] | None = None
    for pattern, weight in table:
        hit = f"/{pattern}/" in low
        if not hit and "/pages/" not in low and stem == pattern:
            hit = True     # lib/api.ts、src/store.ts 这类按文件名主干归类
        if hit and (best is None or len(pattern) >= len(best[0])):
            best = (pattern, weight)
    if best is None:
        for suffix, weight in SUFFIX_WEIGHTS.items():
            if suffix in name:
                return (suffix.strip("."), weight)   # auth.controller.ts 这类按后缀归类
        return ("其它", BACKEND_OTHER_WEIGHT if section == 0 else FRONTEND_OTHER_WEIGHT)
    return best


def _pair_key(relpath: str) -> str:
    """小程序页面/组件的 .wxml/.axml 紧跟同名 .js（SKILL.md：.js 在前、.wxml 随后）"""
    low = _p(relpath)
    if low.endswith((".wxml", ".axml")):
        return (relpath[: relpath.rfind(".")] + ".js\x00").lower()
    return relpath.lower()


def sort_key(entry: Entry, miniprogram: bool = False) -> tuple:
    """排序键，严格对应 SKILL.md Step 3：入口优先（含分档）→ 类别次序 → 同级字典序"""
    if _is_entry(entry.relpath):
        return (entry.section, 0,
                _entry_tier(entry.relpath, entry.section, miniprogram), 0,
                _pair_key(entry.relpath), entry.relpath.lower())
    return (entry.section, 1, 0, entry.weight,
            _pair_key(entry.relpath), entry.relpath.lower())


# ============================ 自检 ============================

def check_violations(entries: list[Entry]) -> list[str]:
    """清单中不得出现样式/配置/文档脚本类条目"""
    bad = []
    for e in entries:
        name = os.path.basename(e.relpath).lower()
        ext = os.path.splitext(name)[1]
        if ext in STYLE_EXTS or ext in CONFIG_EXTS or ext in DOC_SCRIPT_EXTS:
            bad.append(e.relpath)
        elif any(r.match(name) for r in CONFIG_FILE_RE):
            bad.append(e.relpath)
    return bad


# 小程序页面/组件目录标记：只对这些目录下的 .js 做 js↔wxml 成对校验
PAGE_DIR_MARKERS = ("/pages/", "/components/")


def check_pairs(entries: list[Entry]) -> list[str]:
    """小程序 js↔wxml 成对校验

    仅对 pages/**、components/** 下的 .js 要求存在同名 .wxml（微信）或 .axml（支付宝）：
    app.js、api/**、utils/** 等脚本本就没有配套结构文件，不参与校验（避免误报）；
    页面目录整体缺结构文件时同样能查出来（不漏检）。
    """
    manifest = {e.relpath for e in entries}
    issues = []
    for e in sorted(entries, key=lambda x: x.relpath.lower()):
        if not e.relpath.endswith(".js"):
            continue
        low = "/" + e.relpath.lower()
        if not any(m in low for m in PAGE_DIR_MARKERS):
            continue
        stem = e.relpath[: -len(".js")]
        if stem + ".wxml" in manifest or stem + ".axml" in manifest:
            continue
        issues.append(f"{e.relpath} 缺少同名 .wxml")
    return issues


# ============================ 渲染与解析 ============================

def render(entries: list[Entry]) -> str:
    """渲染清单文本：标题 + 后端段 + 空行 + 前端段"""
    backend = [e.relpath for e in entries if e.section == 0]
    frontend = [e.relpath for e in entries if e.section == 1]
    if not backend and not frontend:
        return LISTING_TITLE + "\n"
    parts = [LISTING_TITLE, ""]
    parts.extend(backend)
    if backend and frontend:
        parts.append("")
    parts.extend(frontend)
    return "\n".join(parts) + "\n"


def parse_listing(text: str) -> list[str]:
    """解析清单文本：跳过空行与 # 注释（标题）行"""
    out = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.replace("\\", "/"))
    return out


def default_listing_path(root: str) -> str:
    return os.path.join(root, DEFAULT_LISTING_DIR, LISTING_FILENAME)


# ============================ 主入口 ============================

def _in_keep(relpath: str, keep_paths: tuple[str, ...]) -> bool:
    """项目级白名单：命中的路径不做任何剔除（应对产品本体即模拟器/特殊命名的项目）"""
    for k in keep_paths:
        kk = k.replace("\\", "/").rstrip("/")
        if kk and (relpath == kk or relpath.startswith(kk + "/")):
            return True
    return False


def generate(root: str, skip_dirs=None, read_encoding: bool = True,
             keep_paths: tuple[str, ...] = (), ignore=None) -> ListingResult:
    """生成清单（不写盘）

    ignore: IgnoreRules 实例（可选）；命中的相对路径在采集前被过滤，命中数记入 stats["ignored"]
    """
    root = os.path.abspath(root)
    stats: dict = {"collected": 0, "excluded": {}, "read_failed": 0,
                   "ignored": 0, "keep_paths": list(keep_paths)}
    files = iter_files(root, skip_dirs) if skip_dirs is not None else iter_files(root)
    if ignore is not None:
        kept = []
        for fi in files:
            if keep_paths and _in_keep(fi.relpath, keep_paths):
                kept.append(fi)
                continue
            if ignore.is_ignored(fi.relpath):
                stats["ignored"] += 1
                continue
            kept.append(fi)
        files = kept
    miniprogram = is_miniprogram(root)

    candidates: list[FileInfo] = []
    for fi in files:
        if keep_paths and _in_keep(fi.relpath, keep_paths):
            candidates.append(fi)
            continue
        reason = exclude_reason(fi)
        if reason:
            stats["excluded"][reason] = stats["excluded"].get(reason, 0) + 1
            continue
        candidates.append(fi)
    stats["collected"] = len(candidates)

    variants = variant_removals(candidates)
    if variants:
        stats["excluded"]["同名变体"] = len(variants)

    entries: list[Entry] = []
    for fi in candidates:
        if fi.relpath in variants:
            continue
        if keep_paths and _in_keep(fi.relpath, keep_paths):
            section = classify_section(fi.relpath, fi.ext, miniprogram)
            category, weight = _match_category(fi.relpath, section)
            entries.append(Entry(fi.relpath, section, category, weight))
            continue
        text = None
        if (read_encoding and fi.size > 0
                and os.path.basename(fi.relpath).lower() in _EMPTY_CHECK_NAMES):
            text, _enc = read_text(fi.path)
            if text is None:
                stats["read_failed"] += 1
        if is_empty_package(fi, text):
            stats["excluded"]["空包"] = stats["excluded"].get("空包", 0) + 1
            continue
        section = classify_section(fi.relpath, fi.ext, miniprogram)
        category, weight = _match_category(fi.relpath, section)
        entries.append(Entry(fi.relpath, section, category, weight))

    entries.sort(key=lambda e: sort_key(e, miniprogram))
    result = ListingResult(
        root=root,
        entries=entries,
        content=render(entries),
        stats=stats,
        is_miniprogram=miniprogram,
    )
    result.violations = check_violations(entries)
    result.pairing_issues = check_pairs(entries) if miniprogram else []
    return result


def write_listing(result: ListingResult, path: str | None = None) -> str:
    """写出清单文本（UTF-8 无 BOM），返回写入路径"""
    target = path or default_listing_path(result.root)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(result.content)
    return target
