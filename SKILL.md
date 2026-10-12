---
name: project-critical
description: Critical code 核心代码 — 软著核心代码文件清单生成。按先后端再前端、入口优先排序，剔除空包/样式/配置，输出纯路径Markdown到out文件夹。对齐《源程序AIGC指纹检查标准》：产出即"程序鉴别材料来源索引"，剔除项覆盖 Ck1 结构化文件头（空包）、Ck2 配置、Ck4 零逻辑工具文件，且清单可作为 project-review 三重一致性核对的代码侧索引。
whenToUse: 用户要求生成软著核心代码清单、列出核心代码文件名称、输出"核心代码"Markdown，或触发 project-critical（原 c-c）指令时。
user-invocable: true
---

# Critical Code 核心代码 (project-critical)

为软件著作权申请生成《核心代码文件清单》Markdown。产出物为纯路径清单，满足版权中心对"程序鉴别材料来源"的核验要求，并作为审查阶段"说明书功能 ↔ 代码实现"三重一致性核对的代码侧索引。

## 触发条件

- 用户输入 `project-critical`、`c-c`、`核心代码`、`critical code`、`核心代码清单`、`软著核心代码`
- 或在软著流程中需要列出后端/前端核心源码文件时

## 输入

- 可选：软件名称（仅用于 Markdown 首行标题展示，不参与命名）。输出文件名固定为 `核心代码名称.md`，与软件名称无关。
- 可选：项目根路径（默认当前工作目录 `process.cwd()`，约定结构见下）。

## 与源程序标准的关系（对齐说明）

本清单是「程序鉴别材料的来源索引」。它用路径剔除规则隐式落实《源程序AIGC指纹检查标准》的几类判定：
- 剔除**空包**文件（`__init__.py` 空、`package-info.java` 空、<50 字节 re-export）→ 对齐 Ck1/审查员"空包不算源码"要求；
- 剔除**样式/配置**文件 → 不污染"核心逻辑"清单，避免将声明式内容计为核心代码；
- 保留**业务实现逻辑**（controller/service/entity/mapper、前端 api/store/views）→ 构成三重一致性核对时"代码有实现功能"的完整索引，供 project-review 逐项 vs 说明书功能清单比对。

> 提示：本清单是"是什么"，不评判"对不对"。代码里是否残留 AI 指纹（结构化文件头、教学腔、零 TODO）属 `aigc-c` 独立技能职责，本 skill 只保证清单真实、纯净、按序。

## 项目结构约定（探测优先级）

1. 读取 `2-skills/README.md` 或项目根 `README.md` 确认约定；无则按以下优先级探测：
   - `code/backend` + `code/frontend` + `code/db` + `docs/` + `out/`（标准软著项目）
   - `backend/` + `frontend/` / `src/` + `server/`（扁平项目）
   - `src/main/java` + `src/main/resources` + `src/views` 或 `src/pages`（Java+Vue/React）
   - 单体 `src/` 需通过文件内容与依赖（package.json / pom.xml / requirements.txt）二次判定前后端归属
2. 若均未命中，则以当前目录为根全量扫描后按扩展名与路径关键字归类。

## 执行步骤（严格按序）

### Step 0 — 探测与确认
- 用 `glob` 全量扫描候选（见 Step 1），统计后端/前端文件数与入口是否命中。
- 软件名称仅作首行标题的可选展示用：可从 README 标题、package.json 或用户输入获取，获取不到则标题直接用"核心代码文件清单"；**文件名始终为固定的 `核心代码名称.md`，绝不根据软件名称变化**。

