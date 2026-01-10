"""字幕取得インターフェース"""

from typing import Protocol

from src.domain.entities import Subtitle


class SubtitleFetcher(Protocol):
    """字幕取得のインターフェース"""

    def fetch(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> Subtitle | None:
        """
        動画の字幕を取得

        Args:
            video_id: YouTube動画ID
            preferred_languages: 優先する言語コード（デフォルト: ["ja", "en"]）

        Returns:
            Subtitleエンティティ、字幕がない場合はNone
        """
        ...
