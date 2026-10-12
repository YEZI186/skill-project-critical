# skill-project-critical

软著申报流水线技能：**核心代码文件清单生成**（project-critical）。

按「先后端再前端、入口优先」排序，剔除空包 / 样式 / 配置 / 构建产物与文档脚本，产出纯路径清单；
并附带一个**无界面命令行工具** `code-scrape/`，一条命令同时给出清单、按清单汇总的源代码 md 与行数统计。

- 运行时**零第三方依赖**（Python 3.10+）
- 清单规则以 `SKILL.md` 为单一来源，脚本规则常量集中在 `code-scrape/codescrape/listing.py` 顶部并逐条标注对应章节
- 汇总 md **只含源码正文**（无标题、无统计列表、无分隔线），统计在生成完成后输出到会话，保证文档可复现

## 安装

本仓库是标准 Agent Skills 包（根目录含 `SKILL.md`），用 [`skills` CLI](https://github.com/vercel-labs/skills) 一键安装。

### 推荐：一条命令覆盖 opencode / pi / DeepSeek Harness

```
npx skills add YEZI186/skill-project-critical -a opencode -a pi -g -y
```

这三个 agent 都读取**通用 skills 目录** `~/.agents/skills/`，因此一次安装三方同时生效：

| Agent | 生效路径 | 说明 |
|---|---|---|
| opencode | `~/.agents/skills/project-critical/` | opencode 官方支持的通用 skills 目录（项目级为 `<项目>/.agents/skills/`） |
| pi | `~/.agents/skills/project-critical/` | pi 的全局 skills 目录 |
| DeepSeek Harness | `~/.agents/skills/project-critical/` | DSH 的 `agents` skill 来源，默认启用（见 `<DSH_HOME>/skills-manager/state.json`）；DSH 另支持自有目录 `<DSH_HOME>/skills/` |

> 2026-10-12 本机实测：执行上面这条命令后，两个 agent 的安装结果落在同一路径 `~/.agents/skills/project-critical/`（34 文件 / 约 257 KB，含 `code-scrape/` 全部内容），DSH 侧无需额外操作即可识别。

### 其他 agent

```
npx skills add YEZI186/skill-project-critical -a claude-code -g -y    # 指定单个 agent
npx skills add YEZI186/skill-project-critical -a cursor -g -y
npx skills add YEZI186/skill-project-critical --all                   # 安装到全部已探测到的 agent
npx skills ls -g                                                      # 查看已安装
npx skills remove project-critical -g                                 # 卸载
```

`skills` CLI 支持 85 个 agent（claude-code、cursor、codex、gemini-cli、windsurf、trae、qwen-code、kimi-code-cli、roo、cline、amp、zed…）。

### 装到 DeepSeek Harness 自有目录（可选）

只使用 DSH，或希望把 skill 放在 DSH 自有目录（便于本地改动脚本与规则、避免与通用目录混用）时：

```
git clone https://github.com/YEZI186/skill-project-critical.git "<DSH_HOME>/skills/project-critical"
```

`<DSH_HOME>` 默认 `~/.dsh`（Windows 为 `C:\Users\<用户名>\.dsh`），即最终路径 `~/.dsh/skills/project-critical/`。

### 项目级安装（随仓库提交、团队共享）

在项目根目录执行（安装到该项目的 `.agents/skills/`）：

```
npx skills add YEZI186/skill-project-critical -a opencode -a pi
```

### 手动安装

把本仓库（至少 `SKILL.md` 与 `code-scrape/`）复制到目标 agent 的 skills 目录，**目录名保持 `project-critical`**：

```
<agent skills 目录>/project-critical/
├─ SKILL.md
└─ code-scrape/
```

## 使用

在**项目根目录**执行（零路径参数、不需要选择项目，项目根 = 当前工作目录）：

```
python <skill目录>/code-scrape/codescrape.py run
```

产出：

| 文件 | 内容 |
|---|---|
| `<项目根>/out/核心代码名称.md` | 核心代码文件清单（纯路径，POSIX 分隔，UTF-8 无 BOM） |
| `<项目根>/out/源代码-{项目名}.md` | 按清单顺序连续拼接的源码正文（仅正文） |

统计摘要在生成完成后打印到会话（`--stats-json` 可落盘）：

```
[统计] 文件 70　物理行 3430　空行 0　注释行 142　有效代码行 3288　≈ 68.6 页
```

其他子命令：

```
python codescrape.py list    # 仅生成/更新清单
python codescrape.py pack    # 仅按清单汇总（清单须已存在，--auto-list 可自动生成）
python codescrape.py stat    # 只统计不产出文档
python codescrape.py scan    # 诊断：扫描命中 / 忽略 / 剪枝情况
python codescrape.py -h      # 全部参数
```

常用参数：`--project-name`（登记全称校正）、`--stats-json`、`--strict`、`--dry-run`、`--legacy-report`（与 V1.6 旧算法对照）、`--keep-path`（项目级白名单）。

## 测试

```
cd code-scrape
python -m unittest discover -s tests -p "test_*.py"     # 84 项，约 0.6 秒
```

## 目录结构

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 技能规则（清单生成规则的单一来源） |
| `code-scrape/codescrape.py` | CLI 入口（薄封装） |
| `code-scrape/codescrape/languages.py` | 语言定义表（60+ 扩展名 / 30+ 语言，含 SFC、heredoc、嵌套块注释） |
| `code-scrape/codescrape/loc.py` | 行数统计（单遍词法状态机 + 四口径） |
| `code-scrape/codescrape/listing.py` | 清单生成（采集 / 剔除 / 归类 / 排序 / 成对校验） |
| `code-scrape/codescrape/cli.py` | 子命令、参数校验、退出码 |
| `code-scrape/codescrape/reader.py`·`cleaner.py`·`markdown.py`·`report.py` | 读取编码链 / 清洗 / 文档组装 / 统计报告 |
| `code-scrape/codescrape/legacy_count.py` | V1.6 旧算法只读快照（仅供 `--legacy-report` 对照） |
| `code-scrape/tests/` | 84 项测试 + 黄金样例 fixtures |
| `code-scrape/方案-清单生成与源码汇总脚本化改造.md` | 改造方案与实施记录（含实测数据与验收标准） |
| `code-scrape/Version/版本更新说明.md` | 版本历史（当前 V2.0） |

## 口径说明

- **四口径**：物理行 = 空行 + 注释行 + 有效代码行（逐文件自检，不成立即报内部错误）
- 多行字符串与 docstring 计注释；混合行计代码；Shebang 与编码声明计注释
- **统计与产物对账**：`md 正文行数 = Σ各文件物理行 + 失败占位行 +（可选）分隔行`
- 忽略规则：项目根自备 `忽略规则.gitignore` 或 `--rules` 指定；都不存在则按「无规则」处理，**不创建文件**

## 许可

本仓库未附带开源许可文件；如需明确授权条款，请自行添加 `LICENSE`。
