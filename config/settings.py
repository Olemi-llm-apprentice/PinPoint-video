"""設定管理"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """アプリケーション設定"""

    # API Keys
    YOUTUBE_API_KEY: str
    GEMINI_API_KEY: str

    # LLM Models
    # デフォルトモデル（個別設定がない場合に使用）
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    # クエリ変換用モデル（ユーザー入力→YouTube検索クエリ）
    QUERY_CONVERT_MODEL: str | None = None
    # 字幕分析用モデル（字幕から関連範囲を特定）
    SUBTITLE_ANALYSIS_MODEL: str | None = None
    # 動画分析用モデル（VLMによる精密時刻特定）
    VIDEO_ANALYSIS_MODEL: str | None = None

    # Processing
    MAX_SEARCH_RESULTS: int = 30
    MAX_FINAL_RESULTS: int = 5
    BUFFER_RATIO: float = 0.2
    ENABLE_VLM_REFINEMENT: bool = True
    MIN_CONFIDENCE: float = 0.3

    # YouTube URL Fallback (字幕取得429エラー時の代替処理)
    # GeminiにYouTube URLを直接渡して分析する機能
    ENABLE_YOUTUBE_URL_FALLBACK: bool = True
    # フォールバック対象の最大動画長（秒）- Geminiの制限上20分程度が実用的
    YOUTUBE_URL_FALLBACK_MAX_DURATION: int = 1200  # 20分

    # Duration filters (seconds)
    DURATION_MIN_SEC: int = 60
    DURATION_MAX_SEC: int = 7200  # 2時間

    # Date filters (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ)
    # 例: "2024-01-01T00:00:00Z"
    PUBLISHED_AFTER: str | None = None
    PUBLISHED_BEFORE: str | None = None

    # Timeouts
    YOUTUBE_SEARCH_TIMEOUT: int = 10
    SUBTITLE_FETCH_TIMEOUT: int = 10
    CLIP_EXTRACT_TIMEOUT: int = 120
    VLM_ANALYSIS_TIMEOUT: int = 60

    # Paths
    TEMP_DIR: str = "temp"
    FFMPEG_PATH: str = "ffmpeg"
    YTDLP_PATH: str = "yt-dlp"

    # Logging & Observability
    LOG_LEVEL: str = "INFO"
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "pinpoint-video"

    def get_model(self, purpose: str) -> str:
        """用途に応じたモデル名を取得"""
        model_map = {
            "query_convert": self.QUERY_CONVERT_MODEL,
            "subtitle_analysis": self.SUBTITLE_ANALYSIS_MODEL,
            "video_analysis": self.VIDEO_ANALYSIS_MODEL,
        }
        return model_map.get(purpose) or self.DEFAULT_MODEL

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    """シングルトンで設定を取得"""
    return Settings()
