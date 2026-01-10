"""ドメイン固有の例外定義"""


class PinPointVideoError(Exception):
    """基底例外クラス"""

    pass


class YouTubeSearchError(PinPointVideoError):
    """YouTube検索エラー"""

    pass


class SubtitleNotFoundError(PinPointVideoError):
    """字幕が見つからない"""

    pass


class VideoExtractionError(PinPointVideoError):
    """動画クリップ抽出エラー"""

    pass


class LLMError(PinPointVideoError):
    """LLM API エラー"""

    pass


class VLMError(PinPointVideoError):
    """VLM API エラー"""

    pass


class TimeoutError(PinPointVideoError):
    """タイムアウト"""

    pass
