"""数据源模块：自动发现并注册所有 BaseDataSource 子类。

新增数据源只需将 .py 文件放入此目录，继承 BaseDataSource 并实现接口方法，
无需修改此处 registry 即可自动生效。
"""

import importlib
import pkgutil
from pathlib import Path

from stockradar.data.sources.akshare_source import AkShareDataSource
from stockradar.data.sources.baostock_source import BaostockDataSource
from stockradar.data.sources.base import BaseDataSource
from stockradar.data.sources.tushare_source import TushareDataSource
from stockradar.data.sources.wind_source import WindDataSource

__all__ = [
    "BaseDataSource",
    "BaostockDataSource",
    "TushareDataSource",
    "AkShareDataSource",
    "WindDataSource",
    "get_data_source",
    "discover_sources",
]


def discover_sources() -> dict[str, type[BaseDataSource]]:
    """自动扫描 sources/ 下所有模块，发现 BaseDataSource 子类。

    返回 {name: class} 映射，其中 name 取自类的 name 属性。
    内置 4 个实现优先注册，额外模块动态追加。

    Returns:
        数据源名称到类的映射字典。
    """
    registry: dict[str, type[BaseDataSource]] = {}
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        # 跳过 __init__ 和 base
        if module_info.name in ("__init__", "base"):
            continue

        full_name = f"stockradar.data.sources.{module_info.name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError as e:
            import logging
            logging.getLogger(__name__).warning(
                f"数据源模块 {module_info.name} 导入失败: {e}"
            )
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseDataSource)
                and attr is not BaseDataSource
                and hasattr(attr, "name")
                and attr.name not in registry
            ):
                registry[attr.name] = attr

    return registry


def get_data_source(name: str, **kwargs) -> BaseDataSource:
    """根据名称返回对应的数据源实例。

    先尝试内置 registry，再回退到自动发现，
    确保新数据源无需手动注册即可使用。

    Args:
        name: 数据源名称，支持 'baostock' / 'tushare' / 'akshare' / 'wind'
        **kwargs: 传递给数据源的配置参数

    Returns:
        BaseDataSource 实例

    Raises:
        ValueError: 未知数据源名称
    """
    # 优先使用自动发现的 registry（覆盖手动导入）
    registry = discover_sources()

    name_lower = name.lower()
    if name_lower not in registry:
        raise ValueError(
            f"未知数据源: {name}，支持: {', '.join(sorted(registry.keys()))}"
        )
    cls = registry[name_lower]
    # 仅 tushare 接受 token，其他数据源过滤掉无关参数
    if name_lower != "tushare":
        kwargs.pop("token", None)
    return cls(**kwargs)
