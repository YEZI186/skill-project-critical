"""
模块名称: 文件扫描
文件名称: scanner.py
模块类型: 工具模块
功能描述: 递归枚举目录下的文件（按忽略目录剪枝），返回绝对路径、POSIX 相对路径、
          大小与扩展名，并回填诊断统计（遍历总数、剪枝目录、读取失败数等）
"""

import os
from dataclasses import dataclass

# 默认剪枝目录：版本控制、依赖、构建产物、归档与文档目录
DEFAULT_SKIP_DIRS = frozenset({
    # 版本控制 / 编辑器
    ".git", ".svn", ".hg", ".idea", ".vscode", ".dsh-vision-router",
    # 依赖与构建产物
    "node_modules", "dist", "build", "target", "coverage", "vendor",
    "venv", ".venv", "env", "__pycache__", ".next", ".nuxt", ".nuxt3",
    "miniprogram_npm", ".turbo", ".cache", ".pytest_cache", "unpackage",
    # 归档与文档（清单/汇编/归档旧源码一律不进采集）
    "out", "3-out", "03-审查产物", "docs", "doc",
    # 旧版归档目录（P4 归档的 GUI 与旧模块，绝不能被采集）
    "_legacy",
    # 辅助脚本与框架生成物（排版工具、构建脚本、数据库迁移）
    "tools", "scripts", "migrations", "alembic",
    # 替身与数据
    "mock", "mocks",
    # 临时
    "logs", "tmp", "temp",
})

# Windows 保留设备名：此类文件名会让路径解析异常，必须跳过
_RESERVED_NAMES = {"con", "prn", "aux", "nul",
                   *(f"com{i}" for i in range(1, 10)),
                   *(f"lpt{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class FileInfo:
    """扫描到的文件信息"""
    path: str      # 绝对路径
    relpath: str   # POSIX 相对路径
    size: int      # 字节
    ext: str       # 小写扩展名（含点），无扩展名为空串


def _is_reserved_name(fname: str) -> bool:
    return os.path.splitext(fname)[0].lower() in _RESERVED_NAMES


def safe_relpath(full_path: str, root_path: str) -> str:
    """os.path.relpath 的兜底版本：保留设备名等特殊路径手动截取，统一 POSIX 分隔"""
    try:
        return os.path.relpath(full_path, root_path).replace("\\", "/")
    except ValueError:
        root_cmp = root_path.replace("/", "\\").rstrip("\\")
        full_cmp = full_path.replace("/", "\\")
        if full_cmp.lower().startswith(root_cmp.lower() + "\\"):
            rel = full_cmp[len(root_cmp):]
        else:
            rel = os.path.basename(full_cmp)
        return rel.lstrip("\\/").replace("\\", "/")


def iter_files(root: str, skip_dirs=DEFAULT_SKIP_DIRS,
               include_hidden_files: bool = True, stats: dict | None = None) -> list[FileInfo]:
    """递归枚举 root 下的文件（跳过 skip_dirs 中的目录与隐藏目录）

    stats 回填：raw_files / skipped_dirs / size_errors / root_error / walk_errors / reserved_skipped
    """
    if stats is None:
        stats = {}
    stats.setdefault("raw_files", 0)
    stats.setdefault("skipped_dirs", [])
    stats.setdefault("size_errors", 0)
    stats.setdefault("root_error", "")
    stats.setdefault("walk_errors", [])
    stats.setdefault("reserved_skipped", 0)

    try:
        os.listdir(root)
    except OSError as e:
        stats["root_error"] = f"{type(e).__name__}: {e}"
        return []

    def _on_walk_error(err: OSError):
        if len(stats["walk_errors"]) < 5:
            stats["walk_errors"].append(f"{err.filename}: {err.strerror}")

    files: list[FileInfo] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        kept = []
        for d in dirnames:
            rel = safe_relpath(os.path.join(dirpath, d), root)
            if d in skip_dirs or d.startswith(".") or _is_reserved_name(d):
                if len(stats["skipped_dirs"]) < 40:
                    stats["skipped_dirs"].append(rel)
                continue
            kept.append(d)
        dirnames[:] = kept

        for fname in filenames:
            if fname.startswith(".") and not include_hidden_files:
                st = os.path.join(dirpath, fname)
                stats["raw_files"] += 1
                stats["skipped_dirs"].append(safe_relpath(st, root))
                continue
            if _is_reserved_name(fname):
                stats["raw_files"] += 1
                stats["reserved_skipped"] += 1
                continue
            full_path = os.path.join(dirpath, fname)
            stats["raw_files"] += 1
            try:
                size = os.path.getsize(full_path)
            except OSError:
                stats["size_errors"] += 1
                continue
            files.append(FileInfo(
                path=full_path,
                relpath=safe_relpath(full_path, root),
                size=size,
                ext=os.path.splitext(fname)[1].lower(),
            ))

    files.sort(key=lambda f: f.relpath.lower())
    return files


def read_text(path: str) -> tuple[str | None, str]:
    """读取文本（编码候选链：UTF-8 → GB18030 → Big5 → latin-1），返回 (内容, 编码)"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None, ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"
