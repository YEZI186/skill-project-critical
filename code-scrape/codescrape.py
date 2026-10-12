"""
模块名称: 命令行入口（薄封装）
文件名称: codescrape.py
模块类型: 入口模块
功能描述: 软著核心代码清单与源码汇总的唯一命令入口。

用法（在项目根目录直接执行，零路径参数、不需要选择项目）：

    python <skill目录>/codescrape.py run

项目根 = 当前工作目录；清单与汇总 md 自动落到 <cwd>/out/。
子命令：run / list / pack / stat / scan，详见 `python codescrape.py -h`。
"""

import os
import sys

# 确保无论从哪个工作目录执行，都能导入同目录下的 codescrape 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codescrape.cli import main  # noqa: E402  （路径注入后才可导入）

if __name__ == "__main__":
    sys.exit(main())
