"""ドメインエンティティのテスト"""

import pytest

from src.domain.entities import TimeRange


class TestTimeRange:
    """TimeRangeのテスト"""

    def test_duration(self) -> None:
        """区間の長さ計算"""
        tr = TimeRange(start_sec=100, end_sec=200)
        assert tr.duration_sec == 100

    def test_with_buffer(self) -> None:
        """バッファ追加"""
        tr = TimeRange(start_sec=100, end_sec=200)
        buffered = tr.with_buffer(0.2)
        assert buffered.start_sec == 80  # 100 - 20
        assert buffered.end_sec == 220  # 200 + 20

    def test_buffer_not_negative(self) -> None:
        """バッファでstart_secが負にならない"""
        tr = TimeRange(start_sec=10, end_sec=50)
        buffered = tr.with_buffer(0.5)
        assert buffered.start_sec == 0  # max(0, 10-20)

    def test_invalid_range_negative_start(self) -> None:
        """開始時間が負の場合エラー"""
        with pytest.raises(ValueError, match="non-negative"):
            TimeRange(start_sec=-1, end_sec=100)

    def test_invalid_range_end_before_start(self) -> None:
        """終了時間が開始時間より前の場合エラー"""
        with pytest.raises(ValueError, match="greater than"):
            TimeRange(start_sec=200, end_sec=100)

    def test_to_ffmpeg_ss(self) -> None:
        """ffmpeg -ss フォーマット"""
        tr = TimeRange(start_sec=3661.5, end_sec=3700)  # 1:01:01.50
        assert tr.to_ffmpeg_ss() == "01:01:01.50"

    def test_to_ffmpeg_t(self) -> None:
        """ffmpeg -t フォーマット"""
        tr = TimeRange(start_sec=0, end_sec=65.25)  # 1分5秒
        assert tr.to_ffmpeg_t() == "00:01:05.25"

    def test_to_youtube_embed_params(self) -> None:
        """YouTube埋め込みパラメータ"""
        tr = TimeRange(start_sec=120.5, end_sec=180.9)
        params = tr.to_youtube_embed_params()
        assert params == {"start": 120, "end": 180}
