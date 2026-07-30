"""数据源字段语义与单位归一化测试。"""

import sys
from types import SimpleNamespace

import pandas as pd

from stockradar.data.sources.akshare_source import AkShareDataSource
from stockradar.data.sources.tushare_source import TushareDataSource


def test_akshare_uses_hfq_and_normalizes_volume(monkeypatch) -> None:
    calls: list[str] = []

    def stock_zh_a_hist(**kwargs):
        calls.append(kwargs["adjust"])
        return pd.DataFrame([
            {
                "日期": "2024-01-02",
                "开盘": 10,
                "最高": 11,
                "最低": 9,
                "收盘": 10.5,
                "成交量": 100,
                "成交额": 105_000,
            }
        ])

    fake_akshare = SimpleNamespace(stock_zh_a_hist=stock_zh_a_hist)
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)
    source = AkShareDataSource()

    hfq = source.fetch_history("000001", "2024-01-01", "2024-01-02", "1")
    source.fetch_history("000001", "2024-01-01", "2024-01-02", "2")

    assert calls == ["hfq", "qfq"]
    assert hfq.iloc[0]["volume"] == 10_000
    assert hfq.iloc[0]["turnover"] == 105_000
    assert hfq.iloc[0]["date"] == "2024-01-02"


def test_tushare_normalizes_units_without_adjusting_turnover() -> None:
    class FakeApi:
        def daily(self, **_kwargs):
            return pd.DataFrame([
                {
                    "trade_date": "20240102",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "vol": 100,
                    "amount": 1_050,
                }
            ])

        def adj_factor(self, **_kwargs):
            return pd.DataFrame([
                {"trade_date": "20240102", "adj_factor": 2.0}
            ])

    source = TushareDataSource(token="test-token")
    source._api = FakeApi()

    df = source.fetch_history(
        "000001", "2024-01-01", "2024-01-02", adjustflag="1"
    )

    assert df.iloc[0]["close"] == 21
    assert df.iloc[0]["volume"] == 10_000
    assert df.iloc[0]["turnover"] == 1_050_000
