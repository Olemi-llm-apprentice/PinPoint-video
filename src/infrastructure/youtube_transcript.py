"""youtube-transcript-api v1.2+ クライアント"""


from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptAvailable,
    NoTranscriptFound,
    TranscriptsDisabled,
)

from src.domain.entities import Subtitle, SubtitleChunk


class YouTubeTranscriptClient:
    """
    youtube-transcript-api v1.2+ 対応

    ⚠️ v1.0.0 での破壊的変更:
    - クラスメソッド → インスタンスメソッド
    - get_transcript() → fetch()
    - list_transcripts() → list()
    - 戻り値が list[dict] → FetchedTranscript オブジェクト
    """

    def __init__(self) -> None:
        # v1.0.0以降はインスタンス化が必要
        self.api = YouTubeTranscriptApi()

    def fetch(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> Subtitle | None:
        """
        動画の字幕を取得

        Args:
            video_id: YouTube動画ID
            preferred_languages: 優先する言語コード

        Returns:
            Subtitleエンティティ、字幕がない場合はNone

        Raises:
            RuntimeError: ネットワークエラー等
        """
        if preferred_languages is None:
            preferred_languages = ["ja", "en"]

        try:
            # list() でトランスクリプト一覧を取得
            transcript_list = self.api.list(video_id)

            # 手動字幕を優先、なければ自動生成
            transcript = None
            is_auto_generated = False

            try:
                transcript = transcript_list.find_manually_created_transcript(
                    preferred_languages
                )
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(
                        preferred_languages
                    )
                    is_auto_generated = True
                except NoTranscriptFound:
                    return None

            # fetch() で字幕データ取得（FetchedTranscript オブジェクトを返す）
            fetched_transcript = transcript.fetch()

            # FetchedTranscript はイテラブル
            # 各要素は FetchedTranscriptSnippet (text, start, duration)
            chunks = [
                SubtitleChunk(
                    start_sec=snippet.start,
                    end_sec=snippet.start + snippet.duration,
                    text=snippet.text,
                )
                for snippet in fetched_transcript
            ]

            return Subtitle(
                video_id=video_id,
                language=fetched_transcript.language,
                language_code=fetched_transcript.language_code,
                chunks=chunks,
                is_auto_generated=is_auto_generated,
            )

        except (TranscriptsDisabled, NoTranscriptAvailable):
            return None
        except Exception as e:
            # ネットワークエラー等
            raise RuntimeError(f"Failed to fetch transcript: {e}") from e

    def fetch_raw(
        self,
        video_id: str,
        preferred_languages: list[str] | None = None,
    ) -> list[dict] | None:
        """
        生データ（list[dict]）が必要な場合のヘルパー

        Returns:
            [{"text": "...", "start": 0.0, "duration": 1.5}, ...]
        """
        if preferred_languages is None:
            preferred_languages = ["ja", "en"]

        try:
            transcript_list = self.api.list(video_id)
            transcript = transcript_list.find_transcript(preferred_languages)
            fetched = transcript.fetch()
            # to_raw_data() で従来形式に変換
            return fetched.to_raw_data()
        except (TranscriptsDisabled, NoTranscriptFound, NoTranscriptAvailable):
            return None
