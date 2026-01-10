"""LLMクライアントインターフェース"""

from dataclasses import dataclass
from typing import Protocol

from src.domain.entities import SubtitleChunk, TimeRange


@dataclass
class SearchQueryVariants:
    """検索クエリのバリエーション"""

    original: str  # ユーザー入力そのまま
    optimized: str  # LLMで最適化（現行ロジック）
    simplified: str  # シンプルなキーワードに分割


class LLMClient(Protocol):
    """テキスト処理用LLMのインターフェース"""

    def convert_to_search_query(self, user_query: str) -> str:
        """
        ユーザークエリをYouTube検索クエリに変換（後方互換性のため残す）

        Args:
            user_query: ユーザーの入力クエリ

        Returns:
            YouTube検索に最適化されたクエリ
        """
        ...

    def generate_search_queries(self, user_query: str) -> SearchQueryVariants:
        """
        ユーザークエリから複数の検索クエリバリエーションを生成

        Args:
            user_query: ユーザーの入力クエリ

        Returns:
            SearchQueryVariants: 3種類のクエリバリエーション
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

    def filter_videos_by_title(
        self,
        video_titles: list[tuple[str, str]],
        user_query: str,
        max_results: int = 10,
    ) -> list[str]:
        """
        タイトルベースで関連性の高い動画をフィルタリング

        Args:
            video_titles: [(video_id, title), ...] のリスト
            user_query: ユーザークエリ
            max_results: 返す最大件数

        Returns:
            関連性の高い動画のvideo_idリスト
        """
        ...

    def analyze_youtube_video(
        self,
        video_url: str,
        user_query: str,
    ) -> list[tuple[TimeRange, float, str]]:
        """
        YouTube動画URLを直接LLMに渡して関連範囲を特定

        字幕取得が429エラーで失敗した場合のフォールバック用。
        Gemini 2.5はYouTube URLを直接理解できる。

        Args:
            video_url: YouTube動画のURL
            user_query: ユーザークエリ

        Returns:
            [(TimeRange, confidence, summary), ...]
        """
        ...
