"""時間変換ユーティリティのテスト"""

from src.domain.entities import TimeRange
from src.domain.time_utils import convert_relative_to_absolute


class TestConvertRelativeToAbsolute:
    """相対時間→絶対時間変換のテスト"""

    def test_basic_conversion(self) -> None:
        """基本的な変換"""
        clip_start_sec = 864  # 14:24
        relative_range = TimeRange(36, 225)  # クリップ内 0:36-3:45

        result = convert_relative_to_absolute(clip_start_sec, relative_range)

        assert result.start_sec == 900  # 864 + 36 = 15:00
        assert result.end_sec == 1089   # 864 + 225 = 18:09

    def test_zero_clip_start(self) -> None:
        """クリップ開始が0の場合"""
        clip_start_sec = 0
        relative_range = TimeRange(10, 50)

        result = convert_relative_to_absolute(clip_start_sec, relative_range)

        assert result.start_sec == 10
        assert result.end_sec == 50
