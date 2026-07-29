"""Baostock 数据源实现（免费、无需注册、无限流）。

官网：http://baostock.com
"""

import os
import sys
from contextlib import contextmanager

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.data.sources.base import BaseDataSource

logger = get_logger(__name__)


@contextmanager
def _quiet_baostock():
    """抑制 baostock 内置 print 输出（login/logout success 刷屏）。"""
    devnull = open(os.devnull, "w")
    old_stdout = sys.stdout
    sys.stdout = devnull
    try:
        yield
    finally:
        sys.stdout = old_stdout
        devnull.close()


class BaostockDataSource(BaseDataSource):
    """Baostock 数据源。

    baostock 是免费、无需注册的 A 股数据接口，适合个人量化使用。
    支持后复权 / 前复权 / 不复权，数据覆盖 1990 年至今。

    Attributes:
        name: 数据源标识，固定为 'baostock'
    """

    name: str = "baostock"

    def __init__(self) -> None:
        self._logged_in = False

    # ── 连接管理 ──

    def connect(self) -> bool:
        import baostock as bs
        with _quiet_baostock():
            lg = bs.login()
        if lg.error_code != "0":
            logger.error(f"baostock 登录失败: {lg.error_msg}")
            return False
        self._logged_in = True
        logger.debug("baostock 连接成功")
        return True

    def disconnect(self) -> None:
        import baostock as bs
        with _quiet_baostock():
            bs.logout()
        self._logged_in = False
        logger.debug("baostock 连接已断开")

    # ── 符号转换 ──

    @staticmethod
    def to_internal_code(symbol: str) -> str:
        """纯数字代码 → baostock 格式：6/9开头→sh，其余→sz。"""
        prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
        return f"{prefix}.{symbol}"

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        import baostock as bs

        was_logged_in = self._logged_in
        if not self._logged_in:
            self.connect()

        try:
            rs = bs.query_stock_basic(code_name="", code="")
            symbols = []
            while rs.next():
                row = rs.get_row_data()
                code = row[0]
                status = row[4]
                stock_type = row[5]
                if status == "1" and stock_type == "1":
                    symbols.append(code.split(".")[1])
            logger.info(f"[baostock] 获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"[baostock] 获取股票列表失败: {e}")
            return []
        finally:
            if not was_logged_in:
                self.disconnect()

    # ── 历史数据 ──

    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "1",
    ) -> pd.DataFrame:
        import baostock as bs

        was_logged_in = self._logged_in
        if not self._logged_in:
            self.connect()

        bs_code = self.to_internal_code(symbol)

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjustflag,  # 1=后复权
            )
            if rs.error_code != "0":
                logger.warning(f"[baostock] {symbol} 查询失败: {rs.error_msg}")
                return pd.DataFrame()

            rows = []
            while rs.next():
                rows.append(rs.get_row_data())

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=rs.fields)
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            df = df[df["volume"] > 0]
            df["symbol"] = symbol
            df = df.rename(columns={"amount": "turnover"})
            df = df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]]
            return df
        except Exception as e:
            logger.warning(f"[baostock] {symbol} 拉取失败: {e}")
            return pd.DataFrame()
        finally:
            if not was_logged_in:
                self.disconnect()

    def fetch_batch(
        self,
        tasks: list[tuple[str, str, str, str]],
    ) -> list[list]:
        import baostock as bs
        bs.login()
        results = []
        for symbol, bs_code, start, end in tasks:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=start,
                end_date=end,
                frequency="d",
                adjustflag="1",
            )
            if rs.error_code != "0":
                continue
            while rs.next():
                results.append([symbol] + rs.get_row_data())
        bs.logout()
        return results

    # ── 股票名称 ──

    def get_stock_name(self, symbol: str) -> str:
        import baostock as bs

        was_logged_in = self._logged_in
        if not self._logged_in:
            self.connect()

        bs_code = self.to_internal_code(symbol)
        try:
            rs = bs.query_stock_basic(code=bs_code)
            while rs.next():
                row = rs.get_row_data()
                return row[1]  # 第2个字段是股票名称
        except Exception:
            pass
        finally:
            if not was_logged_in:
                self.disconnect()
        return symbol

    def get_stock_names(self, symbols: list[str]) -> dict[str, str]:
        import baostock as bs

        was_logged_in = self._logged_in
        if not self._logged_in:
            self.connect()

        mapping: dict[str, str] = {}
        try:
            for symbol in symbols:
                bs_code = self.to_internal_code(symbol)
                rs = bs.query_stock_basic(code=bs_code)
                while rs.next():
                    row = rs.get_row_data()
                    mapping[symbol] = row[1]
        except Exception:
            pass
        finally:
            if not was_logged_in:
                self.disconnect()
        return mapping
