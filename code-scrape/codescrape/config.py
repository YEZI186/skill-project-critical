"""
模块名称: 配置管理
文件名称: config.py
模块类型: 工具模块
功能描述: 读取脚本目录的 settings.json（沿用旧版配置键），为 CLI 提供缺省值；
          CLI 参数优先于配置文件。只读，不在项目根或脚本目录写回配置。
"""

import json
import os

# 脚本目录（code-scrape/）：settings.json 与「忽略规则.gitignore」的兜底位置
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CONFIG = {
    "max_empty_lines": 0,
    "trim_trailing_whitespace": True,
    "max_file_size_mb": 50,
    "output_dir": "out",                      # 相对项目根；空串表示输出到项目根
    "output_type": "源代码",
    "output_name_template": "源代码-{项目名}",
    "overwrite_existing": True,
}

# 旧版英文占位符 → 中文占位符（历史 settings.json 的一次性迁移，仅在内存中生效）
_TPL_ALIASES = (("{type}", "{类型}"), ("{project}", "{项目名}"))

# Windows 文件名非法字符（项目名会进入申报材料文件名，必须清洗）
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class Config:
    """应用配置：默认值 ← settings.json ← 调用方覆盖"""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or os.path.join(SCRIPT_DIR, "settings.json")
        self.data: dict = {}
        self.reset()
        self.load()

    def reset(self) -> None:
        self.data = {k: (list(v) if isinstance(v, list) else v)
                     for k, v in DEFAULT_CONFIG.items()}

    def load(self) -> None:
        """从 settings.json 加载；失败保持默认（CLI 场景下配置缺失属正常）"""
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(loaded, dict):
            return
        for key in DEFAULT_CONFIG:
            if key in loaded:
                self.data[key] = loaded[key]
        # 模板占位符迁移（只改内存，不回写用户文件）
        tpl = self.data.get("output_name_template", "")
        if isinstance(tpl, str) and tpl:
            for old, new in _TPL_ALIASES:
                tpl = tpl.replace(old, new)
            self.data["output_name_template"] = tpl

    def save(self) -> None:
        """写回配置文件（CLI 不调用；保留给需要持久化的场景）"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.data.get(key, default))
        except (TypeError, ValueError):
            return default


def sanitize_filename(name: str, fallback: str = "项目") -> str:
    """清洗文件名：去掉 Windows 非法字符与首尾空白/点"""
    cleaned = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch for ch in (name or ""))
    cleaned = cleaned.strip().strip(".")
    return cleaned or fallback


def output_filename(cfg: Config, project_name: str) -> str:
    """按配置模板生成汇总 md 文件名（含扩展名）"""
    tpl = cfg.get("output_name_template") or "源代码-{项目名}"
    out_type = cfg.get("output_type") or "源代码"
    if not isinstance(tpl, str) or not tpl.strip():
        tpl = "源代码-{项目名}"
    name = tpl.replace("{项目名}", project_name).replace("{项目名}", project_name)
    name = name.replace("{类型}", out_type)
    return sanitize_filename(name, fallback="源代码") + ".md"


def output_path(root: str, cfg: Config, project_name: str,
                override: str | None = None) -> str:
    """汇总 md 的最终路径；override 优先（相对项目根解析）"""
    if override:
        return override if os.path.isabs(override) else os.path.join(root, override)
    out_dir = cfg.get("output_dir") or ""
    base = os.path.join(root, out_dir) if out_dir else root
    return os.path.join(base, output_filename(cfg, project_name))
