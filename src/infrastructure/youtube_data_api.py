"""YouTube Data API v3 クライアント"""

import re

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.domain.entities import Video
from src.domain.exceptions import YouTubeSearchError


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
            if effective_published_before:
                search_params["publishedBefore"] = effective_published_before

            # videoDurationは自前フィルタするので "any" を使用
            # （medium=4-20分、long=20分以上 では2時間動画に対応できない）

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

    def _parse_duration(self, duration_str: str) -> int:
        """ISO 8601 duration を秒に変換（PT1H2M3S → 3723）"""
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
