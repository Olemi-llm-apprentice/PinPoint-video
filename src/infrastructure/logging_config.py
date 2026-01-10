"""ロギング設定とLangSmithトレーシング統合"""

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
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
    
    # Settingsから値を取得（.envファイルを読み込む）
    try:
        from config.settings import get_settings
        settings = get_settings()
        return settings.LANGSMITH_TRACING and bool(settings.LANGSMITH_API_KEY)
    except Exception:
        # Settingsが使えない場合は環境変数から直接取得
        tracing_enabled = os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
        api_key_set = bool(os.getenv("LANGSMITH_API_KEY"))
        return tracing_enabled and api_key_set


def generate_trace_metadata() -> dict[str, Any]:
    """
    トレース用のメタデータを生成
    
    各トレースを一意に識別するためのセッションIDとタイムスタンプを含む
    """
    return {
        "session_id": str(uuid.uuid4())[:8],  # 短縮UUID
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "timestamp_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def trace_llm(
    name: str | None = None,
    run_type: str = "llm",
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    LLM呼び出しをトレースするデコレータ
    
    LangSmithが無効の場合はパススルー
    各呼び出しで新しいrun_idを生成し、トレースが上書きされないようにする
    
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
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                # 毎回新しいrun_idとmetadataを生成
                run_id = uuid.uuid4()
                trace_meta = generate_trace_metadata()
                
                # ユーザー指定のmetadataとマージ
                combined_metadata = {
                    **(metadata or {}),
                    **trace_meta,
                }
                
                # traceableでラップして実行
                traced_func = traceable(
                    name=name or func.__name__,
                    run_type=run_type,
                    metadata=combined_metadata,
                    run_id=run_id,
                )(func)
                
                return traced_func(*args, **kwargs)
            
            return wrapper  # type: ignore
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
