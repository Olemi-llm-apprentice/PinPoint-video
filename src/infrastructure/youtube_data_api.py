"""YouTube Data API v3 クライアント"""

import re
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.application.interfaces.youtube_searcher import MultiSearchResult
from src.domain.entities import Video
from src.domain.exceptions import YouTubeSearchError
from src.infrastructure.logging_config import get_logger, trace_tool

logger = get_logger(__name__)


class YouTubeDataAPIClient:
    """YouTube Data API v3 を使用した動画検索"""

    def __init__(
        self,
        api_key: str,
        published_after: str | None = None,
        published_before: str | None = None,
    ):
        """
        Args:
            api_key: YouTube Data API キー
            published_after: デフォルトの公開日時下限（ISO 8601形式）
            published_before: デフォルトの公開日時上限（ISO 8601形式）
        """
        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.default_published_after = published_after
        self.default_published_before = published_before

    @trace_tool(name="youtube_search")
    def search(
        self,
        query: str,
        max_results: int = 30,
        duration_min_sec: int = 60,
        duration_max_sec: int = 7200,
        published_after: str | None = None,
        published_before: str | None = None,
    ) -> list[Video]:
        """
        YouTube動画を検索

        Args:
            query: 検索クエリ
            max_results: 最大取得件数
            duration_min_sec: 最小動画長（秒）
            duration_max_sec: 最大動画長（秒）
            published_after: この日時以降にアップロードされた動画のみ（ISO 8601形式）
            published_before: この日時以前にアップロードされた動画のみ（ISO 8601形式）

        Returns:
            Videoエンティティのリスト

        Raises:
            YouTubeSearchError: API呼び出しエラー
        """
        logger.info(f"[YouTube] 検索開始")
        logger.info(f"  クエリ: {query!r}")
        logger.debug(f"  max_results={max_results}, duration={duration_min_sec}s-{duration_max_sec}s")
        
        try:
            # 検索パラメータを構築
            search_params = {
                "q": query,
                "part": "id,snippet",
                "type": "video",
                "maxResults": min(max_results * 2, 50),  # API上限は50
                "order": "relevance",
                "relevanceLanguage": "ja",  # 日本語優先
            }

            # 日時範囲フィルタ（引数優先、なければデフォルト値）
            effective_published_after = published_after or self.default_published_after
            effective_published_before = published_before or self.default_published_before
            if effective_published_after:
                search_params["publishedAfter"] = effective_published_after
                logger.debug(f"  publishedAfter: {effective_published_after}")
            if effective_published_before:
                search_params["publishedBefore"] = effective_published_before
                logger.debug(f"  publishedBefore: {effective_published_before}")

            # videoDurationは自前フィルタするので "any" を使用
            # （medium=4-20分、long=20分以上 では2時間動画に対応できない）

            # Step 1: search.list で動画ID取得
            logger.debug(f"  Step 1: search.list API呼び出し")
            search_response = (
                self.youtube.search()
                .list(**search_params)
                .execute()
            )

            video_ids = [
                item["id"]["videoId"] for item in search_response.get("items", [])
            ]
            logger.info(f"  検索結果: {len(video_ids)}件の動画ID取得")

            if not video_ids:
                logger.warning(f"[YouTube] 検索結果0件 - クエリ: {query!r}")
                return []

            # Step 2: videos.list で詳細情報取得
            logger.debug(f"  Step 2: videos.list API呼び出し")
            videos_response = (
                self.youtube.videos()
                .list(
                    id=",".join(video_ids),
                    part="snippet,contentDetails",
                )
                .execute()
            )

            videos = []
            filtered_count = 0
            for item in videos_response.get("items", []):
                duration_sec = self._parse_duration(item["contentDetails"]["duration"])

                # duration フィルタ
                if duration_min_sec <= duration_sec <= duration_max_sec:
                    videos.append(
                        Video(
                            video_id=item["id"],
                            title=item["snippet"]["title"],
                            channel_name=item["snippet"]["channelTitle"],
                            duration_sec=duration_sec,
                            published_at=item["snippet"]["publishedAt"],
                            thumbnail_url=item["snippet"]["thumbnails"]["high"]["url"],
                        )
                    )
                else:
                    filtered_count += 1
                    logger.debug(f"    除外: {item['id']} (duration={duration_sec}s)")

            logger.info(f"[YouTube] 検索完了: {len(videos)}件 (duration外で{filtered_count}件除外)")
            for i, v in enumerate(videos[:5]):
                logger.debug(f"    [{i+1}] {v.video_id}: {v.title[:40]}... ({v.duration_sec}s)")
            
            return videos[:max_results]

        except HttpError as e:
            logger.error(f"[YouTube] API エラー: {e}")
            raise YouTubeSearchError(f"YouTube API error: {e}") from e

    def _parse_duration(self, duration_str: str) -> int:
        """ISO 8601 duration を秒に変換（PT1H2M3S → 3723）"""
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    @trace_tool(name="youtube_search_multi_strategy")
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
        1. relevance順（関連性順）
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
        logger.info("=" * 50)
        logger.info("[YouTube] マルチ戦略検索開始")
        logger.info(f"  クエリ数: {len(queries)}")
        for i, q in enumerate(queries):
            logger.info(f"    [{i+1}] {q!r}")

        # 過去1ヶ月の日時を計算
        one_month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # 検索戦略の定義
        strategies = [
            {"name": "relevance", "order": "relevance", "published_after": None},
            {"name": "date", "order": "date", "published_after": None},
            {"name": "relevance_recent", "order": "relevance", "published_after": one_month_ago},
        ]

        # 結果を収集（video_idで重複管理）
        seen_video_ids: set[str] = set()
        all_videos: list[Video] = []
        search_stats: dict[str, int] = {}

        for query in queries:
            for strategy in strategies:
                strategy_key = f"{query[:20]}..._{strategy['name']}" if len(query) > 20 else f"{query}_{strategy['name']}"
                
                logger.info(f"  検索: query={query!r}, strategy={strategy['name']}")

                try:
                    videos = self._search_single_strategy(
                        query=query,
                        order=strategy["order"],
                        published_after=strategy["published_after"],
                        max_results=max_results_per_query,
                        duration_min_sec=duration_min_sec,
                        duration_max_sec=duration_max_sec,
                    )

                    # 重複排除しながら追加
                    new_count = 0
                    for video in videos:
                        if video.video_id not in seen_video_ids:
                            seen_video_ids.add(video.video_id)
                            all_videos.append(video)
                            new_count += 1

                    search_stats[strategy_key] = len(videos)
                    logger.info(f"    結果: {len(videos)}件 (新規: {new_count}件)")

                except Exception as e:
                    logger.warning(f"    検索失敗: {e}")
                    search_stats[strategy_key] = 0

        logger.info("-" * 50)
        logger.info(f"[YouTube] マルチ戦略検索完了")
        logger.info(f"  総検索回数: {len(queries) * len(strategies)}")
        logger.info(f"  重複排除後の動画数: {len(all_videos)}")
        logger.info("=" * 50)

        return MultiSearchResult(
            videos=all_videos,
            search_stats=search_stats,
        )

    def _search_single_strategy(
        self,
        query: str,
        order: str,
        published_after: str | None,
        max_results: int,
        duration_min_sec: int,
        duration_max_sec: int,
    ) -> list[Video]:
        """
        単一の検索戦略で動画を検索（内部メソッド）

        Args:
            query: 検索クエリ
            order: 検索順序 (relevance, date, viewCount, rating)
            published_after: この日時以降に公開された動画のみ（ISO 8601形式）
            max_results: 最大取得件数
            duration_min_sec: 最小動画長（秒）
            duration_max_sec: 最大動画長（秒）

        Returns:
            Videoエンティティのリスト
        """
        try:
            # 検索パラメータを構築
            search_params = {
                "q": query,
                "part": "id,snippet",
                "type": "video",
                "maxResults": min(max_results * 2, 50),
                "order": order,
                "relevanceLanguage": "ja",
            }

            if published_after:
                search_params["publishedAfter"] = published_after

            # Step 1: search.list で動画ID取得
            search_response = (
                self.youtube.search()
                .list(**search_params)
                .execute()
            )

            video_ids = [
                item["id"]["videoId"] for item in search_response.get("items", [])
            ]

            if not video_ids:
                return []

            # Step 2: videos.list で詳細情報取得
            videos_response = (
                self.youtube.videos()
                .list(
                    id=",".join(video_ids),
                    part="snippet,contentDetails",
                )
                .execute()
            )

            videos = []
            for item in videos_response.get("items", []):
                duration_sec = self._parse_duration(item["contentDetails"]["duration"])

                # duration フィルタ
                if duration_min_sec <= duration_sec <= duration_max_sec:
                    videos.append(
                        Video(
                            video_id=item["id"],
                            title=item["snippet"]["title"],
                            channel_name=item["snippet"]["channelTitle"],
                            duration_sec=duration_sec,
                            published_at=item["snippet"]["publishedAt"],
                            thumbnail_url=item["snippet"]["thumbnails"]["high"]["url"],
                        )
                    )

            return videos[:max_results]

        except HttpError as e:
            raise YouTubeSearchError(f"YouTube API error: {e}") from e
