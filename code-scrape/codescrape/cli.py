"""
模块名称: 命令行入口
文件名称: cli.py
模块类型: 入口模块
功能描述: argparse 子命令（run / list / pack / stat / scan）、参数校验、退出码与日志输出。
          以当前工作目录为项目根：在项目根执行 `python <skill>/codescrape.py run` 即可
          产出清单与汇总 md（仅源码正文），统计在生成完成后输出到会话。
"""

import argparse
import os
import re
import sys

from . import __version__
from . import cleaner, legacy_count, listing, loc, markdown, reader, report, scanner
from .config import Config, output_path, sanitize_filename
from .ignore_rules import load_rules, resolve_rules_file

# 退出码（见方案 6.3）
EXIT_OK = 0        # 成功
EXIT_ENV = 1       # 参数/环境错误
EXIT_LISTING = 2   # 清单校验失败（--strict）
EXIT_READ = 3      # 存在读取/解码失败且未加 --allow-partial


class CliError(Exception):
    """带退出码的命令行错误"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# ============================ 基础工具 ============================

def _setup_stdout() -> None:
    """输出编码兜底：保留控制台自身编码（GBK 控制台直接写中文不会乱码），
    仅在编码缺失或为 ASCII 时切到 UTF-8，并统一 errors=replace 避免个别字符导致崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if enc in ("", "ascii", "ansi_x3.4-1968", "us-ascii"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _say(level: str, message: str) -> None:
    print(f"[{level}] {message}")


def _resolve_path(root: str, p: str | None) -> str | None:
    """相对路径按项目根解析"""
    if not p:
        return None
    return os.path.abspath(p) if os.path.isabs(p) else os.path.abspath(os.path.join(root, p))


def extract_chinese(text: str) -> str:
    """只保留中文字符（项目名默认口径：取目录名中的中文）"""
    return "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))


def resolve_project_name(root: str, override: str | None = None) -> tuple[str, str]:
    """解析项目名，返回 (名称, 来源说明)

    默认取项目根目录名中的中文；--project-name 显式指定的登记全称原样使用（仅做文件名安全清洗）。
    """
    if override and override.strip():
        return sanitize_filename(override.strip(), "项目"), "命令行 --project-name"
    name = extract_chinese(os.path.basename(os.path.normpath(root)))
    return (name or "项目"), "项目根目录名（仅中文）"


def _load_ignore_rules(root: str, explicit: str | None):
    """解析忽略规则文件；返回 (规则集, 路径或 None, 来源说明)"""
    path, source = resolve_rules_file(root, explicit)
    return load_rules(path), path, source


def _listing_path(root: str, override: str | None) -> str:
    return _resolve_path(root, override) or listing.default_listing_path(root)


def _md_path(root: str, cfg: Config, project_name: str, override: str | None) -> str:
    return os.path.abspath(output_path(root, cfg, project_name, override))


def _read_listing_text(path: str) -> str:
    rr = reader.read_file(path)
    if not rr.ok:
        raise CliError(EXIT_ENV, f"清单读取失败：{path}（{rr.warning}）")
    return rr.text or ""


def _miniprogram_entries(paths: list[str], miniprogram: bool) -> list[listing.Entry]:
    """把清单路径包装成 Entry（仅用于成对校验，category/weight 不参与）"""
    out = []
    for rel in paths:
        ext = os.path.splitext(rel)[1].lower()
        out.append(listing.Entry(relpath=rel,
                                 section=listing.classify_section(rel, ext, miniprogram),
                                 category="", weight=0))
    return out


# ============================ 子命令实现 ============================

def cmd_list(args, root: str, rules, rules_path: str | None) -> dict:
    """生成/更新清单"""
    result = listing.generate(root=root, keep_paths=tuple(args.keep_path or []), ignore=rules)
    target = _listing_path(root, args.list_path)

    problems: list[str] = []
    problems.extend(f"类型违规：{v}" for v in result.violations)
    problems.extend(f"小程序成对缺失：{p}" for p in result.pairing_issues)

    if not result.entries:
        # 空项目：不写盘（脚本无法凭空造出清单），但给出与 SKILL.md 一致的下一步指引
        raise CliError(EXIT_ENV,
                       f"未采集到任何核心代码文件：{root}"
                       "（请确认在项目根目录下执行，或该项目的源码目录被规则/剪枝排除）。"
                       "若项目确实暂无代码（如文档仓），按 SKILL.md 注意事项生成空清单模板并注明"
                       "「待代码落盘后按此规则重新生成」；代码落盘后再跑本命令补出清单与汇总 md")
    if problems and args.strict:
        detail = "；".join(problems[:5])
        raise CliError(EXIT_LISTING, f"清单校验未通过（--strict 已阻止写出）：{detail}")
    for p in problems:
        _say("警告", p)

    if args.dry_run:
        _say("清单", f"{_display(target, root)}（dry-run 未写出）　条目 {len(result.entries)}")
    else:
        try:
            listing.write_listing(result, target)
        except OSError as e:
            raise CliError(EXIT_ENV, f"清单写出失败：{target}（{type(e).__name__}: {e}）"
                                     "——请确认输出目录可写，或用 -l 指定其它路径")
        _say("清单", f"{_display(target, root)}　条目 {len(result.entries)}")
        if getattr(args, "command", "") == "list":
            # list 只产清单、不产汇总 md：属流程半成品，必须提示补跑（见 SKILL.md Step 5）
            _say("下一步", f"清单已生成，但源代码汇总 md 尚未产出——"
                           f"补跑 `pack`（或直接用 `run`）生成 <root>/out/源代码-{{项目名}}.md")
    return {"path": target, "result": result}


def cmd_pack(args, root: str, cfg: Config, project_name: str, name_source: str,
             rules, do_write: bool = True, listing_result=None) -> tuple[int, dict]:
    """按清单汇总（pack 写文档；stat 只统计）

    listing_result: 传入 ListingResult 时直接用其条目（run --dry-run 时清单未落盘）
    """
    listing_path = _listing_path(root, args.list_path)
    auto_list = bool(getattr(args, "auto_list", False))

    if listing_result is not None:
        entries = [e.relpath for e in listing_result.entries]
    else:
        if not os.path.isfile(listing_path):
            if auto_list:
                gen = listing.generate(root=root, keep_paths=tuple(args.keep_path or []),
                                       ignore=rules)
                if not gen.entries:
                    raise CliError(EXIT_ENV, f"未采集到任何核心代码文件：{root}")
                listing.write_listing(gen, listing_path)
                _say("清单", f"{_display(listing_path, root)}（--auto-list 自动生成）　条目 {len(gen.entries)}")
            else:
                raise CliError(EXIT_ENV,
                               f"清单不存在：{listing_path}（先执行 list 生成，或加 --auto-list）")
        entries = listing.parse_listing(_read_listing_text(listing_path))
    if not entries:
        raise CliError(EXIT_ENV, f"清单为空：{listing_path}")

    # ---- 清单校验：存在性 + 采集类型 ----
    missing: list[str] = []
    invalid: list[str] = []
    ok_paths: list[str] = []
    for rel in entries:
        full = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(full):
            missing.append(rel)
            continue
        if os.path.splitext(rel)[1].lower() not in listing.COLLECT_EXTS:
            invalid.append(rel)
            continue
        ok_paths.append(rel)

    miniprogram = listing.is_miniprogram(root)
    pair_issues = listing.check_pairs(_miniprogram_entries(ok_paths, miniprogram)) if miniprogram else []

    if (missing or invalid or pair_issues) and args.strict:
        detail = []
        if missing:
            detail.append("条目不存在 " + "、".join(missing[:5]))
        if invalid:
            detail.append("类型违规 " + "、".join(invalid[:5]))
        if pair_issues:
            detail.append("小程序成对缺失 " + "、".join(pair_issues[:5]))
        raise CliError(EXIT_LISTING, "清单校验未通过（--strict 已阻止产出）：" + "；".join(detail))
    for rel in missing:
        _say("警告", f"清单条目不存在，已跳过：{rel}")
    for rel in invalid:
        _say("警告", f"清单条目类型不在采集范围，已跳过：{rel}")
    for issue in pair_issues:
        _say("警告", issue)

    # ---- 读取 → 清洗 → 统计（统计输入 = 即将写入 md 的同一文本）----
    max_empty = args.max_empty_lines if args.max_empty_lines is not None else cfg.get_int("max_empty_lines", 0)
    trim_trailing = bool(cfg.get("trim_trailing_whitespace", True))
    max_size_mb = cfg.get("max_file_size_mb", 50)

    file_stats: list[report.FileStat] = []
    pairs: list[tuple[str, str | None]] = []
    warnings: list[str] = []
    for rel in ok_paths:
        full = os.path.join(root, *rel.split("/"))
        ext = os.path.splitext(rel)[1].lower()
        rr = reader.read_file(full, max_size_mb=max_size_mb)
        if not rr.ok:
            file_stats.append(report.FileStat(path=rel, ext=ext, failed=True,
                                              warnings=[rr.warning] if rr.warning else []))
            pairs.append((rel, None))
            warnings.append(f"{rel}：{rr.warning}")
            continue
        cleaned = cleaner.clean_text(rr.text or "", max_empty_lines=max_empty,
                                     trim_trailing=trim_trailing)
        st = loc.count_text(cleaned, path=rel)
        file_stats.append(report.FileStat(
            path=rel, ext=ext, encoding=rr.encoding, phys=st.phys, blank=st.blank,
            comment=st.comment, code=st.code, language=st.language, fallback=st.fallback,
            warnings=list(rr.warnings) + list(st.warnings),
        ))
        for w in list(rr.warnings) + list(st.warnings):
            warnings.append(f"{rel}：{w}")
        pairs.append((rel, cleaned))

    failed = [s for s in file_stats if s.failed]
    doc = markdown.build(
        pairs, project_name=project_name,
        with_file_headers=bool(args.with_file_headers),
        keep_header=bool(args.keep_header),
        legacy_code_lines=sum(s.code for s in file_stats if not s.failed),
        legacy_file_count=len(ok_paths),
    )

    backend = sum(1 for r in ok_paths
                  if listing.classify_section(r, os.path.splitext(r)[1].lower(), miniprogram) == 0)
    listing_info = {
        "path": listing_path,
        "entries": len(entries),
        "matched": len(ok_paths),
        "missing": missing,
        "invalid": invalid,
        "pairing_issues": pair_issues,
        "backend": backend,
        "frontend": len(ok_paths) - backend,
        "miniprogram": miniprogram,
    }

    md_path = "" if not do_write else _md_path(root, cfg, project_name, args.out_path)

    # --legacy-report：用 V1.6 只读快照算旧数字，仅作对照（不参与任何产出，D8）
    legacy = None
    if getattr(args, "legacy_report", False):
        legacy_codes: dict[str, int] = {}
        for rel, cleaned in pairs:
            if cleaned is None:
                continue
            legacy_codes[rel] = legacy_count.count_code_lines(
                cleaned, os.path.splitext(rel)[1].lower())
        legacy = report.legacy_compare(file_stats, legacy_codes)

    stats = report.build_stats(
        root=root, project_name=project_name, project_name_source=name_source,
        listing_info=listing_info, file_stats=file_stats, doc=doc,
        warnings=warnings, md_path=md_path, dry_run=bool(args.dry_run) or not do_write,
        legacy=legacy,
    )

    rec = stats["reconcile"]
    if rec["ok"] and do_write:
        if not args.dry_run:
            if not bool(cfg.get("overwrite_existing", True)) and os.path.isfile(md_path):
                raise CliError(EXIT_ENV, f"输出已存在且 overwrite_existing=false：{md_path}")
            os.makedirs(os.path.dirname(md_path) or ".", exist_ok=True)
            with open(md_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(doc.text())
            _say("写出", f"{_display(md_path, root)}　正文 {doc.body_lines} 行")

    code = EXIT_OK
    if not rec["ok"]:
        code = EXIT_ENV
    elif failed and not args.allow_partial:
        code = EXIT_READ

    if args.stats_json:
        json_path = _resolve_path(root, args.stats_json)
        written = report.write_json(stats, json_path)
        _say("JSON", _display(written, root))

    for line in report.console_lines(stats, quiet=bool(args.quiet),
                                     verbose=bool(args.verbose), root=root):
        print(line)
    return code, stats


def cmd_scan(args, root: str, rules, rules_path: str | None, rules_source: str) -> int:
    """诊断：列出扫描命中、被忽略与剪枝情况"""
    walk_stats: dict = {}
    files = scanner.iter_files(root, stats=walk_stats)
    result = listing.generate(root=root, keep_paths=tuple(args.keep_path or []), ignore=rules)

    _say("扫描", f"{root}　遍历文件 {walk_stats.get('raw_files', 0)}　"
                 f"剪枝目录 {len(walk_stats.get('skipped_dirs') or [])} 个")
    if rules_path:
        _say("规则", f"{_display(rules_path, root)}（{len(rules)} 条，来源：{rules_source}）")
    else:
        _say("规则", rules_source)
    _say("忽略", f"被规则过滤的文件 {result.stats.get('ignored', 0)} 个")
    _say("采集", f"候选 {result.stats.get('collected', 0)} 个")
    buckets = result.stats.get("excluded") or {}
    if buckets:
        detail = "；".join(f"{k} {v}" for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]))
        _say("剔除", detail)
    _say("清单", f"{_display(_listing_path(root, args.list_path), root)}　"
                 f"条目 {len(result.entries)}（后端 {sum(1 for e in result.entries if e.section == 0)}"
                 f" / 前端 {sum(1 for e in result.entries if e.section == 1)}）")
    if result.is_miniprogram:
        _say("小程序", "是（全局入口 app.js / app.wxml 排最前，页面 .js 与同名 .wxml 成对相邻）")
    _say("校验", f"类型违规 {len(result.violations)}　小程序成对缺失 {len(result.pairing_issues)}")
    skipped = (walk_stats.get("skipped_dirs") or [])[:12]
    if skipped:
        _say("剪枝目录", "、".join(skipped) + ("…" if len(walk_stats.get("skipped_dirs") or []) > 12 else ""))
    if walk_stats.get("root_error"):
        raise CliError(EXIT_ENV, f"项目根不可读：{walk_stats['root_error']}")
    return EXIT_OK


