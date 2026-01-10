"""ドメインエンティティ定義"""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class TimeRange:
    """時間範囲を表す値オブジェクト"""

    start_sec: float
    end_sec: float

    def __post_init__(self) -> None:
        if self.start_sec < 0:
            raise ValueError("start_sec must be non-negative")
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")

    @property
    def duration_sec(self) -> float:
        """区間の長さ（秒）"""
        return self.end_sec - self.start_sec

    def with_buffer(self, buffer_ratio: float = 0.2) -> "TimeRange":
        """
        前後にバッファを追加した新しいTimeRangeを返す

        Args:
            buffer_ratio: 区間長に対するバッファの割合（デフォルト20%）

        Returns:
            バッファ追加後のTimeRange
        """
        buffer_sec = self.duration_sec * buffer_ratio
        new_start = max(0, self.start_sec - buffer_sec)
        new_end = self.end_sec + buffer_sec
        return TimeRange(start_sec=new_start, end_sec=new_end)

    def to_ffmpeg_ss(self) -> str:
        """ffmpegの-ssオプション用フォーマット（HH:MM:SS.ms）"""
        td = timedelta(seconds=self.start_sec)
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = int((self.start_sec % 1) * 100)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:02d}"

    def to_ffmpeg_t(self) -> str:
        """ffmpegの-tオプション用フォーマット（duration）"""
        td = timedelta(seconds=self.duration_sec)
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = int((self.duration_sec % 1) * 100)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:02d}"

    def to_youtube_embed_params(self) -> dict[str, int]:
        """YouTube埋め込み用パラメータ"""
        return {"start": int(self.start_sec), "end": int(self.end_sec)}


@dataclass(frozen=True)
class SubtitleChunk:
    """字幕の1チャンク"""

    start_sec: float
    end_sec: float
    text: str


@dataclass
class Subtitle:
    """動画の字幕全体"""

    video_id: str
    language: str
    language_code: str
    chunks: list[SubtitleChunk]
    is_auto_generated: bool

    @property
    def full_text(self) -> str:
        """字幕全文を結合"""
        return " ".join(chunk.text for chunk in self.chunks)

    def get_chunks_in_range(self, time_range: TimeRange) -> list[SubtitleChunk]:
        """指定範囲内のチャンクを取得"""
        return [
            chunk
            for chunk in self.chunks
            if chunk.start_sec >= time_range.start_sec and chunk.end_sec <= time_range.end_sec
        ]


@dataclass
class Video:
    """YouTube動画のメタデータ"""

    video_id: str
    title: str
    channel_name: str
    duration_sec: int
    published_at: str
    thumbnail_url: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.video_id}"

    def embed_url_with_time(self, time_range: TimeRange) -> str:
        """タイムスタンプ付き埋め込みURL"""
        params = time_range.to_youtube_embed_params()
        return f"{self.embed_url}?start={params['start']}&end={params['end']}"


@dataclass
class VideoSegment:
    """動画内の特定セグメント"""

    video: Video
    time_range: TimeRange
    summary: str
    confidence: float  # 0.0 - 1.0

    @property
    def embed_url(self) -> str:
        return self.video.embed_url_with_time(self.time_range)


@dataclass
class SearchResult:
    """検索結果全体"""

    query: str
    segments: list[VideoSegment]
    processing_time_sec: float
