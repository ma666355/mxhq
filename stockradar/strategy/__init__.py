"""策略模块：自动发现并注册所有 BaseStrategy 子类。

新增策略只需将 .py 文件放入此目录，继承 BaseStrategy 并实现 run()，
无需修改 main.py 即可自动生效。
"""

import importlib
import pkgutil
from pathlib import Path

from stockradar.strategy.base import BaseStrategy


def discover_strategies() -> list[type[BaseStrategy]]:
    """自动扫描 strategy/ 下所有模块，发现 BaseStrategy 子类。

    Returns:
        BaseStrategy 子类列表（可直接用 engine + settings 实例化）。
    """
    classes: list[type[BaseStrategy]] = []
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in ("__init__", "base"):
            continue

        full_name = f"stockradar.strategy.{module_info.name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError as e:
            import logging
            logging.getLogger(__name__).warning(
                f"策略模块 {module_info.name} 导入失败: {e}"
            )
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
            ):
                classes.append(attr)

    return classes
