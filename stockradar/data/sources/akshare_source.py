"""AkShare 数据源实现（免费、无需注册、数据源丰富）。

官网：https://akshare.akfamily.xyz
文档：https://akshare.akfamily.xyz/data/stock/stock.html
"""

from __future__ import annotations

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.data.sources.base import BaseDataSource

logger = get_logger(__name__)


class AkShareDataSource(BaseDataSource):
    """AkShare 数据源。

    AkShare 是一个完全免费开源的 Python 财经数据接口库，支持 A 股、港股、
    期货、外汇等多种数据。无需注册，无需 API Key。

    注意：AkShare 底层爬取东方财富等公开网站，偶有接口变化需要升级版本。

    Attributes:
        name: 数据源标识，固定为 'akshare'
    """

    name: str = "akshare"

    def __init__(self) -> None:
        self._connected = False

    # ── 连接管理 ──

    def connect(self) -> bool:
        try:
            import akshare as ak  # noqa: F401
            self._connected = True
            return True
        except ImportError:
            logger.error("[akshare] 请先安装 akshare: pip install akshare")
            return False

    def disconnect(self) -> None:
        self._connected = False

    # ── 符号转换 ──

    @staticmethod
    def to_internal_code(symbol: str) -> str:
        """AkShare 直接使用纯数字代码，无需转换。"""
        return symbol

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        import akshare as ak

        try:
            # 获取沪深京 A 股实时行情列表
            df = ak.stock_zh_a_spot_em()
            if df.empty:
                logger.warning("[akshare] 获取股票列表为空")
                return []

            symbols = df["代码"].tolist()
            logger.info(f"[akshare] 获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"[akshare] 获取股票列表失败: {e}")
            return []

    # ── 历史数据 ──

    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "1",
    ) -> pd.DataFrame:
        import akshare as ak

        # 复权方式映射
        adjust_map = {
            "1": "qfq",   # 后复权
            "2": "qfg",   # 前复权
            "3": "",      # 不复权
        }
        adjust = adjust_map.get(adjustflag, "qfq")

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust,
            )

            if df.empty:
                return pd.DataFrame()

            # AkShare 标准列名映射
            col_map = {
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "turnover",
            }
            df = df.rename(columns=col_map)
            df["symbol"] = symbol

            # 类型转换
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["close"])
            df = df[df["volume"] > 0]
            df = df.sort_values("date")
            df = df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]]

            return df
        except Exception as e:
            logger.warning(f"[akshare] {symbol} 拉取失败: {e}")
            return pd.DataFrame()

    def fetch_batch(
        self,
        tasks: list[tuple[str, str, str, str]],
    ) -> list[list]:
        """批量拉取（AkShare 单进程串行，避免触发反爬）。"""
        import time

        results = []
        for symbol, _raw_code, start, end in tasks:
            df = self.fetch_history(symbol, start, end)
            if not df.empty:
                for _, row in df.iterrows():
                    results.append([
                        symbol,
                        str(row["date"]),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                        float(row["turnover"]),
                    ])
            time.sleep(0.1)  # 避免触发东方财富反爬
        return results

    # ── 股票名称 ──

    def get_stock_name(self, symbol: str) -> str:
        import akshare as ak

        try:
            # 通过个股信息查询
            df = ak.stock_individual_info_em(symbol=symbol)
            if not df.empty:
                # "股票简称" 行
                name_row = df[df["item"] == "股票简称"]
                if not name_row.empty:
                    return name_row.iloc[0]["value"]
        except Exception:
            pass
        return symbol

    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        """批量查询股票名称（通过全市场行情一次性获取）。"""
        import akshare as ak

        try:
            df = ak.stock_zh_a_spot_em()
            if df.empty:
                return {}

            df = df[df["代码"].isin(symbols)]
            return dict(zip(df["代码"], df["名称"]))
        except Exception as e:
            logger.warning(f"[akshare] 批量查询股票名称失败: {e}")
            return {}
