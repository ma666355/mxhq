"""海龟交易策略：20日新高突破 + 成交额过亿 + 动量阳线过滤。"""

import pandas as pd

from stockradar.core.logger import get_logger
from stockradar.strategy.base import BaseStrategy

logger = get_logger(__name__)


class TurtleTradeStrategy(BaseStrategy):
    """海龟交易策略（A股防诱多改良版）。

    选股条件（向量化，严禁 iterrows）：
    1. 突破新高：今日 close > 前20个交易日 high 的最大值
    2. 流动性：今日 turnover > 100,000,000
    3. 防诱多：今日为实体阳线，且收盘价高于昨日收盘价

    Attributes:
        webhook_key: 路由到 'turtle' 专属飞书机器人。
    """

    webhook_key: str = "turtle"

    def run(self) -> list[str]:
        """
        遍历全市场，返回满足海龟突破条件的股票代码列表。
        """
        symbols = self.engine.get_local_symbols()
        candidates: list[str] = []
        candidate_turnover: dict[str, float] = {}
        window = self.param_int("window", 20)
        min_turnover = self.param_float("min_turnover", 100_000_000)

        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < window + 1:
                    continue

                # 前 N 日 high 的滚动最大值，不包含当日。
                df["breakout_high"] = df["high"].shift(1).rolling(window).max()

                last = df.iloc[-1]
                prev = df.iloc[-2]  # 获取昨日数据，用于对比

                if pd.isna(last["breakout_high"]):
                    continue

                breakout = last["close"] > last["breakout_high"]
                liquid = last["turnover"] > min_turnover

                is_yang = last["close"] > last["open"]
                is_up = last["close"] > prev["close"]

                if breakout and liquid and is_yang and is_up:
                    candidates.append(symbol)
                    candidate_turnover[symbol] = float(last["turnover"])

            except Exception as exc:
                logger.warning(f"[{symbol}] TurtleTradeStrategy 计算失败：{exc}")
                continue

        # 数据库中没有换手率或流通股本，使用可验证的成交额排序。
        candidates.sort(key=lambda symbol: candidate_turnover[symbol], reverse=True)

        logger.info(f"TurtleTradeStrategy 选出 {len(candidates)} 只股票")
        return candidates
