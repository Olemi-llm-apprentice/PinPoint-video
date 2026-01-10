"""動画クリップ抽出インターフェース"""

from typing import Protocol

from src.domain.entities import TimeRange


class VideoExtractor(Protocol):
    """動画クリップ抽出のインターフェース"""

    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        """
        ストリーミングURL取得（ダウンロードしない）

        Args:
            video_url: YouTube動画URL

        Returns:
            (video_stream_url, audio_stream_url)
        """
        ...

    def extract_clip(
        self,
        video_url: str,
        time_range: TimeRange,
        output_path: str,
    ) -> str:
        """
        指定範囲のクリップを部分ダウンロード

        Args:
            video_url: YouTube動画URL
            time_range: 抽出する時間範囲
            output_path: 出力ファイルパス

        Returns:
            出力ファイルパス
        """
        ...
