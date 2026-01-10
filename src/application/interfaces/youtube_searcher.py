"""YouTube検索インターフェース"""

from dataclasses import dataclass, field
from typing import Protocol

from src.domain.entities import Video


@dataclass
class MultiSearchResult:
    """複数検索戦略の結果"""

    videos: list[Video]  # 重複排除済みの動画リスト
    search_stats: dict[str, int] = field(default_factory=dict)  # 各戦略の検索件数


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

    def search_multi_strategy(
        self,
        queries: list[str],
        max_results_per_query: int = 10,
        duration_min_sec: int = 60,
        duration_max_sec: int = 7200,
    ) -> MultiSearchResult:
        """
        複数のクエリと検索戦略で動画を検索し、重複を排除

        各クエリに対して3パターンの検索を実行:
        1. relevance順
        2. date順（新しい順）
        3. relevance順 + 過去1ヶ月フィルタ

        Args:
            queries: 検索クエリのリスト
            max_results_per_query: 各クエリ・戦略あたりの最大取得件数
            duration_min_sec: 最小動画長（秒）
            duration_max_sec: 最大動画長（秒）

        Returns:
            MultiSearchResult: 重複排除済みの結果と統計情報
        """
        ...
