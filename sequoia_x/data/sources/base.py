"""数据源抽象基类：定义所有数据源必须实现的统一接口。"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseDataSource(ABC):
    """数据源抽象基类。

    所有具体数据源（baostock / tushare / akshare / wind）必须继承此类，
    并实现所有抽象方法。

    设计原则：
    - 统一输入：股票代码统一为纯数字字符串（如 '000001'、'600519'）
    - 统一输出：DataFrame 列名统一为 [symbol, date, open, high, low, close, volume, turnover]
    - 复权方式：各数据源内部实现自行保证，默认采用后复权
    """

    name: str = "base"

    @abstractmethod
    def connect(self) -> bool:
        """建立连接 / 登录。返回 True 表示成功。"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接 / 登出。"""
        ...

    @abstractmethod
    def get_all_symbols(self) -> list[str]:
        """获取全市场 A 股代码列表。

        Returns:
            纯数字股票代码列表，如 ['000001', '600519', ...]
        """
        ...

    @abstractmethod
    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "1",
    ) -> pd.DataFrame:
        """拉取单只股票历史日 K 线数据。

        Args:
            symbol: 纯数字股票代码，如 '000001'
            start_date: 起始日期，格式 YYYY-MM-DD
            end_date: 截止日期，格式 YYYY-MM-DD
            adjustflag: 复权方式 '1'=后复权 '2'=前复权 '3'=不复权

        Returns:
            DataFrame，列名：symbol, date, open, high, low, close, volume, turnover
            无数据时返回空 DataFrame。
        """
        ...

    @abstractmethod
    def fetch_batch(
        self,
        tasks: list[tuple[str, str, str, str]],
    ) -> list[list]:
        """批量拉取多只股票历史数据（供多进程 worker 调用）。

        每个 worker 进程独立连接数据源，调用此方法拉取分配到的任务。

        Args:
            tasks: [(symbol, raw_code, start_date, end_date), ...]
                   raw_code 为数据源内部格式的代码（如 baostock 的 'sh.600000'）

        Returns:
            [[symbol, date, open, high, low, close, volume, turnover], ...]
        """
        ...

    @abstractmethod
    def get_stock_name(self, symbol: str) -> str:
        """查询单只股票名称。

        Args:
            symbol: 纯数字股票代码

        Returns:
            股票名称，如 '平安银行'；查询失败时返回 symbol 本身
        """
        ...

    @abstractmethod
    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        """批量查询股票名称。

        Args:
            symbols: 纯数字股票代码列表

        Returns:
            {code: name} 映射字典
        """
        ...

    @staticmethod
    def to_internal_code(symbol: str) -> str:
        """将纯数字代码转为数据源内部格式（子类可覆盖）。

        默认实现：6/9开头 → sh，其余 → sz（baostock 格式）。
        """
        prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
        return f"{prefix}.{symbol}"

    @staticmethod
    def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
        """将各数据源的列名统一为规范格式。"""
        col_map = {
            "amount": "turnover",
            "vol": "volume",
            "pct_chg": "pct_change",
            "trade_date": "date",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        required = ["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]
        for col in required:
            if col not in df.columns:
                df[col] = None
        return df[required]
