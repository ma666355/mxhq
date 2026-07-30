"""A 股不同板块的涨跌停价格计算。"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal


def infer_price_limit_ratio(symbol: str, stock_name: str = "") -> Decimal:
    """根据证券代码和名称推断通常适用的涨跌幅比例。"""
    normalized_name = stock_name.upper().replace(" ", "")
    if symbol.startswith(("300", "301", "688", "689")):
        return Decimal("0.20")
    if symbol.startswith(("4", "8", "92")):
        return Decimal("0.30")
    if "ST" in normalized_name:
        return Decimal("0.05")
    return Decimal("0.10")


def calculate_limit_price(
    previous_close: float,
    ratio: Decimal,
    direction: Literal["up", "down"],
) -> float:
    """按交易价格最小单位 0.01 元计算涨停价或跌停价。"""
    close = Decimal(str(previous_close))
    if direction == "up":
        factor = Decimal("1") + ratio
    elif direction == "down":
        factor = Decimal("1") - ratio
    else:
        raise ValueError(f"未知涨跌停方向: {direction}")
    return float((close * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
