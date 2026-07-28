"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── 数据源配置 ──
    data_source: str = "baostock"
    """数据源名称，支持: baostock / tushare / akshare / wind（默认 baostock）"""

    # ── 数据源专用配置 ──
    tushare_token: str = ""
    """Tushare API token（仅 data_source=tushare 时需要）"""

    # ── 数据库配置 ──
    db_path: str = "data/sequoia_v2.db"
    start_date: str = "2024-01-01"

    # ── 通知配置 ──
    feishu_webhook_url: str = ""
    """默认飞书 Webhook URL（data_source=tushare/akshare 时可不填）"""

    strategy_webhooks: dict[str, str] = {}

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
