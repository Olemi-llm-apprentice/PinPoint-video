"""LLMクライアントインターフェース"""

from typing import Protocol

from src.domain.entities import SubtitleChunk, TimeRange


class LLMClient(Protocol):
    """テキスト処理用LLMのインターフェース"""

    def convert_to_search_query(self, user_query: str) -> str:
        """
        ユーザークエリをYouTube検索クエリに変換

        Args:
            user_query: ユーザーの入力クエリ

        Returns:
            YouTube検索に最適化されたクエリ
        """
        ...

    def find_relevant_ranges(
        self,
        subtitle_text: str,
        subtitle_chunks: list[SubtitleChunk],
        user_query: str,
    ) -> list[tuple[TimeRange, float, str]]:
        """
        字幕から該当する時間範囲を特定

        Args:
            subtitle_text: 字幕全文
            subtitle_chunks: 字幕チャンクリスト
            user_query: ユーザークエリ

        Returns:
            [(TimeRange, confidence, summary), ...]
        """
        ...
