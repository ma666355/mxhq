# StockRadar: 王者回归 | The King Returns

> A 股量化选股系统 V2 | A-Share Quantitative Stock Selection System V2

---

## 简介 | Introduction

StockRadar V2 是面向 A 股市场的量化选股系统，基于现代 Python 工程化标准从零重构。
系统以 OOP 架构、向量化计算和增量数据更新为核心设计原则，每日收盘后自动选股并推送至飞书群。

**V2.1 新增：多数据源抽象层**，支持 baostock / tushare / akshare / wind 一键切换，
一行配置即可更换底层数据引擎，不修改任何策略代码。

---

## 支持的数据源 | Data Sources

| 数据源 | 费用 | 注册 | 频次限制 | 并行 | 状态 |
|--------|------|------|----------|------|------|
| **Baostock** | 免费 | 不需要 | 无 | 8 进程 | 默认 |
| **AkShare** | 免费 | 不需要 | 建议限速 | 串行 | 可用 |
| **Tushare** | 免费/积分 | 需要 | 有 | 串行 | 需 Token |
| **Wind** | 商业 | 需要 | 无 | 串行 | 需终端 |

### 切换方式

```bash
# 方式一：修改 .env
DATA_SOURCE=akshare

# 方式二：命令行临时覆盖
python main.py --source tushare
```

---

## 两种运行模式

```bash
python main.py               # 日常模式：增量补数据 + 跑策略 + 飞书推送（2~3分钟）
python main.py --backfill     # 回填模式：全市场历史K线一次性灌入（约12分钟）
python main.py --source akshare  # 指定数据源运行
```

---

## 内置策略 | Strategies

| 策略 | 说明 |
|---|---|
| **TurtleTrade** | 海龟突破：20日新高 + 成交额过亿 + 阳线防诱多，按流通市值排序 |
| **MaVolume** | 均线+放量突破 |
| **HighTightFlag** | 高而窄的旗形整理突破 |
| **LimitUpShakeout** | 涨停洗盘回踩确认 |
| **UptrendLimitDown** | 上升趋势中的跌停反包 |
| **RpsBreakout** | 欧奈尔 RPS 相对强度突破 |
| **PrivatePlacement** | 私募增持跟踪 |

---

## 快速开始 | Quick Start

### 环境要求

- Python >= 3.10

### 1. 安装依赖

```bash
# 推荐使用 uv（快速包管理器）
uv sync

# 或者 pip
pip install .

# 如需 tushare 数据源
pip install ".[tushare]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env：
#   - 选数据源：DATA_SOURCE=baostock（默认）
#   - 飞书推送：FEISHU_WEBHOOK_URL（可选，不填则跳过推送）
#   - Tushare：  TUSHARE_TOKEN（仅 tushare 需要）
```

### 3. 首次回填历史数据

```bash
python main.py --backfill
```

### 4. 日常运行

```bash
python main.py
```

建议配合 crontab 每个交易日收盘后自动执行：

```cron
15 19 * * 1-5 cd /root/mxhq && python main.py >> log.txt 2>&1
```

---

## 目录结构 | Project Structure

```
mxhq/
├── main.py                           # 入口：argparse 分发日常/回填 + --source 覆盖
├── pyproject.toml                    # 依赖声明 + 可选 tushare 依赖
├── .env.example                      # 环境变量模板
├── data/                             # SQLite 数据库（运行时生成，不入 git）
├── stockradar/
│   ├── core/
│   │   ├── config.py                 # Pydantic-settings 配置管理
│   │   └── logger.py                 # rich 结构化日志
│   ├── data/
│   │   ├── engine.py                 # 数据引擎（SQLite + 增量同步）
│   │   └── sources/                  # 数据源抽象层 🆕
│   │       ├── base.py               #   抽象基类（统一接口）
│   │       ├── baostock_source.py    #   Baostock 实现
│   │       ├── tushare_source.py     #   Tushare 实现
│   │       ├── akshare_source.py     #   AkShare 实现
│   │       └── wind_source.py        #   Wind 实现
│   ├── strategy/
│   │   ├── base.py                   # 策略抽象基类
│   │   ├── turtle_trade.py           # 海龟交易策略
│   │   ├── ma_volume.py              # 均线放量策略
│   │   ├── high_tight_flag.py        # 高窄旗形策略
│   │   ├── limit_up_shakeout.py      # 涨停洗盘策略
│   │   ├── uptrend_limit_down.py     # 上升跌停策略
│   │   ├── rps_breakout.py           # RPS 突破策略
│   │   └── private_placement.py      # 私募增持策略
│   └── notify/
│       └── feishu.py                 # 飞书 Webhook 推送
└── tests/                            # 单元测试
```

---

## 扩展：自定义数据源

所有数据源继承 `BaseDataSource`，只需实现 6 个方法：

```python
from stockradar.data.sources.base import BaseDataSource

class MyDataSource(BaseDataSource):
    name = "my_source"

    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def get_all_symbols(self) -> list[str]: ...
    def fetch_history(self, symbol, start, end, adjustflag="1") -> pd.DataFrame: ...
    def fetch_batch(self, tasks) -> list[list]: ...
    def get_stock_names(self, symbols) -> dict[str, str]: ...
```

然后在 `stockradar/data/sources/__init__.py` 的 registry 中注册即可使用。

---

## 数据说明

- **数据格式**：日 K 线（open / high / low / close / volume / turnover）
- **复权方式**：后复权（hfq）— 历史价格不变，适合增量存储
- **存储**：本地 SQLite（`data/stockradar.db`），可直接拷贝到其他机器使用
- **增量机制**：首次 `--backfill` 全量灌入，日常 `main.py` 增量补最新交易日

---

## 许可证 | License

MIT
