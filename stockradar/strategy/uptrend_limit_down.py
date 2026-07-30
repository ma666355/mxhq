"""上升趋势跌停策略：趋势中放量跌停，捕捉错杀机会。"""

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.strategy.base import BaseStrategy
from stockradar.strategy.price_limit import (
    calculate_limit_price,
    infer_price_limit_ratio,
)

logger = get_logger(__name__)


class UptrendLimitDownStrategy(BaseStrategy):
    """上升趋势跌停策略。

    选股条件（向量化，严禁 iterrows）：
    1. 处于上升趋势：昨日20日均线 > 昨日60日均线
    2. 放量跌停：按 ST、主板、创业板、科创板、北交所分别计算跌停价
                且今日 volume > 20日均量的 2.0 倍

    Attributes:
        webhook_key: 路由到 'limit_down' 专属飞书机器人。
    """

    webhook_key: str = "limit_down"
    config_key: str = "uptrend_limit_down"

    def run(self) -> list[str]:
        """
        遍历全市场，返回满足上升趋势跌停条件的股票代码列表。

        Returns:
            满足条件的股票代码列表。
        """
        symbols = self.engine.get_local_symbols()
        names = self.engine.get_stock_names(symbols)
        selected: list[str] = []
        ma_short = self.param_int("ma_short", 20)
        ma_long = self.param_int("ma_long", 60)
        volume_window = self.param_int("volume_window", 20)
        volume_ratio = self.param_float("volume_ratio", 2.0)
        min_bars = max(ma_long + 1, volume_window)

        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < min_bars:
                    continue

                # 向量化计算均线
                df["ma_short"] = df["close"].rolling(ma_short).mean()
                df["ma_long"] = df["close"].rolling(ma_long).mean()
                df["vol_ma"] = df["volume"].rolling(volume_window).mean()

                prev = df.iloc[-2]  # 昨日
                today = df.iloc[-1]  # 今日

                if (
                    pd.isna(prev["ma_short"])
                    or pd.isna(prev["ma_long"])
                    or pd.isna(today["vol_ma"])
                ):
                    continue

                # 条件 1：上升趋势（昨日均线多头排列）
                uptrend = prev["ma_short"] > prev["ma_long"]
                # 条件 2：放量跌停
                limit_ratio = infer_price_limit_ratio(
                    symbol, names.get(symbol, "")
                )
                down_limit = calculate_limit_price(
                    float(prev["close"]), limit_ratio, "down"
                )
                limit_down = today["close"] <= down_limit + 0.001
                volume_surge = today["volume"] > today["vol_ma"] * volume_ratio

                if uptrend and limit_down and volume_surge:
                    selected.append(symbol)

            except Exception as exc:
                logger.warning(f"[{symbol}] UptrendLimitDownStrategy 计算失败：{exc}")
                continue

        logger.info(f"UptrendLimitDownStrategy 选出 {len(selected)} 只股票")
        return selected
