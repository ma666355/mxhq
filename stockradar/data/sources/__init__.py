"""数据源模块：支持 baostock / tushare / akshare / wind 多数据源接入。"""

from stockradar.data.sources.base import BaseDataSource
from stockradar.data.sources.baostock_source import BaostockDataSource
from stockradar.data.sources.tushare_source import TushareDataSource
from stockradar.data.sources.akshare_source import AkShareDataSource
from stockradar.data.sources.wind_source import WindDataSource

__all__ = [
    "BaseDataSource",
    "BaostockDataSource",
    "TushareDataSource",
    "AkShareDataSource",
    "WindDataSource",
]


def get_data_source(name: str, **kwargs) -> BaseDataSource:
    """根据名称返回对应的数据源实例。

    Args:
        name: 数据源名称，支持 'baostock' / 'tushare' / 'akshare' / 'wind'
        **kwargs: 传递给数据源的配置参数

    Returns:
        BaseDataSource 实例

    Raises:
        ValueError: 未知数据源名称
    """
    registry = {
        "baostock": BaostockDataSource,
        "tushare": TushareDataSource,
        "akshare": AkShareDataSource,
        "wind": WindDataSource,
    }
    name_lower = name.lower()
    if name_lower not in registry:
        raise ValueError(
            f"未知数据源: {name}，支持: {', '.join(registry.keys())}"
        )
    return registry[name_lower](**kwargs)
