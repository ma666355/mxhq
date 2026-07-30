"""高旗形整理策略：强动量后极度收敛缩量。"""

from stockradar.core.logger import get_logger
from stockradar.strategy.base import BaseStrategy

logger = get_logger(__name__)


class HighTightFlagStrategy(BaseStrategy):
    """高旗形整理策略。

    选股条件（向量化，严禁 iterrows）：
    1. 强动量：过去40天区间最高价 / 区间最低价 > 1.6（涨幅超60%）
    2. 极度收敛：最近10天区间最高价 / 区间最低价 < 1.15（振幅低于15%）
    3. 缩量：今日 volume < 过去20日 volume 均值的 0.6 倍

    Attributes:
        webhook_key: 路由到 'flag' 专属飞书机器人。
    """

    webhook_key: str = "flag"
    config_key: str = "high_tight_flag"

    def run(self) -> list[str]:
        """
        遍历全市场，返回满足高旗形整理条件的股票代码列表。

        Returns:
            满足条件的股票代码列表。
        """
        symbols = self.engine.get_local_symbols()
        selected: list[str] = []
        momentum_days = self.param_int("momentum_days", 40)
        momentum_ratio = self.param_float("momentum_ratio", 0.6)
        flag_days = self.param_int("flag_days", 10)
        tight_ratio = self.param_float("tight_ratio", 0.15)
        high_level_ratio = self.param_float("high_level_ratio", 0.8)
        volume_window = self.param_int("volume_window", 20)
        volume_ratio = self.param_float("volume_ratio", 0.6)
        min_bars = max(momentum_days, flag_days, volume_window + 1)

        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < min_bars:
                    continue

                # 向量化计算各窗口指标
                momentum_window = df.tail(momentum_days)
                flag_window = df.tail(flag_days)

                momentum_high = momentum_window["high"].max()
                momentum_low = momentum_window["low"].min()
                flag_high = flag_window["high"].max()
                flag_low = flag_window["low"].min()

                if momentum_low == 0 or flag_low == 0:
                    continue

                # 条件 1：强动量
                momentum = momentum_high / momentum_low - 1 > momentum_ratio
                # 条件 2：极度收敛
                consolidation = flag_high / flag_low - 1 < tight_ratio
                # 条件 3：高位抗跌
                high_level = flag_low >= momentum_high * high_level_ratio
                # 条件 4：缩量（向量化均值）
                historical_volume = df["volume"].iloc[-volume_window - 1:-1].mean()
                shrink = df["volume"].iloc[-1] < historical_volume * volume_ratio

                if momentum and consolidation and high_level and shrink:
                    selected.append(symbol)

            except Exception as exc:
                logger.warning(f"[{symbol}] HighTightFlagStrategy 计算失败：{exc}")
                continue

        logger.info(f"HighTightFlagStrategy 选出 {len(selected)} 只股票")
        return selected
