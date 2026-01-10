"""YouTube検索インターフェース"""

from typing import Protocol

from src.domain.entities import Video


class YouTubeSearcher(Protocol):
    """YouTube動画検索のインターフェース"""

    def search(
        self,
        query: str,
        max_results: int = 10,
        duration_min_sec: int = 60,
        duration_max_sec: int = 1800,
    ) -> list[Video]:
        """
        YouTube動画を検索

        Args:
            query: 検索クエリ
            max_results: 最大取得件数
            duration_min_sec: 最小動画長（秒）
            duration_max_sec: 最大動画長（秒）

        Returns:
            Videoエンティティのリスト
        """
        ...