# ============================ 参数与分发 ============================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codescrape",
        description="软著核心代码清单生成与源码汇总（无界面命令行工具）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-r", "--root", default=None,
                        help="项目根目录；默认为当前工作目录（skill 使用时不传）")
    common.add_argument("--project-name", default=None,
                        help="项目名（登记全称）；默认为项目根目录名中的中文")
    common.add_argument("-l", "--list", dest="list_path", default=None,
                        help="清单路径；默认 <root>/out/核心代码名称.md")
    common.add_argument("-o", "--out", dest="out_path", default=None,
                        help="汇总 md 输出路径；默认按 settings.json 模板落 <root>/out/")
    common.add_argument("--rules", default=None,
                        help="忽略规则文件；默认 <root>/忽略规则.gitignore，回退脚本目录")
    common.add_argument("-k", "--max-empty-lines", dest="max_empty_lines", type=int,
                        choices=(0, 1, 2), default=None,
                        help="空行压缩 0/1/2；默认取 settings.json（当前 0）")
    common.add_argument("--with-file-headers", action="store_true",
                        help="每份源码前插入路径注释行（不计入统计）")
    common.add_argument("--keep-header", action="store_true",
                        help="在 md 顶部写回旧版标题与统计列表（默认不写）")
    common.add_argument("--stats-json", default=None, help="把统计 JSON 落盘")
    common.add_argument("--legacy-report", action="store_true",
                        help="并列旧版算法数字与逐条差异归因（只读对照，不改变产出）")
    common.add_argument("--strict", action="store_true",
                        help="清单缺失/违规条目 → 退出码 2 且不产出文档")
    common.add_argument("--allow-partial", action="store_true",
                        help="存在读取失败时不判失败（默认退出码 3）")
    common.add_argument("--keep-path", action="append", default=[], metavar="PATH",
                        help="项目级白名单：命中路径不做任何剔除（可重复）")
    common.add_argument("-q", "--quiet", action="store_true", help="只输出结果路径与错误")
    common.add_argument("-v", "--verbose", action="store_true", help="输出逐文件明细")
    common.add_argument("--dry-run", action="store_true", help="不写盘，只输出将要写出的路径与统计")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[common], help="生成清单 + 汇总（默认）")
    sub.add_parser("list", parents=[common], help="仅生成/更新清单")
    pack = sub.add_parser("pack", parents=[common], help="仅按清单汇总")
    pack.add_argument("--auto-list", action="store_true", help="清单不存在时自动先生成")
    stat = sub.add_parser("stat", parents=[common], help="只统计不产出文档")
    stat.add_argument("--auto-list", action="store_true", help="清单不存在时自动先生成")
    sub.add_parser("scan", parents=[common], help="诊断：扫描命中/忽略/剪枝情况")
    return parser


