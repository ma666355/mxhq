"""Wind 数据源实现（需要本地安装 Wind 金融终端）。

Wind 是商业金融数据终端，提供全面的 A 股、港股、期货、宏观等数据。
使用前需安装 Wind 终端并启动 WindPy 服务。

注意事项：
- WindPy 仅支持 Windows，部分支持 Linux
- 需要有效的 Wind 账号和 license
- 首次使用需在 Wind 终端中执行 `windpy` 命令启动 Python 接口
"""

from __future__ import annotations

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.data.sources.base import BaseDataSource

logger = get_logger(__name__)


class WindDataSource(BaseDataSource):
    """Wind 金融终端数据源。

    使用前准备：
    1. 安装并登录 Wind 金融终端
    2. 在 Wind 终端命令行输入 `windpy` 启动 Python 接口
    3. pip install WindPy（Wind 自带的 Python 包）

    Wind 代码格式：
    - A股：000001.SZ, 600519.SH
    - 指数：000300.SH（沪深300）
    - 板块：根据 Wind 行业分类

    Attributes:
        name: 数据源标识，固定为 'wind'
    """

    name: str = "wind"

    def __init__(self) -> None:
        self._w = None

    # ── 连接管理 ──

    def connect(self) -> bool:
        try:
            from WindPy import w
            w.start()
            if not w.isconnected():
                logger.error(
                    "[wind] 连接失败，请确保 Wind 终端已启动且登录了账号"
                )
                return False
            self._w = w
            logger.info("[wind] 连接成功")
            return True
        except ImportError:
            logger.error(
                "[wind] 请先安装 WindPy（Wind 终端自带），"
                "或在 Wind 终端命令行执行 `windpy` 启动 Python 接口"
            )
            return False
        except Exception as e:
            logger.error(f"[wind] 连接异常: {e}")
            return False

    def disconnect(self) -> None:
        if self._w:
            try:
                self._w.stop()
            except Exception:
                pass
            self._w = None

    # ── 符号转换 ──

    @staticmethod
    def to_internal_code(symbol: str) -> str:
        """纯数字代码 → Wind 格式：000001.SZ / 600519.SH / 8/4开头.BJ。"""
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        elif symbol.startswith(("4", "8")):
            return f"{symbol}.BJ"
        return f"{symbol}.SZ"

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        if not self._w:
            if not self.connect():
                return []

        try:
            # 获取全部 A 股列表
            # sectorid=a001010100000000 = 全部 A 股
            codes, fields = self._w.wset(
                "sectorconstituent",
                f"date={pd.Timestamp.now().strftime('%Y-%m-%d')};"
                "sectorid=a001010100000000;field=wind_code",
            )
            if codes.ErrorCode != 0:
                logger.error(f"[wind] 获取股票列表失败: {codes.Data}")
                return []

            symbols = [c.split(".")[0] for c in codes.Data[0]]
            logger.info(f"[wind] 获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"[wind] 获取股票列表失败: {e}")
            return []

    # ── 历史数据 ──

    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "1",
    ) -> pd.DataFrame:
        if not self._w:
            if not self.connect():
                return pd.DataFrame()

        wind_code = self.to_internal_code(symbol)

        # 复权方式：1=后复权，2=前复权，3=不复权
        price_adj_map = {"1": "1", "2": "2", "3": ""}
        price_adj = price_adj_map.get(adjustflag, "1")

        try:
            # wsd: Wind 序列数据接口
            # fields: open, high, low, close, volume, amt
            error, df_data = self._w.wsd(
                wind_code,
                "open,high,low,close,volume,amt",
                start_date,
                end_date,
                f"PriceAdj={price_adj}",
                usedf=True,
            )

            if error != 0:
                logger.warning(f"[wind] {symbol} 查询失败: error={error}")
                return pd.DataFrame()

            if df_data.empty:
                return pd.DataFrame()

            df_data = df_data.reset_index()
            df_data.columns = ["date", "open", "high", "low", "close", "volume", "turnover"]
            df_data["symbol"] = symbol

            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df_data[col] = pd.to_numeric(df_data[col], errors="coerce")

            df_data = df_data.dropna(subset=["close"])
            df_data = df_data[df_data["volume"] > 0]
            df_data["date"] = pd.to_datetime(df_data["date"]).dt.strftime("%Y-%m-%d")
            df_data = df_data.sort_values("date")
            df_data = df_data[
                ["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]
            ]

            return df_data
        except Exception as e:
            logger.warning(f"[wind] {symbol} 拉取失败: {e}")
            return pd.DataFrame()

    def fetch_batch(
        self,
        tasks: list[tuple[str, str, str, str]],
    ) -> list[list]:
        """批量拉取（Wind 支持多证券同时查询，按证券拆分处理）。"""
        results = []
        for symbol, wind_code, start, end in tasks:
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
        return results

    # ── 股票名称 ──

    def get_stock_name(self, symbol: str) -> str:
        if not self._w:
            if not self.connect():
                return symbol

        wind_code = self.to_internal_code(symbol)
        try:
            error, df = self._w.wsd(
                wind_code, "sec_name",
                pd.Timestamp.now().strftime("%Y-%m-%d"),
                pd.Timestamp.now().strftime("%Y-%m-%d"),
                usedf=True,
            )
            if error == 0 and not df.empty:
                return df.iloc[0, 0]
        except Exception:
            pass
        return symbol

    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        result = {}
        for symbol in symbols:
            result[symbol] = self.get_stock_name(symbol)
        return result
