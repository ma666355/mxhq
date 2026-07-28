"""数据引擎模块：负责 SQLite 行情数据存储与增量同步。

支持多数据源（baostock / tushare / akshare / wind），通过 Settings.data_source 切换。
"""

import sqlite3
import time
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from stockradar.core.config import Settings
from stockradar.core.logger import get_logger
from stockradar.data.sources.base import BaseDataSource

logger = get_logger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_daily (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   REAL,
    turnover REAL,
    UNIQUE (symbol, date)
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_daily (symbol, date);
"""


class DataEngine:
    """行情数据引擎，负责 SQLite 存储和多数据源数据同步。

    使用方式：
        from stockradar.data.sources import get_data_source
        source = get_data_source('akshare')
        engine = DataEngine(settings, source)
    """

    def __init__(self, settings: Settings, data_source: BaseDataSource) -> None:
        self.db_path: str = settings.db_path
        self.start_date: str = settings.start_date
        self.source: BaseDataSource = data_source
        self._init_db()

    # ── 数据库初始化 ──

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
        logger.info(f"数据库初始化完成：{self.db_path}（数据源: {self.source.name}）")

    # ── 数据读取 ──

    def _get_last_date(self, symbol: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM stock_daily WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return row[0] if row and row[0] else None

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql(
                "SELECT * FROM stock_daily WHERE symbol = ? ORDER BY date",
                conn,
                params=(symbol,),
            )
        return df

    # ── 数据同步 ──

    def sync_today_bulk(self) -> int:
        """多进程并行拉取增量数据，写入 SQLite。

        对于支持并行连接的数据源（baostock），使用多进程加速；
        对于需要登录态的数据源（tushare / akshare），降级为单进程串行。
        """
        today_str = date.today().strftime("%Y-%m-%d")

        tasks = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol"
            ).fetchall()

        if not rows:
            logger.warning("本地无股票数据，请先执行 --backfill")
            return 0

        for symbol, last_date in rows:
            if last_date and last_date >= today_str:
                continue
            start = today_str
            if last_date:
                start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime(
                    "%Y-%m-%d"
                )
            internal_code = self.source.to_internal_code(symbol)
            tasks.append((symbol, internal_code, start, today_str))

        if not tasks:
            logger.info("所有股票已是最新，无需更新")
            return 0

        logger.info(
            f"需要更新 {len(tasks)} 只股票"
            f"（数据源: {self.source.name}）..."
        )

        # 多进程仅对 baostock 有效（baostock 支持独立 login）
        # 其他数据源降级为串行
        if self.source.name == "baostock":
            all_rows = self._parallel_fetch(tasks)
        else:
            all_rows = self._serial_fetch(tasks)

        if not all_rows:
            logger.info("无新数据（可能非交易日）")
            return 0

        df = pd.DataFrame(
            all_rows,
            columns=[
                "symbol", "date", "open", "high", "low",
                "close", "volume", "turnover",
            ],
        )
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df[df["volume"] > 0]

        count = len(df)
        with sqlite3.connect(self.db_path) as conn:
            for d in df["date"].unique().tolist():
                conn.execute("DELETE FROM stock_daily WHERE date = ?", (d,))
            df.to_sql(
                "stock_daily", conn, if_exists="append",
                index=False, method="multi", chunksize=500,
            )
            conn.commit()

        logger.info(f"sync_today_bulk: 写入 {count} 条数据")
        return count

    def _parallel_fetch(self, tasks: list) -> list:
        """8 进程并行拉取（仅 baostock 数据源）。"""
        n_workers = min(8, len(tasks))
        chunks = [tasks[i::n_workers] for i in range(n_workers)]

        with Pool(n_workers) as pool:
            batch_results = pool.map(self.source.fetch_batch, chunks)

        all_rows = []
        for batch in batch_results:
            all_rows.extend(batch)
        return all_rows

    def _serial_fetch(self, tasks: list) -> list:
        """串行拉取（tushare / akshare / wind 等受频次限制的数据源）。"""
        return self.source.fetch_batch(tasks)

    # ── 历史回填 ──

    def backfill(self, symbols: list[str]) -> None:
        """批量回填历史日 K 线数据。

        容错机制：
        - 单只股票失败自动重试 3 次，间隔递增（2s/4s/8s）
        - 已入库的自动 skip，中断后可重跑续传
        - 非 baostock 数据源串行拉取，自动控制频次
        """
        today_str = date.today().strftime("%Y-%m-%d")
        max_retries = 3

        # 连接数据源（baostock 特殊处理：需在循环外 maintain 一个长连接）
        is_baostock = self.source.name == "baostock"
        if is_baostock:
            self.source.connect()

        success = 0
        skipped = 0
        failed = 0

        try:
            for i, symbol in enumerate(symbols):
                last_date = self._get_last_date(symbol)
                if last_date and last_date >= today_str:
                    skipped += 1
                    if (i + 1) % 500 == 0:
                        logger.info(
                            f"已处理 {i + 1}/{len(symbols)}，"
                            f"成功 {success} 跳过 {skipped} 失败 {failed}"
                        )
                    continue

                start = last_date or self.start_date
                if last_date:
                    start = (
                        date.fromisoformat(last_date) + timedelta(days=1)
                    ).strftime("%Y-%m-%d")

                # 带重试的拉取
                df = pd.DataFrame()
                fetch_ok = False
                for attempt in range(max_retries):
                    try:
                        df = self.source.fetch_history(symbol, start, today_str)
                        fetch_ok = True
                        break
                    except Exception as exc:
                        if attempt < max_retries - 1:
                            wait = 2 ** (attempt + 1)
                            logger.warning(
                                f"[{symbol}] 第{attempt + 1}次失败: {exc}，"
                                f"{wait}s 后重试"
                            )
                            time.sleep(wait)
                            if is_baostock:
                                self.source.disconnect()
                                time.sleep(1)
                                self.source.connect()
                        else:
                            logger.warning(
                                f"[{symbol}] {max_retries}次重试均失败，跳过"
                            )

                if not fetch_ok:
                    failed += 1
                    continue

                if df.empty:
                    skipped += 1
                    continue

                # 写入数据库
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        df.to_sql(
                            "stock_daily", conn, if_exists="append",
                            index=False, method="multi", chunksize=500,
                        )
                except sqlite3.IntegrityError:
                    pass

                success += 1

                if (i + 1) % 500 == 0:
                    logger.info(
                        f"已处理 {i + 1}/{len(symbols)}，"
                        f"成功 {success} 跳过 {skipped} 失败 {failed}"
                    )

                # 非 baostock 数据源：控制拉取频次
                if not is_baostock and self.source.name in ("tushare", "akshare"):
                    time.sleep(0.1)

        finally:
            if is_baostock:
                self.source.disconnect()

        logger.info(
            f"回填完成 — 成功: {success} | 跳过: {skipped} | 失败: {failed}"
        )

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        """通过数据源获取全市场 A 股代码列表。"""
        return self.source.get_all_symbols()

    def get_local_symbols(self) -> list[str]:
        """从本地 SQLite 获取已有数据的股票代码列表。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM stock_daily"
            ).fetchall()
        return [row[0] for row in rows]