### Step 1 — 采集候选文件（全量，不抽样）
按以下扩展名全量采集（递归，忽略 `node_modules/`, `.git/`, `dist/`, `build/`, `.idea/`, `.vscode/`, `__pycache__/`, `.next/`, `.nuxt/`, `coverage/`, `out/`, `docs/`）：
- 后端：`.java`, `.py`, `.go`, `.ts`（后端）, `.js`（后端）, `.php`, `.cs`, `.cpp`, `.c`
- 前端（Web）：`.vue`, `.tsx`, `.jsx`, `.ts`（前端）, `.js`（前端）
- 前端（**微信小程序，四件套中必须有 `.wxml`**）：`.js`（小程序页面/组件逻辑，与 Web 前端 `.js` 同判）、**`.wxml`（页面结构程序，属核心实现逻辑，必须采集、不得遗漏）**；`.wxss`（样式）与 `.json`（配置）不采集，见 Step 2。
- 排除：`.json`, `.xml`, `.yml`, `.yaml`, `.toml`, `.properties`, `.gradle`, `.md`, `.txt`, `.sql`, `.html`（纯模板除外，`.vue` 保留）、`.wxss`（小程序样式）

> **微信小程序辨识**：项目存在 `app.json`、`project.config.json`、`miniprogram`/`miniprogramRoot`、`app.js`+`app.json`+`app.wxss` 同目录等特征即判为微信小程序工程；其页面按「`.js`（页面逻辑）+ `.wxml`（页面结构）」成对采集，`.wxss` 样式、`.json` 配置不采集。**只要项目/目录含小程序页面，`.wxml` 必须全量进入清单，禁止遗漏、禁止当配置文件剔除。**

> 前后端归属判定：路径含 `backend`/`server`/`src/main/java`/`app/backend` 归后端；含 `frontend`/`client`/`src/views`/`src/pages`/`src/components`/`src/api`/`src/store` 归前端；微信小程序页面（如 `pages/**`、`components/**` 下的 `.js`/`.wxml`）归前端；模糊路径按 `package.json`/`app.json` 依赖与文件内容辅助判定。

### Step 2 — 过滤（必须剔除，宁可错杀样式/配置，不可漏入）
**一律剔除：**
1. **空包文件**：内容为空或仅含包声明的 `__init__.py`、`package-info.java`、空 `index.ts` 仅 re-export 且无逻辑（文件 < 50 bytes 且无实质代码）。
2. **样式文件**：`*.css`, `*.scss`, `*.less`, `*.styl`, `*.sass`, `*.wxss` 等纯样式（**注意：`*.wxml` 是页面结构程序、不是样式，保留**）；`.vue` 中的 `<style>` 块不单独计文件，`.vue` 本体保留。
3. **程序配置文件**：`vite.config.*`, `vue.config.*`, `webpack.config.*`, `tsconfig.json`, `jsconfig.json`, `.eslintrc*`, `.prettierrc*`, `babel.config.*`, `.env*`, `application*.yml`, `application*.properties`, `settings.py`、`pom.xml`, `build.gradle`, `package.json`, `Dockerfile`、**微信小程序 `app.json` / `project.config.json` / 各页面 `.json`（配置）** 等。
4. **构建产物与依赖**：`dist/`, `build/`, `target/`, `node_modules/`, `vendor/`。
5. **文档与脚本**：`docs/`, `*.md`, `*.sql`、`*.sh`, `mock/` 仅 mock 数据。

**必须保留：**
- 前端页面（Web）：`src/views/**`, `src/pages/**`, `src/components/**`（含业务逻辑的组件）
- 前端实现逻辑（Web）：`src/api/**`, `src/store/**`, `src/router/**`, `src/utils/**`、`src/hooks/**`、`App.vue/tsx`
- **前端页面（微信小程序，四件套缺一不漏）**：**`.js` 页面逻辑 + `.wxml` 页面结构必须成对保留**；即 `pages/**`、`components/**` 下的小程序 `.js` 与**对应 `.wxml` 一律保留**；页面/组件的 `.json`（配置）剔除，`.wxss`（样式）剔除。
- 后端实现逻辑：`controller`/`api`/`handler`, `service/**`, `entity/**`/`model/**`, `mapper/**`/`repository/**`, `dto/**`/`vo/**`/`schema/**`, 业务 `config`、业务 `util`

