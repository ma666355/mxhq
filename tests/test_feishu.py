"""飞书通知属性测试。"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from stockradar.core.config import Settings
from stockradar.data.sources import BaostockDataSource
from stockradar.notify.feishu import FeishuNotifier


def make_settings_and_source(
    webhook_url: str = "https://example.com/default",
) -> tuple[Settings, BaostockDataSource]:
    source = BaostockDataSource()
    settings = Settings(
        db_path="data/test.db",
        start_date="2024-01-01",
        feishu_webhook_url=webhook_url,
    )
    return settings, source


# Property 10: 飞书通知包含所有选股结果
@given(
    symbols=st.lists(
        st.text(min_size=6, max_size=6, alphabet="0123456789"),
        min_size=1, max_size=10, unique=True,
    )
)
@h_settings(max_examples=50)
def test_notification_contains_all_symbols(symbols: list[str]) -> None:
    """属性 10：send() 发出的请求体应包含所有 symbol。"""
    settings, source = make_settings_and_source()
    notifier = FeishuNotifier(settings, source)

    # Mock 股票名称查询，避免实际网络请求
    with patch.object(source, "get_stock_names", return_value={}):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.json.return_value = {"code": 0}
            notifier.send(symbols=symbols, strategy_name="TestStrategy")

        call_args = mock_post.call_args
        body = json.loads(
            call_args.kwargs.get("data")
            or call_args.args[1] if len(call_args.args) > 1
            else call_args.kwargs["data"]
        )
        card_text = json.dumps(body)
        for symbol in symbols:
            assert symbol in card_text


# Property 11: 飞书通知使用 ConfigManager 中的 Webhook URL
@given(
    webhook_url=st.from_regex(
        r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[a-z0-9\-]{8,36}",
        fullmatch=True,
    )
)
@h_settings(max_examples=50)
def test_notification_uses_config_url(webhook_url: str) -> None:
    """属性 11：send() 发出的 HTTP 请求目标 URL 应等于 settings 中配置的 URL。"""
    settings, source = make_settings_and_source(webhook_url=webhook_url)
    notifier = FeishuNotifier(settings, source)

    with patch.object(source, "get_stock_names", return_value={}):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.json.return_value = {"code": 0}
            notifier.send(
                symbols=["000001"], strategy_name="Test", webhook_key="default"
            )

    called_url = (
        mock_post.call_args.args[0]
        if mock_post.call_args.args
        else mock_post.call_args.kwargs.get("url")
    )
    assert called_url == webhook_url


# Property 12: HTTP 失败时记录 ERROR 日志
@given(status_code=st.integers(min_value=400, max_value=599))
@h_settings(max_examples=50)
def test_http_failure_logs_error(status_code: int) -> None:
    """属性 12：非 200 响应时，send() 应记录 ERROR 级别日志，不抛出异常。"""
    import logging as _logging
    import stockradar.notify.feishu as feishu_module

    settings, source = make_settings_and_source()
    notifier = FeishuNotifier(settings, source)

    feishu_logger = _logging.getLogger(feishu_module.__name__)
    log_records: list[_logging.LogRecord] = []

    class _ListHandler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            log_records.append(record)

    handler = _ListHandler(_logging.ERROR)
    feishu_logger.addHandler(handler)
    try:
        with patch.object(source, "get_stock_names", return_value={}):
            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(
                    status_code=status_code, text="error"
                )
                mock_post.return_value.json.return_value = {"code": -1}
                notifier.send(symbols=["000001"], strategy_name="Test")
    finally:
        feishu_logger.removeHandler(handler)

    assert any(r.levelno == _logging.ERROR for r in log_records)
