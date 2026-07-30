"""不同 A 股板块涨跌停价格测试。"""

from decimal import Decimal

import pytest

from stockradar.strategy.price_limit import (
    calculate_limit_price,
    infer_price_limit_ratio,
)


@pytest.mark.parametrize(
    ("symbol", "name", "expected"),
    [
        ("600000", "浦发银行", Decimal("0.10")),
        ("300001", "特锐德", Decimal("0.20")),
        ("688001", "华兴源创", Decimal("0.20")),
        ("830799", "艾融软件", Decimal("0.30")),
        ("600001", "*ST示例", Decimal("0.05")),
        ("300001", "*ST创业板", Decimal("0.20")),
    ],
)
def test_infer_price_limit_ratio(
    symbol: str,
    name: str,
    expected: Decimal,
) -> None:
    assert infer_price_limit_ratio(symbol, name) == expected


def test_calculate_limit_price_uses_cent_rounding() -> None:
    assert calculate_limit_price(10.03, Decimal("0.10"), "up") == 11.03
    assert calculate_limit_price(10.03, Decimal("0.10"), "down") == 9.03