### Step 3 — 排序（核心规则，不可违背）
**总序：先后端，再前端。** 后端清单在前，前端清单在后。
**后端内排序（入口/主程序优先）：**
1. 入口/启动类最前：`*Application.java`、`main.py`/`app.py`/`run.py`/`manage.py`、`main.go`、`Program.cs`、`index.js`/`server.js`
2. 次级：业务 `config` → `controller` → `service` → `service/impl` → `mapper`/`repository` → `entity`/`model` → `dto` → `util`
3. 同级内字典序。
**前端内排序（入口/主程序优先）：**
1. 入口最前：`main.ts`/`main.js`/`index.ts`/`index.js`、`App.vue`/`App.tsx`、`router/index.*`；**微信小程序入口 `app.js` + 全局 `app.wxml`（若有）排前**
2. 次级：`src/api/**` → `src/store/**` → `src/views/**`/`src/pages/**` → `src/components/**` → `src/utils/**`/`src/hooks/**`；**微信小程序页面按页内 `.js` 与其同名 `.wxml` 相邻列出（`.js` 在前、`.wxml` 随后，再下一页）**，`pages/**`/`components/**` 内同名 `.js`/`.wxml` 成对排布
3. 同级内字典序。

### Step 4 — 生成 Markdown（唯一产出）
- **输出目录**：项目根 `out/`；若不存在则创建。兼容 `3-out/`。**本项目约定**：新输出统一归到 `03-审查产物/` 下相应子目录（`out/` 已归档为 `03-审查产物/历史输出-out`），除非 `agent.md` 另有规定。
- **文件名**：无论软件名称是什么，输出文件名都固定为 `核心代码名称.md`（唯一产出，不依软件名称变化，也不生成任何副本）。
- **文件内容（严格）：**
```markdown
# 核心代码文件清单

code/backend/src/main/java/com/example/Application.java
code/backend/src/main/java/com/example/controller/UserController.java
...
code/frontend/src/views/Login.vue
code/frontend/src/api/user.ts
...
```
约束：
1. 文档只包含文件路径，一行一个，不含序号、项目符号、表格。
2. 路径使用 POSIX 风格（`/` 分隔），相对路径，不含盘符。
3. 不包含空包、样式、配置文件的条目；前端页面及其 `api/store/utils` 逻辑必须成对出现。
4. **微信小程序不遗漏 `.wxml`**：凡含小程序页面/组件的目录，该目录下每个 `.js` 对应的 `.wxml` 必须出现在清单中，**禁止省略/遗漏任何 `.wxml`**（`.wxss` 样式、`.json` 配置除外）；小程序 `.js` 与 `.wxml` 成对列出。
5. 编码 UTF-8，无 BOM。
- **校验**：生成后回扫每条路径确实存在；统计后端/前端数量并在日志中输出，但不写入正文；**小程序校验额外核对：每个小程序页面 `.js` 是否存在同名 `.wxml` 且均已入清单（缺一即返工补全）**。

### Step 5 — 自检与交付
- 复核：抽检 3~5 条路径确认非样式/配置、非空包；确认入口文件位于段首。
- 汇报：输出路径、文件数、排序依据、已剔除类型。
- 提醒：该清单为"程序鉴别材料来源索引"，正式提交的 60 页源代码文档需按此清单顺序排版前后各 30 页连续片段；并可用于 project-review 三重一致性核对。

## 配套脚本（V2.0 起，可选加速）

`code-scrape/` 提供与本文件规则**同源**的无界面命令行工具（Python 3.10+，运行时零第三方依赖），在项目根**零参数**执行即可产出 Step 4 的清单：

```
python <skill目录>/code-scrape/codescrape.py run     # 生成清单 + 按清单汇总源代码 md
```

