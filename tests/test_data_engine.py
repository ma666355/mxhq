"""数据引擎属性测试。"""

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from stockradar.core.config import Settings
from stockradar.data.engine import DataEngine
from stockradar.data.sources import BaostockDataSource
from stockradar.data.sources.base import BaseDataSource


def make_engine_in(tmp_dir: str) -> tuple[DataEngine, Settings]:
    """创建使用临时数据库和 Baostock 数据源的 DataEngine 实例。"""
    settings = Settings(
        db_path=str(Path(tmp_dir) / "test.db"),
        start_date="2024-01-01",
        feishu_webhook_url="",
    )
    source = BaostockDataSource()
    engine = DataEngine(settings, source)
    return engine, settings


# Property 4: (symbol, date) 唯一约束防止重复写入
@given(
    symbol=st.text(min_size=6, max_size=6, alphabet="0123456789"),
    trade_date=st.dates(min_value=date(2024, 1, 1), max_value=date(2025, 12, 31)),
)
@h_settings(max_examples=50, deadline=None)
def test_unique_symbol_date_constraint(symbol: str, trade_date: date) -> None:
    """相同 (symbol, date) 插入两次，数据库中该组合记录数应保持为 1。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        engine, _ = make_engine_in(tmp_dir)
        row = {
            "symbol": symbol, "date": str(trade_date),
            "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
            "volume": 1000.0, "turnover": 10500.0,
        }
        df = pd.DataFrame([row])
        with sqlite3.connect(engine.db_path) as conn:
            df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi")
            try:
                df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi")
            except sqlite3.IntegrityError:
                pass
            count = conn.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE symbol=? AND date=?",
                (symbol, str(trade_date)),
            ).fetchone()[0]
        assert count == 1


def test_incremental_sync_preserves_other_symbols_on_same_date(
    tmp_path: Path,
) -> None:
    """局部增量更新不得删除同一交易日其他股票的数据。"""
    settings = Settings(
        db_path=str(tmp_path / "test.db"),
        start_date="2024-01-01",
        feishu_webhook_url="",
    )
    source = MagicMock(spec=BaseDataSource)
    source.name = "fake"
    source.to_internal_code.side_effect = lambda symbol: symbol

    engine = DataEngine(settings, source)
    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    seed = pd.DataFrame([
        {
            "symbol": "000001", "date": today,
            "open": 10, "high": 11, "low": 9, "close": 10.5,
            "volume": 1_000, "turnover": 10_500,
        },
        {
            "symbol": "000002", "date": yesterday,
            "open": 20, "high": 21, "low": 19, "close": 20.5,
            "volume": 2_000, "turnover": 41_000,
        },
    ])
    engine._upsert_dataframe(seed)
    source.fetch_batch.return_value = [
        ["000002", today, 21, 22, 20, 21.5, 2_100, 45_150],
    ]

    assert engine.sync_today_bulk() == 1

    with sqlite3.connect(engine.db_path) as conn:
        rows = conn.execute(
            "SELECT symbol, date FROM stock_daily ORDER BY symbol, date"
        ).fetchall()
    assert rows == [
        ("000001", today),
        ("000002", yesterday),
        ("000002", today),
    ]
