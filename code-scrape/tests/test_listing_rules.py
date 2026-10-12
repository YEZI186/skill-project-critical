"""
测试名称: 清单生成规则
文件名称: test_listing_rules.py
测试目的: 用临时构造的迷你工程验证「剔除（空包/样式/配置/文档脚本）→ 前后端归类
          → 入口优先排序 → 小程序 js↔wxml 成对校验 → 违禁自检」全链路
"""

import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from codescrape.listing import (generate, is_miniprogram, parse_listing, render)


def _write(path: str, text: str = "x = 1\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class ListingRuleTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _make_backend_frontend(self):
        r = self.root
        # 后端
        _write(f"{r}/backend/src/main/java/com/x/Application.java", "public class Application {}\n")
        _write(f"{r}/backend/src/main/java/com/x/config/WebConfig.java", "public class WebConfig {}\n")
        _write(f"{r}/backend/src/main/java/com/x/controller/AController.java", "public class AController {}\n")
        _write(f"{r}/backend/src/main/java/com/x/service/AService.java", "public interface AService {}\n")
        _write(f"{r}/backend/src/main/java/com/x/service/impl/AServiceImpl.java", "public class AServiceImpl {}\n")
        _write(f"{r}/backend/src/main/java/com/x/mapper/AMapper.java", "public interface AMapper {}\n")
        _write(f"{r}/backend/src/main/java/com/x/entity/A.java", "public class A {}\n")
        _write(f"{r}/backend/src/main/java/com/x/dto/ADTO.java", "public class ADTO {}\n")
        _write(f"{r}/backend/src/main/java/com/x/util/U.java", "public class U {}\n")
        # 应剔除
        _write(f"{r}/backend/src/main/java/com/x/package-info.java", "package com.x;\n")
        _write(f"{r}/backend/src/main/java/com/x/Empty.java", "")
        _write(f"{r}/backend/src/main/resources/application.yml", "server:\n  port: 8080\n")
        _write(f"{r}/backend/src/main/resources/static/app.css", ".a{}\n")
        _write(f"{r}/backend/pom.xml", "<project/>\n")
        # 前端
        _write(f"{r}/frontend/src/main.ts", "import { createApp } from 'vue';\n")
        _write(f"{r}/frontend/src/api/user.ts", "export const a = 1;\n")
        _write(f"{r}/frontend/src/views/Login.vue", "<template><div/></template>\n")
        _write(f"{r}/frontend/src/styles/a.scss", ".b{}\n")
        _write(f"{r}/frontend/src/utils/date.ts", "export const d = 1;\n")
        _write(f"{r}/frontend/package.json", "{}\n")
        _write(f"{r}/frontend/index.ts", "export * from './src/main';\n")
        _write(f"{r}/README.md", "# 说明\n")

    def test_backend_frontend_order_and_exclusions(self):
        self._make_backend_frontend()
        result = generate(self.root)
        got = result.paths
        want = [
            "backend/src/main/java/com/x/Application.java",
            "backend/src/main/java/com/x/config/WebConfig.java",
            "backend/src/main/java/com/x/controller/AController.java",
            "backend/src/main/java/com/x/service/AService.java",
            "backend/src/main/java/com/x/service/impl/AServiceImpl.java",
            "backend/src/main/java/com/x/mapper/AMapper.java",
            "backend/src/main/java/com/x/entity/A.java",
            "backend/src/main/java/com/x/dto/ADTO.java",
            "backend/src/main/java/com/x/util/U.java",
            "frontend/src/main.ts",
            "frontend/src/api/user.ts",
            "frontend/src/views/Login.vue",
            "frontend/src/utils/date.ts",
        ]
        self.assertEqual(want, got)
        self.assertEqual([], result.violations)
        self.assertFalse(result.is_miniprogram)
        # 剔除分桶可诊断
        for reason in ("配置", "样式", "空包", "文档/脚本"):
            self.assertIn(reason, result.stats["excluded"], reason)

    def test_render_has_title_and_section_gap(self):
        self._make_backend_frontend()
        content = generate(self.root).content
        lines = content.split("\n")
        self.assertEqual("# 核心代码文件清单", lines[0])
        self.assertEqual("", lines[1])
        backend_idx = lines.index("backend/src/main/java/com/x/util/U.java")
        self.assertEqual("", lines[backend_idx + 1])   # 前后端之间空行
        self.assertEqual("frontend/src/main.ts", lines[backend_idx + 2])
        self.assertTrue(content.endswith("\n"))
        # 解析回去应等于原始条目
        self.assertEqual(generate(self.root).paths, parse_listing(content))

    def test_miniprogram_pairing_check(self):
        r = self.root
        _write(f"{r}/app.js", "App({})\n")
        _write(f"{r}/app.wxss", ".a{}\n")
        _write(f"{r}/app.json", "{}\n")
        _write(f"{r}/pages/index/index.js", "Page({})\n")
        _write(f"{r}/pages/index/index.wxml", "<view/>\n")
        _write(f"{r}/pages/broken/broken.js", "Page({})\n")   # 缺 .wxml
        _write(f"{r}/api/user.js", "export const a = 1;\n")
        _write(f"{r}/utils/req.js", "export const b = 2;\n")
        self.assertTrue(is_miniprogram(r))
        result = generate(r)
        self.assertTrue(result.is_miniprogram)
        # app.js / api / utils 所在目录没有 .wxml，不得误报
        self.assertEqual(1, len(result.pairing_issues), result.pairing_issues)
        self.assertIn("broken.js", result.pairing_issues[0])
        paths = result.paths
        self.assertEqual("app.js", paths[0])                      # 小程序入口最前
        self.assertLess(paths.index("pages/index/index.js"),
                        paths.index("pages/index/index.wxml"))     # js 在 wxml 前
        self.assertEqual([], result.violations)

    def test_empty_project(self):
        result = generate(self.root)
        self.assertEqual([], result.paths)
        self.assertEqual("# 核心代码文件清单\n", result.content)

    def test_skip_dirs_prunes_archives(self):
        r = self.root
        _write(f"{r}/backend/src/main/java/com/x/Application.java", "public class Application {}\n")
        _write(f"{r}/out/核心代码名称.md", "x\n")
        _write(f"{r}/out/archive/OldService.java", "public class OldService {}\n")
        _write(f"{r}/node_modules/pkg/index.js", "module.exports = 1;\n")
        _write(f"{r}/docs/demo.java", "public class Demo {}\n")
        result = generate(r)
        self.assertEqual(["backend/src/main/java/com/x/Application.java"], result.paths)

    def test_d13_manage_and_demo_dirs_excluded(self):
        """裁定行为：manage.py 与演示/模拟设施不入清单；FastAPI app/main.py 入清单"""
        r = self.root
        _write(f"{r}/manage.py", "import os\n\n\ndef main():\n    pass\n")
        _write(f"{r}/cotton/settings.py", "DEBUG = True\n")
        _write(f"{r}/apps/acquisition/views.py", "def v():\n    return 1\n")
        _write(f"{r}/terminal_simulator/terminal.py", "print('sim')\n")
        _write(f"{r}/backend/app/main.py", "app = object()\n")
        result = generate(r)
        self.assertEqual(["backend/app/main.py", "apps/acquisition/views.py"], result.paths)
        self.assertIn("框架管理脚本", result.stats["excluded"])
        self.assertIn("演示/模拟设施", result.stats["excluded"])

    def test_keep_paths_overrides_exclusion(self):
        """项目级白名单：产品本体即模拟器时可用 keep_paths 覆盖"""
        r = self.root
        _write(f"{r}/terminal_simulator/terminal.py", "print('sim')\n")
        result = generate(r, keep_paths=("terminal_simulator",))
        self.assertEqual(["terminal_simulator/terminal.py"], result.paths)


class Step3OrderTest(unittest.TestCase):
    """SKILL.md Step 3 排序对齐：类别次序、别名/复数目录、入口分档、小程序成对"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_backend_alias_dirs_follow_step3(self):
        """config(database) → controller(routers) → service(services) → entity(model) → dto(schema) → util"""
        r = self.root
        _write(f"{r}/backend/app/main.py", "app = object()\n")
        _write(f"{r}/backend/app/config.py", "DEBUG = True\n")
        _write(f"{r}/backend/app/database.py", "engine = object()\n")
        _write(f"{r}/backend/app/routers/auth.py", "router = object()\n")
        _write(f"{r}/backend/app/services/user.py", "def f():\n    return 1\n")
        _write(f"{r}/backend/app/models/user.py", "class U:\n    pass\n")
        _write(f"{r}/backend/app/schemas/user.py", "class S:\n    pass\n")
        _write(f"{r}/backend/app/utils/response.py", "def ok():\n    return 1\n")
        self.assertEqual(generate(r).paths, [
            "backend/app/main.py",
            "backend/app/config.py",
            "backend/app/database.py",
            "backend/app/routers/auth.py",
            "backend/app/services/user.py",
            "backend/app/models/user.py",
            "backend/app/schemas/user.py",
            "backend/app/utils/response.py",
        ])

    def test_startup_script_counts_as_entry(self):
        """SKILL.md「入口/启动类最前」：start_server.py 与 main.py 同档，紧跟其后"""
        r = self.root
        _write(f"{r}/backend/start_server.py", "uvicorn.run('app')\n")
        _write(f"{r}/backend/app/main.py", "app = object()\n")
        _write(f"{r}/backend/app/routers/auth.py", "router = object()\n")
        self.assertEqual(generate(r).paths, [
            "backend/app/main.py",
            "backend/start_server.py",
            "backend/app/routers/auth.py",
        ])

    def test_frontend_alias_dirs_and_entry_tiers_follow_step3(self):
        """入口：main.* → App.* → router/index.*；次级：api → store → views → components → utils"""
        r = self.root
        _write(f"{r}/frontend/src/App.vue", "<template/>\n")
        _write(f"{r}/frontend/src/main.ts", "import x from 'x'\n")
        _write(f"{r}/frontend/src/router/index.ts", "export const r = 1\n")
        _write(f"{r}/frontend/src/api/user.ts", "export const a = 1\n")
        _write(f"{r}/frontend/src/stores/user.ts", "export const s = 1\n")
        _write(f"{r}/frontend/src/views/Home.vue", "<template/>\n")
        _write(f"{r}/frontend/src/components/Card.vue", "<template/>\n")
        _write(f"{r}/frontend/src/composables/useX.ts", "export const u = 1\n")
        _write(f"{r}/frontend/src/utils/request.ts", "export const q = 1\n")
        self.assertEqual(generate(r).paths, [
            "frontend/src/main.ts",
            "frontend/src/App.vue",
            "frontend/src/router/index.ts",
            "frontend/src/api/user.ts",
            "frontend/src/stores/user.ts",
            "frontend/src/views/Home.vue",
            "frontend/src/components/Card.vue",
            "frontend/src/composables/useX.ts",
            "frontend/src/utils/request.ts",
        ])

    def test_utils_dir_wins_over_filename_stem(self):
        """utils/request.ts 属 utils 组（SKILL.md 按目录），不得因文件名被提到 api 组"""
        r = self.root
        _write(f"{r}/frontend/src/utils/request.ts", "export const q = 1\n")
        _write(f"{r}/frontend/src/views/Home.vue", "<template/>\n")
        self.assertEqual(generate(r).paths,
                         ["frontend/src/views/Home.vue", "frontend/src/utils/request.ts"])

    def test_nestjs_suffix_categories_use_global_order(self):
        """层次体现在文件名时仍全局归类（controller → service → dto），不做业务模块分组"""
        r = self.root
        _write(f"{r}/backend/src/main.ts", "bootstrap()\n")
        _write(f"{r}/backend/src/beta/beta.controller.ts", "export class B {}\n")
        _write(f"{r}/backend/src/alpha/alpha.service.ts", "export class A {}\n")
        _write(f"{r}/backend/src/alpha/dto/alpha.dto.ts", "export class D {}\n")
        _write(f"{r}/backend/src/alpha/alpha.module.ts", "export class M {}\n")
        self.assertEqual(generate(r).paths, [
            "backend/src/main.ts",
            "backend/src/beta/beta.controller.ts",
            "backend/src/alpha/alpha.service.ts",
            "backend/src/alpha/dto/alpha.dto.ts",
            "backend/src/alpha/alpha.module.ts",
        ])

    def test_django_views_urls_models_utils_order(self):
        """Django：urls.py（路由层）与 views.py（接口层）同组 → models → utils → apps.py（其它）"""
        r = self.root
        _write(f"{r}/apps/acquisition/views.py", "def v():\n    return 1\n")
        _write(f"{r}/apps/acquisition/urls.py", "urlpatterns = []\n")
        _write(f"{r}/apps/acquisition/models.py", "class M:\n    pass\n")
        _write(f"{r}/apps/acquisition/apps.py", "class C:\n    pass\n")
        _write(f"{r}/utils/pricing.py", "def p():\n    return 1\n")
        self.assertEqual(generate(r).paths, [
            "apps/acquisition/urls.py",
            "apps/acquisition/views.py",
            "apps/acquisition/models.py",
            "utils/pricing.py",
            "apps/acquisition/apps.py",
        ])

    def test_miniprogram_app_wxml_entry_and_structure_pairing(self):
        """小程序：app.js + 全局 app.wxml 排前；页面 .js 紧跟同名 .wxml/.axml"""
        r = self.root
        _write(f"{r}/app.js", "App({})\n")
        _write(f"{r}/app.wxml", "<view/>\n")
        _write(f"{r}/app.json", "{}\n")
        _write(f"{r}/pages/a/a.js", "Page({})\n")
        _write(f"{r}/pages/a/a.wxml", "<view/>\n")
        _write(f"{r}/pages/b/b.js", "Page({})\n")
        _write(f"{r}/pages/b/b.axml", "<view/>\n")
        result = generate(r)
        got = result.paths
        self.assertEqual(got[0], "app.js")
        self.assertEqual(got[1], "app.wxml")
        self.assertLess(got.index("pages/a/a.js"), got.index("pages/a/a.wxml"))
        self.assertLess(got.index("pages/b/b.js"), got.index("pages/b/b.axml"))
        self.assertEqual([], result.pairing_issues)   # .axml 也算配对，不得误报


if __name__ == "__main__":
    unittest.main()
