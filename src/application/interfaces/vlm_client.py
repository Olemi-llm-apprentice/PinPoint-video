"""VLMクライアントインターフェース"""

from typing import Protocol

from src.domain.entities import TimeRange


class VLMClient(Protocol):
    """動画分析用VLMのインターフェース"""

    def analyze_video_clip(
        self,
        video_path: str,
        user_query: str,
    ) -> tuple[TimeRange, float, str]:
        """
        動画クリップを分析し、クエリに該当する部分の時間を特定

        Args:
            video_path: ローカルの動画ファイルパス
            user_query: ユーザーの検索クエリ

        Returns:
            (relative_time_range, confidence, summary)
            relative_time_range: クリップ内での相対時間
        """
        ...
