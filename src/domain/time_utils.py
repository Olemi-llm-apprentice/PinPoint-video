"""時間変換ユーティリティ"""

from src.domain.entities import TimeRange


def convert_relative_to_absolute(
    clip_start_sec: float,
    relative_range: TimeRange,
) -> TimeRange:
    """
    クリップ内の相対時間を元動画の絶対時間に変換

    Args:
        clip_start_sec: クリップの開始時間（元動画基準）
        relative_range: VLMが返したクリップ内相対時間

    Returns:
        元動画での絶対時間

    Example:
        clip_start_sec = 864  # 14:24（バッファ込みクリップ開始）
        relative_range = TimeRange(36, 225)  # クリップ内 0:36-3:45
        → TimeRange(900, 1089)  # 元動画 15:00-18:09
    """
    return TimeRange(
        start_sec=clip_start_sec + relative_range.start_sec,
        end_sec=clip_start_sec + relative_range.end_sec,
    )
