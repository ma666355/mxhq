"""Tushare 数据源实现（需要注册获取 token）。

官网：https://tushare.pro
注册后可免费使用基础接口，部分高级接口需要积分。
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.data.sources.base import BaseDataSource

logger = get_logger(__name__)


class TushareDataSource(BaseDataSource):
    """Tushare 数据源。

    使用前需要在 https://tushare.pro 注册并获取 API token。
    免费用户有调用频次限制，建议配合 time.sleep 控制频率。

    Attributes:
        name: 数据源标识，固定为 'tushare'
        token: Tushare API token（必填）
    """

    name: str = "tushare"

    def __init__(self, token: str = "") -> None:
        self.token: str = token
        self._api: Any = None

    # ── 连接管理 ──

    def connect(self) -> bool:
        if not self.token:
            logger.error("[tushare] token 未配置，请在 .env 中设置 TUSHARE_TOKEN")
            return False
        try:
            import tushare as ts
            ts.set_token(self.token)
            self._api = ts.pro_api()
            # 简单验证：拉取一只股票的最新交易日数据
            _ = self._api.daily(ts_code="000001.SZ", start_date="20240101", end_date="20240101")
            return True
        except ImportError:
            logger.error("[tushare] 请先安装 tushare: pip install tushare")
            return False
        except Exception as e:
            logger.error(f"[tushare] 连接失败: {e}")
            return False

    def disconnect(self) -> None:
        self._api = None

    # ── 符号转换 ──

    @staticmethod
    def to_internal_code(symbol: str) -> str:
        """纯数字代码 → tushare 格式：000001.SZ / 600519.SH / 8/4开头.BJ。"""
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        elif symbol.startswith(("4", "8")):
            return f"{symbol}.BJ"
        return f"{symbol}.SZ"

    @staticmethod
    def to_raw_code(ts_code: str) -> str:
        """tushare 格式 → 纯数字代码。"""
        return ts_code.split(".")[0]

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        if not self._api:
            if not self.connect():
                return []

        try:
            df = self._api.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name",
            )
            if df.empty:
                logger.warning("[tushare] 获取股票列表为空")
                return []

            # 过滤：只保留沪深京 A 股
            symbols = df["symbol"].tolist()
            logger.info(f"[tushare] 获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"[tushare] 获取股票列表失败: {e}")
            return []

    # ── 历史数据 ──

    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "1",
    ) -> pd.DataFrame:
        if not self._api:
            if not self.connect():
                return pd.DataFrame()

        ts_code = self.to_internal_code(symbol)
        # tushare 日期格式：YYYYMMDD
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")

        try:
            # 1. 日线基础数据（不复权）
            df = self._api.daily(
                ts_code=ts_code,
                start_date=start,
                end_date=end,
                fields="trade_date,open,high,low,close,vol,amount",
            )
            if df.empty:
                return pd.DataFrame()

            # 2. 复权因子：1=后复权，2=前复权，3=不复权
            if adjustflag in ("1", "2"):
                time.sleep(0.3)  # tushare 免费用户频次限制
                adj_df = self._api.adj_factor(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                )
                if adj_df.empty:
                    logger.warning(f"[tushare] {symbol} 复权因子为空")
                    return pd.DataFrame()
                df = df.merge(adj_df, on="trade_date", how="left")
                df["adj_factor"] = pd.to_numeric(
                    df["adj_factor"], errors="coerce"
                )
                if adjustflag == "1":
                    price_factor = df["adj_factor"]
                else:
                    valid_factors = df.dropna(subset=["adj_factor"])
                    if valid_factors.empty:
                        return pd.DataFrame()
                    latest_row = valid_factors.sort_values(
                        "trade_date"
                    ).iloc[-1]
                    latest_factor = latest_row["adj_factor"]
                    price_factor = df["adj_factor"] / latest_factor
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col] * price_factor

            df = df.rename(columns={
                "trade_date": "date",
                "vol": "volume",
                "amount": "turnover",
            })
            df["symbol"] = symbol

            # 类型转换
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Tushare 日线单位：成交量=手、成交额=千元；统一为股、元。
            df["volume"] = df["volume"] * 100
            df["turnover"] = df["turnover"] * 1_000

            df = df.dropna(subset=["close"])
            df = df[df["volume"] > 0]
            df = df.sort_values("date")
            df = df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]]

            # 日期格式从 20240101 → 2024-01-01
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

            return df
        except Exception as e:
            logger.warning(f"[tushare] {symbol} 拉取失败: {e}")
            return pd.DataFrame()

    def fetch_batch(
        self,
        tasks: list[tuple[str, str, str, str]],
    ) -> list[list]:
        """批量拉取（tushare 免费用户有频次限制，单进程保守拉取）。"""
        results = []
        for symbol, ts_code, start, end in tasks:
            df = self.fetch_history(symbol, start, end)
            if not df.empty:
                for _, row in df.iterrows():
                    results.append([
                        symbol,
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        row["turnover"],
                    ])
            time.sleep(0.2)  # 频次控制
        return results

    # ── 股票名称 ──

    def get_stock_name(self, symbol: str) -> str:
        if not self._api:
            if not self.connect():
                return symbol

        ts_code = self.to_internal_code(symbol)
        try:
            df = self._api.stock_basic(
                ts_code=ts_code,
                fields="name",
            )
            if not df.empty:
                return df.iloc[0]["name"]
        except Exception:
            pass
        return symbol

    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        if not self._api:
            if not self.connect():
                return {}

        try:
            df = self._api.stock_basic(
                exchange="",
                list_status="L",
                fields="symbol,name",
            )
            if not df.empty:
                df = df[df["symbol"].isin(symbols)]
                return dict(zip(df["symbol"], df["name"]))
        except Exception:
            pass
        return {}
