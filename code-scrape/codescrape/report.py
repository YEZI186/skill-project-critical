"""
模块名称: 统计报告
文件名称: report.py
模块类型: 核心模块
功能描述: 生成完成后把统计摘要输出到会话/控制台（替代旧版 GUI 日志区与文档头部统计），
          并提供 --stats-json 落盘（schema codescrape/stats@1）。
          统计对象与写入 md 的正文同源，出口即对账：md 正文行数 = Σ各文件 phys + 占位行 + 分隔行。
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

SCHEMA = "codescrape/stats@1"
# 页数估算基数：送排版的正文行数（不是有效代码行数）
PAGE_LINES = 50
# 语言行最多罗列的种类数
LANG_LIMIT = 8


def page_count(lines: int) -> float:
    return round(lines / PAGE_LINES, 1)


@dataclass
class FileStat:
    """单个文件的四口径统计（统计输入 = 清洗后写入 md 的同一文本）"""
    path: str
    ext: str
    encoding: str = ""
    phys: int = 0
    blank: int = 0
    comment: int = 0
    code: int = 0
    language: str = ""
    fallback: bool = False
    failed: bool = False
    warnings: list[str] = field(default_factory=list)


def _display(path: str, root: str) -> str:
    """输出用路径：项目内显示 POSIX 相对路径，项目外显示绝对路径"""
    try:
        rel = os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")
    return path.replace("\\", "/") if rel.startswith("../") else rel


def reconcile(doc, file_stats: list[FileStat]) -> dict:
    """对账恒等式：md 正文总行数 = Σ各文件 phys + 失败占位行数 + 分隔行数"""
    total_phys = sum(s.phys for s in file_stats if not s.failed)
    left = doc.body_lines
    right = total_phys + doc.placeholder_lines + doc.separator_lines
    return {
        "md_body_lines": left,
        "sum_file_phys": total_phys,
        "placeholder_lines": doc.placeholder_lines,
        "separator_lines": doc.separator_lines,
        "ok": left == right,
    }


# ============================ 旧版算法对照（--legacy-report，D8）============================

def _legacy_reason(ext: str, delta: int) -> str:
    """按差异方向与扩展名给出启发式归因（说明"旧数字为何不同"，不逐行复刻旧算法）"""
    if delta > 0:
        return "旧算法把字符串内的注释符当作注释开始，吞掉后续行"
    if ext in (".wxml", ".axml", ".html", ".xml"):
        return "旧算法未识别 HTML 注释（<!-- -->）"
    if ext in (".vue", ".svelte", ".astro"):
        return "旧算法只识别 <!-- -->，漏识别 <script> 内的 JS 注释"
    if ext == ".sql":
        return "旧算法对 .sql 只配了 //，漏识别 -- 行注释"
    if ext in (".yaml", ".yml", ".toml", ".ini", ".conf", ".properties"):
        return "旧算法未识别该语法的注释规则"
    if ext == ".py":
        return "旧算法三引号/docstring 判定差异"
    return "旧算法注释规则缺失或处理差异"


def legacy_compare(file_stats: list[FileStat], legacy_codes: dict) -> dict:
    """新旧算法逐文件对照；legacy_codes: {relpath: 旧算法有效代码行数}"""
    rows: list[dict] = []
    old_total = 0
    new_total = 0
    for s in file_stats:
        if s.failed or s.path not in legacy_codes:
            continue
        old = int(legacy_codes[s.path])
        old_total += old
        new_total += s.code
        if old == s.code:
            continue
        delta = s.code - old
        rows.append({
            "path": s.path, "ext": s.ext, "old": old, "new": s.code,
            "delta": delta, "reason": _legacy_reason(s.ext, delta),
        })
    rows.sort(key=lambda r: (-abs(r["delta"]), r["path"]))
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["reason"], {"reason": r["reason"], "files": 0, "delta": 0})
        g["files"] += 1
        g["delta"] += r["delta"]
    return {
        "old_total": old_total,
        "new_total": new_total,
        "delta": new_total - old_total,
        "changed_files": len(rows),
        "compared_files": sum(1 for s in file_stats if not s.failed and s.path in legacy_codes),
        "groups": sorted(groups.values(), key=lambda g: -abs(g["delta"])),
        "rows": rows,
        "note": "旧数字由 codescrape/legacy_count.py 的 V1.6 只读快照算出；归因为启发式（按扩展名与差异方向），非逐行复刻旧算法",
    }


def build_stats(*, root: str, project_name: str, project_name_source: str,
                listing_info: dict, file_stats: list[FileStat], doc,
                warnings: list[str] | None = None, md_path: str = "",
                dry_run: bool = False, generated_at: str | None = None,
                legacy: dict | None = None) -> dict:
    """汇总为可序列化的统计字典（stats-json 与内容输出共用同一份数据）"""
    ok_stats = [s for s in file_stats if not s.failed]
    totals = {
        "files": len(ok_stats),
        "phys": sum(s.phys for s in ok_stats),
        "blank": sum(s.blank for s in ok_stats),
        "comment": sum(s.comment for s in ok_stats),
        "code": sum(s.code for s in ok_stats),
        "md_lines": doc.body_lines,
        "pages": page_count(doc.body_lines),
    }
    by_lang: dict[str, dict] = {}
    for s in ok_stats:
        key = s.ext or "(无扩展名)"
        row = by_lang.setdefault(key, {"ext": key, "files": 0, "phys": 0,
                                       "blank": 0, "comment": 0, "code": 0})
        row["files"] += 1
        row["phys"] += s.phys
        row["blank"] += s.blank
        row["comment"] += s.comment
        row["code"] += s.code
    languages = sorted(by_lang.values(), key=lambda r: (-r["phys"], r["ext"]))
    return {
        "schema": SCHEMA,
        "generated_at": generated_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "root": root,
        "project_name": project_name,
        "project_name_source": project_name_source,
        "dry_run": bool(dry_run),
        "listing": listing_info,
        "totals": totals,
        "md": {
            "path": md_path,
            "header_lines": doc.header_lines,
            "body_lines": doc.body_lines,
        },
        "by_language": languages,
        "files": [asdict(s) for s in file_stats],
        "fallback_extensions": sorted({s.ext for s in ok_stats if s.fallback and s.ext}),
        "reconcile": reconcile(doc, file_stats),
        "legacy": legacy,
        "warnings": list(warnings or []),
    }


def delivery_line(stats: dict, root: str = "") -> str:
    """交付自检行：两份材料（清单 + 汇总 md）必须同时落盘**且对账成立**（SKILL.md Step 5）

    返回空串表示本轮不产出文档（dry-run / stat），不做交付判定。
    三种结果：齐备 / 存疑（已落盘但对账不平）/ 不完整（缺文件）。
    """
    md = stats.get("md", {}) or {}
    listing = stats.get("listing", {}) or {}
    rec = stats.get("reconcile") or {}
    if not md.get("path") or stats.get("dry_run"):
        return ""
    listing_path = listing.get("path", "") or ""
    md_path = md.get("path", "")
    md_show = _display(md_path, root)
    have_listing = bool(listing_path) and os.path.isfile(listing_path)
    have_md = os.path.isfile(md_path)
    if not (have_listing and have_md):
        lack = "、".join(n for n, ok in (("清单", have_listing), ("汇总 md", have_md)) if not ok)
        return f"[交付] 不完整：缺 {lack}——按 SKILL.md Step 5 补跑 `run` 后再交付"
    if not rec.get("ok", True):
        return (f"[交付] 存疑：两份材料已落盘，但对账不平（md 正文 {rec.get('md_body_lines')} 行 ≠ "
                f"Σ物理 {rec.get('sum_file_phys')} + 占位 {rec.get('placeholder_lines')}"
                f" + 分隔 {rec.get('separator_lines')}）——不得交付，先排查")
    return (f"[交付] 两份材料齐备：清单 {_display(listing_path, root)}"
            f"（{listing.get('entries', 0)} 条）／汇总 {md_show}（{md.get('body_lines', 0)} 行）")


def console_lines(stats: dict, quiet: bool = False, verbose: bool = False,
                  root: str = "") -> list[str]:
    """把统计渲染为会话输出行（[级别] 前缀，与历史 GUI 文案风格一致）"""
    root = root or stats.get("root", "")
    listing = stats.get("listing", {}) or {}
    totals = stats.get("totals", {}) or {}
    md = stats.get("md", {}) or {}
    out: list[str] = []

    md_show = _display(md.get("path", ""), root) if md.get("path") else "(未写出)"
    listing_path = listing.get("path", "") or ""
    if quiet:
        lines = [f"[输出] {md_show}（仅源码正文，无头部）"]
        rec_q = stats.get("reconcile") or {}
        if not rec_q.get("ok", True):
            lines.append(
                f"[内部错误] 对账不平：md 正文 {rec_q.get('md_body_lines')} 行 ≠ "
                f"Σ物理 {rec_q.get('sum_file_phys')} + 占位 {rec_q.get('placeholder_lines')}"
                f" + 分隔 {rec_q.get('separator_lines')}"
            )
        # quiet 也要给交付结论：否则按 SKILL.md Step 5 的判据无法在 -q 下判定完成
        delivery = delivery_line(stats, root)
        if delivery:
            lines.append(delivery)
        return lines

    out.append(f"[完成] 项目：{stats.get('project_name', '')}　根目录：{root}")
    if listing_path:
        out.append(
            f"[清单] {_display(listing_path, root)}　条目 {listing.get('entries', 0)}"
            f"　命中 {listing.get('matched', 0)}　缺失 {len(listing.get('missing') or [])}"
            f"　违规 {len(listing.get('invalid') or [])}"
            f"（后端 {listing.get('backend', 0)} / 前端 {listing.get('frontend', 0)}）"
        )
    out.append(
        f"[统计] 文件 {totals.get('files', 0)}　物理行 {totals.get('phys', 0)}"
        f"　空行 {totals.get('blank', 0)}　注释行 {totals.get('comment', 0)}"
        f"　有效代码行 {totals.get('code', 0)}"
        f"　≈ {totals.get('pages', 0)} 页（按正文 {totals.get('md_lines', 0)} 行 / {PAGE_LINES} 行每页）"
    )
    langs = stats.get("by_language") or []
    if langs:
        shown = langs[:LANG_LIMIT]
        text = "；".join(f"{r['ext']} {r['files']} 文件 {r['phys']} 行" for r in shown)
        rest = langs[LANG_LIMIT:]
        if rest:
            text += f"；其它 {sum(r['files'] for r in rest)} 文件 {sum(r['phys'] for r in rest)} 行"
        out.append(f"[语言] {text}")
    legacy = stats.get("legacy")
    if legacy:
        out.append(
            f"[旧版对照] 旧算法有效代码 {legacy.get('old_total', 0)}"
            f" / 新实现 {legacy.get('new_total', 0)}　净差 {legacy.get('delta', 0):+d}"
            f"　差异文件 {legacy.get('changed_files', 0)} / {legacy.get('compared_files', 0)} 个"
            "（旧数字取自 V1.6 只读快照，归因为启发式）"
        )
        groups = legacy.get("groups") or []
        if groups:
            detail = "；".join(f"{g['reason']} {g['delta']:+d}（{g['files']} 文件）" for g in groups)
            out.append(f"[旧版对照] 归因：{detail}")
    head_note = f"（含旧版头部 {md.get('header_lines', 0)} 行）" if md.get("header_lines") else "（仅源码正文，无头部）"
    out.append(f"[输出] {md_show}{head_note}")

    # 交付自检：两份材料（清单 + 汇总 md）必须同时落盘且对账成立（SKILL.md Step 5）
    delivery = delivery_line(stats, root)
    if delivery:
        out.append(delivery)

    failed = [f for f in stats.get("files", []) if f.get("failed")]
    skipped: list[str] = []
    if failed:
        skipped.append("读取失败 " + "、".join(f["path"] for f in failed[:5]))
    if listing.get("missing"):
        skipped.append("清单缺失 " + "、".join((listing["missing"])[:5]))
    if listing.get("invalid"):
        skipped.append("类型违规 " + "、".join((listing["invalid"])[:5]))
    if stats.get("warnings"):
        skipped.append("告警 " + str(len(stats["warnings"])) + " 条")
    out.append("[提示] 跳过/失败：" + ("；".join(skipped) if skipped else "无"))

    rec = stats.get("reconcile") or {}
    if not rec.get("ok", True):
        out.append(
            f"[内部错误] 对账不平：md 正文 {rec.get('md_body_lines')} 行 ≠ "
            f"Σ物理 {rec.get('sum_file_phys')} + 占位 {rec.get('placeholder_lines')}"
            f" + 分隔 {rec.get('separator_lines')}"
        )
    if verbose:
        out.append(f"[对账] md 正文 {rec.get('md_body_lines')} 行 = Σ物理 {rec.get('sum_file_phys')}"
                   f" + 占位 {rec.get('placeholder_lines')} + 分隔 {rec.get('separator_lines')}"
                   f"　{'成立' if rec.get('ok') else '不成立'}")
        for f in stats.get("files", []):
            flag = "读取失败" if f.get("failed") else f"{f.get('encoding', '')}"
            out.append(
                f"[文件] {f.get('path')}　{flag}　物理 {f.get('phys', 0)}"
                f"　空 {f.get('blank', 0)}　注释 {f.get('comment', 0)}　代码 {f.get('code', 0)}"
            )
        for w in stats.get("warnings") or []:
            out.append(f"[告警] {w}")
        for r in (legacy.get("rows") if legacy else []) or []:
            out.append(f"[旧版对照] {r['path']}　旧 {r['old']} → 新 {r['new']}"
                       f"（{r['delta']:+d}：{r['reason']}）")
    return out


def write_json(stats: dict, path: str) -> str:
    """把统计落盘（UTF-8 无 BOM，缩进 2）"""
    target = os.path.abspath(path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return target
