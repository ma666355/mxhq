"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── 数据源配置 ──
    data_source: str = "baostock"
    """数据源名称，支持: baostock / tushare / akshare / wind（默认 baostock）"""

    # ── 数据源专用配置 ──
    tushare_token: str = ""
    """Tushare API token（仅 data_source=tushare 时需要）"""

    # ── 数据库配置 ──
    db_path: str = "data/stockradar.db"
    start_date: str = "2024-01-01"

    # ── 通知配置 ──
    feishu_webhook_url: str = ""
    """默认飞书 Webhook URL（data_source=tushare/akshare 时可不填）"""

    strategy_webhooks: dict[str, str] = Field(default_factory=dict)
    strategy_config: dict[str, dict[str, int | float]] = Field(default_factory=dict)
    strategy_config_path: str = "pyproject.toml"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context: object) -> None:
        """初始化后合并 STRATEGY_WEBHOOK_ 前缀的环境变量到 strategy_webhooks。"""
        import os

        prefix = "STRATEGY_WEBHOOK_"
        webhooks: dict[str, str] = dict(self.strategy_webhooks)
        for key, value in os.environ.items():
            if key.upper().startswith(prefix):
                strategy_key = key[len(prefix):].lower()
                webhooks[strategy_key] = value

        object.__setattr__(self, "strategy_webhooks", webhooks)

        config_path = Path(self.strategy_config_path)
        file_config: dict[str, dict[str, int | float]] = {}
        if config_path.is_file():
            try:
                import tomllib
            except ImportError:  # pragma: no cover - Python 3.10
                import tomli as tomllib

            document = tomllib.loads(config_path.read_text(encoding="utf-8"))
            raw_config = (
                document.get("tool", {})
                .get("stockradar", {})
                .get("strategy", {})
            )
            if isinstance(raw_config, dict):
                for strategy_name, values in raw_config.items():
                    if not isinstance(values, dict):
                        continue
                    file_config[str(strategy_name)] = {
                        str(key): value
                        for key, value in values.items()
                        if isinstance(value, (int, float))
                    }

        merged_config = {
            name: dict(values)
            for name, values in file_config.items()
        }
        for strategy_name, values in self.strategy_config.items():
            merged_config.setdefault(strategy_name, {}).update(values)
        object.__setattr__(self, "strategy_config", merged_config)

    def get_webhook_url(self, webhook_key: str) -> str:
        """根据 webhook_key 返回对应的 Webhook URL。

        优先从 strategy_webhooks 查找，找不到则 fallback 到 feishu_webhook_url。

        Args:
            webhook_key: 策略标识，如 'ma_volume'、'turtle'。

        Returns:
            对应的 Webhook URL 字符串。
        """
        return self.strategy_webhooks.get(
            webhook_key.lower(), self.feishu_webhook_url
        )

    def get_strategy_value(
        self,
        strategy_name: str,
        key: str,
        default: int | float,
    ) -> int | float:
        """读取策略参数；未配置时返回代码提供的默认值。"""
        return self.strategy_config.get(strategy_name, {}).get(key, default)


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局 Settings 单例。

    首次调用时从环境变量或 .env 文件加载配置。
    若 feishu_webhook_url 为空，不会报错（允许纯本地使用）。

    Returns:
        Settings: 全局唯一的配置实例。
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
