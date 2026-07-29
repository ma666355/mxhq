"""StockRadar V2 主程序入口。

支持多数据源（baostock / tushare / akshare / wind），通过 .env 中 DATA_SOURCE 切换。

两种运行模式：
  python main.py               # 日常模式：增量补数据 + 跑策略 + 飞书推送（2~3分钟）
  python main.py --backfill    # 回填模式：拉全市场历史K线（首次/补数据用）
"""

import argparse
import sys
import socket

from dotenv import load_dotenv

load_dotenv()

socket.setdefaulttimeout(10.0)

from stockradar.core.config import get_settings
from stockradar.core.logger import get_logger
from stockradar.data.engine import DataEngine
from stockradar.data.sources import get_data_source
from stockradar.notify.feishu import FeishuNotifier
from stockradar.strategy import discover_strategies


def main() -> None:
    parser = argparse.ArgumentParser(description="StockRadar V2 选股系统")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="回填模式：拉取全市场历史 K 线",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="数据源覆盖（baostock / tushare / akshare / wind），"
             "不指定则使用 .env 中的 DATA_SOURCE",
    )
    args = parser.parse_args()

    try:
        # 1. 初始化配置
        settings = get_settings()

        # 2. 初始化日志
        logger = get_logger(__name__)
        logger.info("StockRadar V2 启动")

        # 3. 初始化数据源
        source_name = args.source or settings.data_source
        source_kwargs: dict = {}
        if source_name == "tushare":
            source_kwargs["token"] = settings.tushare_token
        data_source = get_data_source(source_name, **source_kwargs)
        logger.info(f"数据源: {source_name}")

        # 4. 初始化数据引擎
        engine = DataEngine(settings, data_source)

        if args.backfill:
            # ── 回填模式 ──
            logger.info("进入回填模式...")
            all_symbols = engine.get_all_symbols()
            engine.backfill(all_symbols)
            logger.info("StockRadar V2 回填模式运行完成")
            return

        # ── 日常模式 ──
        logger.info("开始拉取最新快照...")
        count = engine.sync_today_bulk()
        logger.info(f"快照同步完成，写入 {count} 只股票")

        # 5. 自动发现策略（新增策略无需改 main.py，丢文件即可）
        strategy_classes = discover_strategies()
        logger.info(f"发现 {len(strategy_classes)} 个策略")
        strategies = [
            cls(engine=engine, settings=settings)
            for cls in strategy_classes
        ]

        notifier = FeishuNotifier(settings, data_source)

        # 6. 遍历策略，有结果则推送至对应机器人
        for strategy in strategies:
            strategy_name = type(strategy).__name__
            logger.info(f"执行策略：{strategy_name}")

            selected: list[str] = strategy.run()
            logger.info(f"{strategy_name} 选出 {len(selected)} 只股票")

            if selected:
                notifier.send(
                    symbols=selected,
                    strategy_name=strategy_name,
                    webhook_key=strategy.webhook_key,
                )
            else:
                logger.info(f"{strategy_name} 无选股结果，跳过推送")

    except Exception:
        try:
            _logger = get_logger(__name__)
            _logger.exception("主流程发生未捕获异常，程序终止")
        except Exception:
            import traceback

            traceback.print_exc()
        sys.exit(1)

    logger.info("StockRadar V2 运行完成")


if __name__ == "__main__":
    main()
