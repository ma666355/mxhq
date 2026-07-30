"""配置管理属性测试。"""

import os
from pathlib import Path

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st


# Property 1: 环境变量覆盖配置默认值
@given(
    db_path=st.text(
        min_size=1, max_size=100,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="/_.-",
        ),
    )
)
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_env_overrides_default(db_path: str, monkeypatch) -> None:
    """属性 1：任意合法 db_path 通过环境变量设置后，Settings 实例应反映该值。"""
    import stockradar.core.config as cfg_module

    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setattr(cfg_module, "_settings", None)
    from stockradar.core.config import Settings

    s = Settings()
    assert s.db_path == db_path


# Property 2: feishu_webhook_url 默认值为空字符串（不再必填）
def test_feishu_webhook_url_defaults_to_empty() -> None:
    """属性 2：feishu_webhook_url 默认为 ''，允许不配置飞书推送。"""
    import os
    from stockradar.core.config import Settings

    env_backup = os.environ.pop("FEISHU_WEBHOOK_URL", None)
    try:
        s = Settings()
        assert s.feishu_webhook_url == ""
    finally:
        if env_backup is not None:
            os.environ["FEISHU_WEBHOOK_URL"] = env_backup


def test_strategy_parameters_are_loaded_from_pyproject(tmp_path: Path) -> None:
    """策略参数应从 pyproject.toml 的对应区段加载。"""
    config_path = tmp_path / "pyproject.toml"
    config_path.write_text(
        """
[tool.stockradar.strategy.rps_breakout]
rps_period = 60
rps_threshold = 88
""".strip(),
        encoding="utf-8",
    )

    from stockradar.core.config import Settings

    settings = Settings(strategy_config_path=str(config_path))
    assert settings.get_strategy_value("rps_breakout", "rps_period", 120) == 60
    assert settings.get_strategy_value("rps_breakout", "rps_threshold", 90) == 88