def _display(path: str, root: str) -> str:
    try:
        rel = os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")
    return path.replace("\\", "/") if rel.startswith("../") else rel


def _dispatch(args) -> int:
    root = os.path.abspath(args.root or os.getcwd())
    if not os.path.isdir(root):
        raise CliError(EXIT_ENV, f"项目根目录不存在：{root}")
    cfg = Config()
    project_name, name_source = resolve_project_name(root, args.project_name)
    rules, rules_path, rules_source = _load_ignore_rules(root, args.rules)

    if args.command == "scan":
        return cmd_scan(args, root, rules, rules_path, rules_source)

    if args.command == "list":
        cmd_list(args, root, rules, rules_path)
        return EXIT_OK

    if args.command in ("pack", "stat"):
        code, _stats = cmd_pack(args, root, cfg, project_name, name_source, rules,
                                do_write=(args.command == "pack"))
        return code

    # run = list + pack（--dry-run 时清单不落盘，直接把生成结果交给 pack）
    info = cmd_list(args, root, rules, rules_path)
    code, _stats = cmd_pack(args, root, cfg, project_name, name_source, rules, do_write=True,
                            listing_result=info["result"] if args.dry_run else None)
    return code


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except CliError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:  # pragma: no cover
        print("[错误] 已中断", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
