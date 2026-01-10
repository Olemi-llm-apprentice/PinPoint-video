"""ロギング設定とLangSmithトレーシング統合"""

import logging
import os
import sys
from functools import wraps
from typing import Any, Callable, TypeVar

# LangSmithのインポート
try:
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree

    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    traceable = None  # type: ignore

# 型変数
F = TypeVar("F", bound=Callable[..., Any])

# ロガーのキャッシュ
_loggers: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    """
    名前付きロガーを取得
    
    Args:
        name: ロガー名（通常は __name__ を使用）
    
    Returns:
        設定済みのロガー
    """
    if name in _loggers:
        return _loggers[name]
    
    logger = logging.getLogger(name)
    _loggers[name] = logger
    return logger


def setup_logging(
    level: int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """
    アプリケーション全体のロギングを設定
    
    Args:
        level: ログレベル
        format_string: ログフォーマット文字列
    """
    if format_string is None:
        format_string = (
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
    
    # ルートロガーを設定
    logging.basicConfig(
        level=level,
        format=format_string,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # 外部ライブラリのログレベルを調整
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def is_langsmith_enabled() -> bool:
    """LangSmithが有効かどうかを確認"""
    if not LANGSMITH_AVAILABLE:
        return False
    
    # 環境変数でトレーシングが有効か確認
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
    api_key_set = bool(os.getenv("LANGSMITH_API_KEY"))
    
    return tracing_enabled and api_key_set


def trace_llm(
    name: str | None = None,
    run_type: str = "llm",
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    LLM呼び出しをトレースするデコレータ
    
    LangSmithが無効の場合はパススルー
    
    Args:
        name: トレース名（デフォルトは関数名）
        run_type: 実行タイプ ("llm", "chain", "tool", etc.)
        metadata: 追加メタデータ
    
    Example:
        @trace_llm(name="query_conversion")
        def convert_to_search_query(self, user_query: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        if is_langsmith_enabled() and traceable is not None:
            # LangSmithが有効な場合はtraceableでラップ
            traced_func = traceable(
                name=name or func.__name__,
                run_type=run_type,
                metadata=metadata or {},
            )(func)
            return traced_func  # type: ignore
        else:
            # LangSmithが無効な場合はそのまま返す
            return func
    
    return decorator


def trace_chain(
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    チェーン/ユースケース全体をトレースするデコレータ
    """
    return trace_llm(name=name, run_type="chain", metadata=metadata)


def trace_tool(
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    ツール呼び出しをトレースするデコレータ
    """
    return trace_llm(name=name, run_type="tool", metadata=metadata)


class LogContext:
    """
    ログのコンテキスト情報を保持するヘルパー
    
    Example:
        ctx = LogContext(video_id="abc123", query="test")
        logger.info(f"Processing {ctx}")
    """
    
    def __init__(self, **kwargs: Any):
        self._data = kwargs
    
    def __str__(self) -> str:
        parts = [f"{k}={v!r}" for k, v in self._data.items()]
        return " | ".join(parts)
    
    def update(self, **kwargs: Any) -> "LogContext":
        """新しいコンテキストを追加した新しいインスタンスを返す"""
        new_data = {**self._data, **kwargs}
        return LogContext(**new_data)
    
    def to_dict(self) -> dict[str, Any]:
        """辞書形式で返す"""
        return self._data.copy()