- **产出**：`<项目根>/out/核心代码名称.md`（与 Step 4 完全同格式，可直接作为唯一产出交付）；个别项目要求输出到 `03-审查产物/` 时用 `-l`/`-o` 覆盖路径。汇总 md 只含源码正文（无头部统计），统计在生成完成后输出到会话（`--stats-json` 可落盘）。
- **子命令**：`run`（清单+汇总）/ `list`（仅清单）/ `pack`（仅汇总）/ `stat`（只统计）/ `scan`（诊断扫描命中与剪枝）；参数见 `codescrape.py -h`。
- **唯一例外（以脚本实现为准）**：脚本把 `manage.py` 判为框架脚手架而**剔除**（`FRAMEWORK_ADMIN_FILES`），与 Step 3 的入口列表不一致——它属 Django 脚手架而非业务实现；确需保留时用 `--keep-path manage.py` 加入白名单。
- **规则单一来源**：清单规则仍以本文件为准；脚本的规则常量集中在 `code-scrape/codescrape/listing.py` 顶部并逐条标注对应本文件章节，规则漂移时定点修改并对真实项目回归。
- **排序落地细化（不改 Step 3 语义）**：脚本严格按本文件 Step 3 排序（入口分档 `main.*`/`index.*` → `App.*` → `router/index.*`；次级 config → controller → service → mapper/repository → entity/model → dto → util 与 api → store → views/pages → components → utils/hooks），仅对 Step 3 未逐一列举的情况作等价细化：启动脚本（`start_server.py`/`start.py`/`bootstrap.*`）按「入口/启动类」归入口；`database.py` 按「业务 config」归配置层；Django `urls.py` 与 `views.py` 同属接口层；NestJS 等「层次体现在文件名」的框架按 `.controller.`/`.service.`/`.dto.` 等后缀映射到对应层次且**不做业务模块分组**；类别表含常见复数/别名（`routers`/`services`/`models`/`schemas`/`stores`/`composables` 等）；小程序页面 `.js` 与同名 `.wxml`/`.axml` 成对相邻。

## 排除清单速查表

| 类型 | 典型文件 | 处理 | 对齐标准 |
|------|---------|------|---------|
| 空包 | `__init__.py` 空文件, `package-info.java` 空 | 剔除 | Ck1 结构化文件头/空包 |
| 样式 | `*.css/scss/less`, `src/styles/**`, `*.wxss` | 剔除（`*.wxml` 不是样式，保留） | 非核心逻辑 |
| 配置 | `vite.config.ts`, `tsconfig.json`, `application.yml`, `.env`, 微信小程序 `*.json` | 剔除 | Ck2 编码/配置 |
| 构建 | `dist/**`, `node_modules/**` | 剔除 | 依赖/构建产物 |
| 微信小程序 | 页面 `pages/**` 的 `.js` + **同名 `.wxml`** | **两者保留、成对列出**；`app.js`+`app.wxml`(若有)排前；`.wxss`/`.json` 剔除 | 核心实现逻辑（页面结构程序不遗漏） |
| 保留 | `*.vue`, `*.tsx` 页面, `controller/service/entity/mapper`, `api/store/router` | 保留 | 核心实现逻辑 |

## 常见项目映射示例
- **Spring Boot + Vue**：后端 `Application.java` → `controller` → `service` → `mapper` → `entity`；前端 `main.ts` → `App.vue` → `router` → `api` → `views`
- **FastAPI + React**：后端 `run.py`/`main.py` → `api/` → `services/` → `models/` → `schemas/`；前端 `main.tsx` → `App.tsx` → `api/` → `pages/`
- **Django + Vue**：后端 `manage.py` → `views.py` → `models.py` → `serializers.py`；前端同上
- **Spring Boot + 微信小程序**：后端 `Application.java` → `controller` → `service` → `mapper` → `entity`；前端 `app.js` →（全局 `app.wxml` 若有）+ 各页面 `pages/xxx.js` 与其同名 `xxx.wxml` 成对（如 `pages/index/index.js`、`pages/index/index.wxml`），组件 `components/xxx.js` 与其同名 `xxx.wxml` 成对

## 注意事项
- 不得编造不存在的文件路径；所有路径必须经 `glob` 验证存在。
- 不得将样式/配置/空包计入数量。
- **微信小程序 `.wxml` 一律不得遗漏**：页面的 `.js` + 同名 `.wxml` 必须成对入清单（页面结构程序是核心实现逻辑，不是配置/样式）；仅 `.wxss` 样式、`.json` 配置剔除。
- 若项目暂无代码（如当前工作区为文档仓），则生成空清单模板并注明"待代码落盘后按此规则重新生成"。
- 关联 skill：`aigc-c`（独立，源码 AIGC 指纹去除）、`project-review`（一致性核对）、`project-guide`（说明书功能清单与本品内容对照）。