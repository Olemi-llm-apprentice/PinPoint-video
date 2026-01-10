"""youtube-transcript-api v1.2+ クライアント"""


from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
)

from src.domain.entities import Subtitle, SubtitleChunk
from src.infrastructure.logging_config import get_logger, trace_tool

logger = get_logger(__name__)


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

    @trace_tool(name="fetch_transcript")
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

        logger.debug(f"[字幕] 取得開始: {video_id}")
        logger.debug(f"  優先言語: {preferred_languages}")

        try:
            # list() でトランスクリプト一覧を取得
            transcript_list = self.api.list(video_id)
            
            # 利用可能な字幕をログ出力
            available_transcripts = []
            for t in transcript_list:
                available_transcripts.append(f"{t.language_code}({'auto' if t.is_generated else 'manual'})")
            logger.debug(f"  利用可能な字幕: {', '.join(available_transcripts) if available_transcripts else 'なし'}")

            # 手動字幕を優先、なければ自動生成
            transcript = None
            is_auto_generated = False

            try:
                transcript = transcript_list.find_manually_created_transcript(
                    preferred_languages
                )
                logger.debug(f"  手動字幕を使用: {transcript.language_code}")
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(
                        preferred_languages
                    )
                    is_auto_generated = True
                    logger.debug(f"  自動生成字幕を使用: {transcript.language_code}")
                except NoTranscriptFound:
                    logger.debug(f"  {video_id}: 対応する字幕なし (優先言語: {preferred_languages})")
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
            
            total_duration = chunks[-1].end_sec if chunks else 0
            logger.debug(f"[字幕] 取得成功: {video_id} - {len(chunks)}チャンク, {total_duration:.1f}秒")

            return Subtitle(
                video_id=video_id,
                language=fetched_transcript.language,
                language_code=fetched_transcript.language_code,
                chunks=chunks,
                is_auto_generated=is_auto_generated,
            )

        except TranscriptsDisabled:
            logger.debug(f"[字幕] 無効: {video_id} - 字幕が無効化されています")
            return None
        except Exception as e:
            # ネットワークエラー等
            logger.error(f"[字幕] エラー: {video_id} - {e}")
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
        except (TranscriptsDisabled, NoTranscriptFound):
            return None
