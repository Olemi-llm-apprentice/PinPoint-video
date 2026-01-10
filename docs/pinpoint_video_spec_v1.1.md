# PinPoint.video 詳細仕様書

## 1. プロダクト概要

### 1.1 プロダクト名
**PinPoint.video**

### 1.2 コンセプト
YouTube動画から、ユーザーが求める情報が含まれる部分だけをピンポイントで抽出し、タイムスタンプ付きリンクとして提供するAIツール。

### 1.3 解決する課題
- 20分の動画の中で、必要な情報は40秒しかないのに、全編を視聴する時間の無駄
- 2時間のカンファレンス動画から特定のトピックを探す困難さ
- 技術チュートリアル動画で「この機能の使い方だけ知りたい」というニーズ

### 1.4 ターゲットユーザー
- 開発者（技術チュートリアルを効率的に消化したい）
- リサーチャー（長時間のインタビュー・カンファレンス動画から情報抽出）
- 学習者（教育コンテンツの特定部分だけ復習したい）

### 1.5 主要な価値提案
- **時間短縮**: 20分 → 40秒（必要な部分だけ）
- **精度**: AIによる内容理解で、字幕検索より高精度
- **即座にアクセス**: タイムスタンプ付きYouTubeリンクで即座に該当部分へ

---

## 2. システムアーキテクチャ

### 2.1 全体構成

```
┌─────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                       │
│                      (Streamlit Web UI)                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Application Layer                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ SearchUseCase│  │ExtractUseCase│  │ PrecisionRefineUseCase │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Domain Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │
│  │  Video   │  │ Subtitle │  │TimeRange │  │ SearchResult   │   │
│  │  Entity  │  │  Entity  │  │  Entity  │  │    Entity      │   │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │YouTube API  │  │yt-dlp/ffmpeg│  │    Gemini API Client    │  │
│  │  Client     │  │  Extractor  │  │  (Flash / Pro Vision)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 ディレクトリ構造

```
pinpoint_video/
├── app/
│   └── main.py                    # Streamlit エントリポイント
├── src/
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py            # Video, Subtitle, TimeRange, SearchResult
│   │   └── exceptions.py          # ドメイン固有の例外
│   ├── application/
│   │   ├── __init__.py
│   │   ├── interfaces/
│   │   │   ├── __init__.py
│   │   │   ├── youtube_searcher.py    # Protocol定義
│   │   │   ├── subtitle_fetcher.py    # Protocol定義
│   │   │   ├── video_extractor.py     # Protocol定義
│   │   │   ├── llm_client.py          # Protocol定義
│   │   │   └── vlm_client.py          # Protocol定義
│   │   └── usecases/
│   │       ├── __init__.py
│   │       ├── search_videos.py       # 動画検索ユースケース
│   │       ├── extract_segments.py    # セグメント抽出ユースケース
│   │       └── refine_timestamp.py    # 精密時刻特定ユースケース
│   └── infrastructure/
│       ├── __init__.py
│       ├── youtube_data_api.py        # YouTube Data API v3
│       ├── youtube_transcript.py      # youtube-transcript-api
│       ├── ytdlp_extractor.py         # yt-dlp + ffmpeg
│       ├── gemini_llm_client.py       # Gemini Flash (テキスト)
│       └── gemini_vlm_client.py       # Gemini Pro Vision (動画)
├── config/
│   └── settings.py                # 設定管理
├── tests/
│   ├── unit/
│   └── integration/
├── requirements.txt
├── .env.example
└── README.md
```

### 2.3 依存性注入（DI）パターン

```python
# src/application/interfaces/video_extractor.py
from typing import Protocol
from src.domain.entities import TimeRange

class VideoExtractor(Protocol):
    """動画クリップ抽出のインターフェース"""
    
    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        """ストリーミングURL取得（video, audio）"""
        ...
    
    def extract_clip(
        self, 
        video_url: str, 
        time_range: TimeRange,
        output_path: str
    ) -> str:
        """指定範囲のクリップを抽出"""
        ...
```

```python
# src/infrastructure/ytdlp_extractor.py
class YtdlpVideoExtractor:
    """yt-dlp + ffmpeg による実装"""
    
    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        # 実装
        ...
    
    def extract_clip(
        self, 
        video_url: str, 
        time_range: TimeRange,
        output_path: str
    ) -> str:
        # 実装
        ...
```

```python
# main.py での組み立て
from src.infrastructure.ytdlp_extractor import YtdlpVideoExtractor
from src.infrastructure.gemini_vlm_client import GeminiVLMClient
from src.application.usecases.refine_timestamp import RefineTimestampUseCase

# DIで注入（新SDK: api_keyはオプション、環境変数から自動取得）
extractor = YtdlpVideoExtractor()
vlm_client = GeminiVLMClient()  # GEMINI_API_KEY環境変数から自動取得
refine_usecase = RefineTimestampUseCase(
    video_extractor=extractor,
    vlm_client=vlm_client
)
```

---

## 3. ドメインモデル

### 3.1 エンティティ定義

```python
# src/domain/entities.py
from dataclasses import dataclass
from typing import Optional
from datetime import timedelta

@dataclass(frozen=True)
class TimeRange:
    """時間範囲を表す値オブジェクト"""
    start_sec: float
    end_sec: float
    
    def __post_init__(self):
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
        return TimeRange(
            start_sec=max(0, self.start_sec - buffer_sec),
            end_sec=self.end_sec + buffer_sec
        )
    
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
        return {
            "start": int(self.start_sec),
            "end": int(self.end_sec)
        }


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
    chunks: list[SubtitleChunk]
    is_auto_generated: bool
    
    @property
    def full_text(self) -> str:
        """字幕全文を結合"""
        return " ".join(chunk.text for chunk in self.chunks)
    
    def get_chunks_in_range(self, time_range: TimeRange) -> list[SubtitleChunk]:
        """指定範囲内のチャンクを取得"""
        return [
            chunk for chunk in self.chunks
            if chunk.start_sec >= time_range.start_sec 
            and chunk.end_sec <= time_range.end_sec
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
```

---

## 4. 処理フロー詳細

### 4.1 全体フロー図

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Phase 1] ユーザー入力処理                                            │
├──────────────────────────────────────────────────────────────────────┤
│ 1. ユーザーが検索クエリを入力                                         │
│    例: 「Claude Codeのultrathinkの使い方」                           │
│                                                                      │
│ 2. LLM（Gemini Flash）でYouTube検索クエリに変換                      │
│    入力: ユーザークエリ                                               │
│    出力: "Claude Code ultrathink tutorial"                           │
│    処理時間: 1-2秒                                                    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [Phase 2] YouTube検索 & フィルタリング                                │
├──────────────────────────────────────────────────────────────────────┤
│ 3. YouTube Data API v3 で動画検索                                    │
│    - 検索クエリ: Phase 1の出力                                        │
│    - 取得件数: 10件                                                   │
│    - ソート: relevance（デフォルト）                                  │
│    処理時間: 1-2秒                                                    │
│                                                                      │
│ 4. メタデータでフィルタリング                                         │
│    - duration: 60秒以上、1800秒（30分）以下                          │
│    - 字幕あり動画のみ（次ステップで確認）                             │
│    処理時間: <1秒                                                     │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [Phase 3] 字幕取得 & 粗い範囲特定                                     │
├──────────────────────────────────────────────────────────────────────┤
│ 5. 各動画の字幕を並列取得（youtube-transcript-api）                   │
│    - 字幕なし動画は除外                                               │
│    - 日本語 or 英語字幕を優先                                         │
│    処理時間: 2-3秒（並列処理）                                        │
│                                                                      │
│ 6. LLM（Gemini Flash）で字幕から該当範囲を粗く特定                   │
│    入力: 字幕全文 + ユーザークエリ                                    │
│    出力: 該当する可能性のある時間範囲（複数可）                        │
│    処理時間: 2-3秒                                                    │
│                                                                      │
│ 7. 上位5件に絞り込み                                                  │
│    - 該当範囲が見つかった動画を優先                                   │
│    - confidence scoreでソート                                        │
│    処理時間: <1秒                                                     │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [Phase 4] 部分ダウンロード & 精密時刻特定                             │
├──────────────────────────────────────────────────────────────────────┤
│ 8. 各動画の該当範囲 + バッファを部分ダウンロード                      │
│    - バッファ: 該当範囲の20%を前後に追加                              │
│    - yt-dlp -g でストリーミングURL取得                                │
│    - ffmpeg で部分ダウンロード                                        │
│    処理時間: 10-30秒/動画                                             │
│                                                                      │
│ 9. VLM（Gemini Pro Vision）で精密な時刻を特定                        │
│    入力: ダウンロードしたクリップ + ユーザークエリ                    │
│    出力: クリップ内の相対時間（開始・終了）                           │
│    処理時間: 10-20秒/動画                                             │
│                                                                      │
│ 10. 相対時間を絶対時間に変換                                          │
│     クリップ開始時間 + VLM出力 = 元動画での絶対時間                   │
│     処理時間: <1秒                                                    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [Phase 5] 結果生成 & 表示                                             │
├──────────────────────────────────────────────────────────────────────┤
│ 11. YouTube埋め込みURL生成                                            │
│     https://youtube.com/embed/{video_id}?start={sec}&end={sec}       │
│                                                                      │
│ 12. 結果をStreamlit UIで表示                                          │
│     - 各セグメントのサマリー                                          │
│     - タイムスタンプ付きYouTubeプレーヤー                             │
│     - 元動画へのリンク                                                │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 処理時間サマリー

| Phase | 処理内容 | 推定時間 |
|-------|----------|----------|
| 1 | クエリ変換 | 1-2秒 |
| 2 | YouTube検索 + フィルタ | 1-2秒 |
| 3 | 字幕取得 + 粗い範囲特定 | 4-6秒 |
| 4 | 部分DL + 精密特定（5動画） | 20-50秒 |
| 5 | 結果生成 | <1秒 |
| **合計** | | **30秒〜1分** |

※ 2時間の長時間動画でも、部分ダウンロードにより処理時間は変わらない

---

## 5. 各コンポーネント詳細仕様

### 5.1 YouTube検索（Phase 2）

#### 5.1.1 インターフェース

```python
# src/application/interfaces/youtube_searcher.py
from typing import Protocol
from src.domain.entities import Video

class YouTubeSearcher(Protocol):
    def search(
        self, 
        query: str, 
        max_results: int = 10,
        duration_min_sec: int = 60,
        duration_max_sec: int = 1800
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
```

#### 5.1.2 実装詳細

```python
# src/infrastructure/youtube_data_api.py
from googleapiclient.discovery import build
from src.domain.entities import Video

class YouTubeDataAPIClient:
    def __init__(self, api_key: str):
        self.youtube = build("youtube", "v3", developerKey=api_key)
    
    def search(
        self, 
        query: str, 
        max_results: int = 10,
        duration_min_sec: int = 60,
        duration_max_sec: int = 1800
    ) -> list[Video]:
        # Step 1: search.list で動画ID取得
        search_response = self.youtube.search().list(
            q=query,
            part="id,snippet",
            type="video",
            maxResults=max_results * 2,  # フィルタ後に減るので多めに取得
            order="relevance",
            videoDuration="medium",  # 4分〜20分
            relevanceLanguage="ja",  # 日本語優先
        ).execute()
        
        video_ids = [
            item["id"]["videoId"] 
            for item in search_response.get("items", [])
        ]
        
        # Step 2: videos.list で詳細情報取得
        videos_response = self.youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,contentDetails"
        ).execute()
        
        videos = []
        for item in videos_response.get("items", []):
            duration_sec = self._parse_duration(
                item["contentDetails"]["duration"]
            )
            
            # duration フィルタ
            if duration_min_sec <= duration_sec <= duration_max_sec:
                videos.append(Video(
                    video_id=item["id"],
                    title=item["snippet"]["title"],
                    channel_name=item["snippet"]["channelTitle"],
                    duration_sec=duration_sec,
                    published_at=item["snippet"]["publishedAt"],
                    thumbnail_url=item["snippet"]["thumbnails"]["high"]["url"]
                ))
        
        return videos[:max_results]
    
    def _parse_duration(self, duration_str: str) -> int:
        """ISO 8601 duration を秒に変換（PT1H2M3S → 3723）"""
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
```

### 5.2 字幕取得（Phase 3）

#### 5.2.1 インターフェース

```python
# src/application/interfaces/subtitle_fetcher.py
from typing import Protocol, Optional
from src.domain.entities import Subtitle

class SubtitleFetcher(Protocol):
    def fetch(
        self, 
        video_id: str,
        preferred_languages: list[str] = ["ja", "en"]
    ) -> Optional[Subtitle]:
        """
        動画の字幕を取得
        
        Args:
            video_id: YouTube動画ID
            preferred_languages: 優先する言語コード
        
        Returns:
            Subtitleエンティティ、字幕がない場合はNone
        """
        ...
```

#### 5.2.2 実装詳細

```python
# src/infrastructure/youtube_transcript.py
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, 
    NoTranscriptFound,
    NoTranscriptAvailable
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
    
    def __init__(self):
        # v1.0.0以降はインスタンス化が必要
        self.api = YouTubeTranscriptApi()
    
    def fetch(
        self, 
        video_id: str,
        preferred_languages: list[str] = ["ja", "en"]
    ) -> Optional[Subtitle]:
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
                    text=snippet.text
                )
                for snippet in fetched_transcript
            ]
            
            return Subtitle(
                video_id=video_id,
                language=fetched_transcript.language,
                language_code=fetched_transcript.language_code,
                chunks=chunks,
                is_auto_generated=is_auto_generated
            )
            
        except (TranscriptsDisabled, NoTranscriptAvailable):
            return None
        except Exception as e:
            # ネットワークエラー等
            raise RuntimeError(f"Failed to fetch transcript: {e}")
    
    def fetch_raw(
        self,
        video_id: str,
        preferred_languages: list[str] = ["ja", "en"]
    ) -> Optional[list[dict]]:
        """
        生データ（list[dict]）が必要な場合のヘルパー
        
        Returns:
            [{"text": "...", "start": 0.0, "duration": 1.5}, ...]
        """
        try:
            transcript_list = self.api.list(video_id)
            transcript = transcript_list.find_transcript(preferred_languages)
            fetched = transcript.fetch()
            # to_raw_data() で従来形式に変換
            return fetched.to_raw_data()
        except (TranscriptsDisabled, NoTranscriptFound, NoTranscriptAvailable):
            return None
```

#### 5.2.3 エンティティ更新（language_code追加）

```python
# src/domain/entities.py の Subtitle クラスを更新
@dataclass
class Subtitle:
    """動画の字幕全体"""
    video_id: str
    language: str           # "English", "日本語" など
    language_code: str      # "en", "ja" など（新規追加）
    chunks: list[SubtitleChunk]
    is_auto_generated: bool
    
    @property
    def full_text(self) -> str:
        """字幕全文を結合"""
        return " ".join(chunk.text for chunk in self.chunks)
```


### 5.3 字幕からの粗い範囲特定（Phase 3）

#### 5.3.1 インターフェース

```python
# src/application/interfaces/llm_client.py
from typing import Protocol
from src.domain.entities import TimeRange

class LLMClient(Protocol):
    def convert_to_search_query(self, user_query: str) -> str:
        """ユーザークエリをYouTube検索クエリに変換"""
        ...
    
    def find_relevant_ranges(
        self, 
        subtitle_text: str,
        subtitle_chunks: list[SubtitleChunk],
        user_query: str
    ) -> list[tuple[TimeRange, float, str]]:
        """
        字幕から該当する時間範囲を特定
        
        Returns:
            [(TimeRange, confidence, summary), ...]
        """
        ...
```

#### 5.3.2 実装詳細

```python
# src/infrastructure/gemini_llm_client.py
from google import genai
from google.genai import types
import json
from src.domain.entities import TimeRange, SubtitleChunk

class GeminiLLMClient:
    """
    Google GenAI SDK (google-genai) を使用
    
    ⚠️ 旧SDK (google-generativeai) は 2025/11/30 でサポート終了
    
    環境変数:
        GEMINI_API_KEY: APIキー（自動で読み込まれる）
    """
    
    def __init__(self, api_key: str | None = None):
        # api_key を渡さない場合、GEMINI_API_KEY 環境変数から自動取得
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()  # 環境変数から自動取得
    
    def convert_to_search_query(self, user_query: str) -> str:
        prompt = f"""
あなたはYouTube検索クエリの最適化専門家です。

ユーザーの質問を、YouTube検索で最も関連性の高い結果が得られる
検索クエリに変換してください。

ルール:
- 英語のキーワードを含める（技術用語は英語が効果的）
- 5-7語程度に収める
- 「tutorial」「how to」「explained」などの修飾語を適宜追加

ユーザーの質問: {user_query}

検索クエリのみを出力してください（説明不要）:
"""
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    
    def find_relevant_ranges(
        self, 
        subtitle_text: str,
        subtitle_chunks: list[SubtitleChunk],
        user_query: str
    ) -> list[tuple[TimeRange, float, str]]:
        # 字幕チャンクを時間付きで整形
        formatted_chunks = "\n".join([
            f"[{chunk.start_sec:.1f}s - {chunk.end_sec:.1f}s] {chunk.text}"
            for chunk in subtitle_chunks
        ])
        
        prompt = f"""
あなたは動画内容分析の専門家です。

以下の字幕データから、ユーザーの質問に関連する部分を特定してください。

ユーザーの質問: {user_query}

字幕データ:
{formatted_chunks}

以下のJSON形式で回答してください:
{{
  "segments": [
    {{
      "start_sec": <開始秒>,
      "end_sec": <終了秒>,
      "confidence": <0.0-1.0の確信度>,
      "summary": "<この部分で話されている内容の要約>"
    }}
  ]
}}

ルール:
- 関連性の高い部分を最大3つまで抽出
- 関連する部分がない場合は空配列を返す
- confidenceは内容の関連性に基づいて設定
- summaryは日本語で50文字以内

JSONのみを出力してください:
"""
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        try:
            # JSON部分を抽出してパース
            json_str = response.text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            
            data = json.loads(json_str)
            
            results = []
            for seg in data.get("segments", []):
                time_range = TimeRange(
                    start_sec=float(seg["start_sec"]),
                    end_sec=float(seg["end_sec"])
                )
                confidence = float(seg["confidence"])
                summary = seg["summary"]
                results.append((time_range, confidence, summary))
            
            return results
            
        except (json.JSONDecodeError, KeyError, ValueError):
            return []
```

### 5.4 部分ダウンロード（Phase 4）

#### 5.4.1 インターフェース

```python
# src/application/interfaces/video_extractor.py
from typing import Protocol
from src.domain.entities import TimeRange

class VideoExtractor(Protocol):
    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        """
        ストリーミングURL取得（ダウンロードしない）
        
        Returns:
            (video_stream_url, audio_stream_url)
        """
        ...
    
    def extract_clip(
        self, 
        video_url: str, 
        time_range: TimeRange,
        output_path: str
    ) -> str:
        """
        指定範囲のクリップを部分ダウンロード
        
        Args:
            video_url: YouTube動画URL
            time_range: 抽出する時間範囲
            output_path: 出力ファイルパス
        
        Returns:
            出力ファイルパス
        """
        ...
```

#### 5.4.2 実装詳細

```python
# src/infrastructure/ytdlp_extractor.py
import subprocess
import tempfile
from pathlib import Path
from src.domain.entities import TimeRange

class YtdlpVideoExtractor:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ytdlp_path: str = "yt-dlp"):
        self.ffmpeg_path = ffmpeg_path
        self.ytdlp_path = ytdlp_path
    
    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        """
        yt-dlp -g でストリーミングURLを取得
        動画全体をダウンロードせず、URLだけ取得（1-2秒）
        """
        result = subprocess.run(
            [
                self.ytdlp_path,
                "--youtube-skip-dash-manifest",
                "-g",
                video_url
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            raise ValueError(f"Failed to get stream URLs: {result.stdout}")
        
        return lines[0], lines[1]  # video_url, audio_url
    
    def extract_clip(
        self, 
        video_url: str, 
        time_range: TimeRange,
        output_path: str
    ) -> str:
        """
        指定範囲だけを部分ダウンロード
        
        処理フロー:
        1. yt-dlp -g でストリーミングURL取得
        2. ffmpeg -ss でシーク（Range Requestで該当位置から取得）
        3. -t で指定長さだけダウンロード
        4. video + audio をマージして出力
        
        2時間動画でも、切り出す部分の長さだけで処理時間が決まる
        """
        video_stream, audio_stream = self.get_stream_urls(video_url)
        
        ss_time = time_range.to_ffmpeg_ss()
        duration = time_range.to_ffmpeg_t()
        
        # ffmpeg コマンド構築
        cmd = [
            self.ffmpeg_path,
            "-y",  # 上書き許可
            "-ss", ss_time,  # 開始位置（video stream）
            "-i", video_stream,
            "-ss", ss_time,  # 開始位置（audio stream）
            "-i", audio_stream,
            "-t", duration,  # 切り出し長さ
            "-map", "0:v",  # video streamを使用
            "-map", "1:a",  # audio streamを使用
            "-c:v", "libx264",  # video codec
            "-c:a", "aac",      # audio codec
            "-movflags", "+faststart",  # Web再生用最適化
            output_path
        ]
        
        subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            timeout=120  # 2分でタイムアウト
        )
        
        return output_path
```

### 5.5 VLMによる精密時刻特定（Phase 4）

#### 5.5.1 インターフェース

```python
# src/application/interfaces/vlm_client.py
from typing import Protocol
from src.domain.entities import TimeRange

class VLMClient(Protocol):
    def analyze_video_clip(
        self,
        video_path: str,
        user_query: str
    ) -> tuple[TimeRange, float, str]:
        """
        動画クリップを分析し、クエリに該当する部分の時間を特定
        
        Args:
            video_path: ローカルの動画ファイルパス
            user_query: ユーザーの検索クエリ
        
        Returns:
            (relative_time_range, confidence, summary)
            relative_time_range: クリップ内での相対時間
        """
        ...
```

#### 5.5.2 実装詳細

```python
# src/infrastructure/gemini_vlm_client.py
from google import genai
from google.genai import types
import json
from pathlib import Path
from src.domain.entities import TimeRange

class GeminiVLMClient:
    """
    Google GenAI SDK (google-genai) を使用した動画分析
    
    動画理解の仕様:
    - 最大動画長: 1Mコンテキスト=1時間、2Mコンテキスト=2時間
    - サンプリング: デフォルト1FPS（カスタマイズ可能）
    - トークン計算: 約300tokens/秒（低解像度: 100tokens/秒）
    """
    
    def __init__(self, api_key: str | None = None):
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()
    
    def analyze_video_clip(
        self,
        video_path: str,
        user_query: str
    ) -> tuple[TimeRange, float, str]:
        """
        動画クリップを分析し、クエリに該当する部分の時間を特定
        
        Note:
        - gemini-2.5-flash は動画分析に対応
        - 部分ダウンロードしたクリップは通常5分以下なので余裕
        """
        # 動画ファイルをアップロード
        video_file = self.client.files.upload(file=video_path)
        
        prompt = f"""
あなたは動画内容分析の専門家です。

この動画クリップを分析し、以下の質問に関連する部分を特定してください。

質問: {user_query}

以下のJSON形式で回答してください:
{{
  "start_sec": <クリップ内での開始秒>,
  "end_sec": <クリップ内での終了秒>,
  "confidence": <0.0-1.0の確信度>,
  "summary": "<該当部分で話されている内容の要約>"
}}

ルール:
- start_sec, end_sec はこの動画クリップ内での相対時間（0秒から開始）
- 該当する部分がない場合は confidence を 0.0 にする
- summary は日本語で100文字以内
- 映像と音声の両方を考慮して判断する

JSONのみを出力してください:
"""
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[video_file, prompt]
            )
            
            json_str = response.text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            
            data = json.loads(json_str)
            
            time_range = TimeRange(
                start_sec=float(data["start_sec"]),
                end_sec=float(data["end_sec"])
            )
            confidence = float(data["confidence"])
            summary = data["summary"]
            
            return time_range, confidence, summary
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Failed to parse VLM response: {e}")
        
        finally:
            # アップロードしたファイルを削除
            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass
    
    def analyze_video_clip_with_custom_fps(
        self,
        video_path: str,
        user_query: str,
        fps: float = 1.0
    ) -> tuple[TimeRange, float, str]:
        """
        カスタムFPSで動画を分析（長い動画や高速動画向け）
        
        Args:
            fps: サンプリングFPS（デフォルト1.0）
                 - 長い動画: 0.5以下推奨
                 - 高速アクション: 2.0以上推奨
        """
        video_bytes = Path(video_path).read_bytes()
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=types.Content(
                parts=[
                    types.Part(
                        inline_data=types.Blob(
                            data=video_bytes,
                            mime_type="video/mp4"
                        ),
                        video_metadata=types.VideoMetadata(fps=fps)
                    ),
                    types.Part(text=f"質問: {user_query}\n\nJSON形式で回答:")
                ]
            )
        )
        
        # 以下、パース処理は同様
        # ...
```

### 5.6 時間変換ユーティリティ

```python
# src/domain/time_utils.py
from src.domain.entities import TimeRange

def convert_relative_to_absolute(
    clip_start_sec: float,
    relative_range: TimeRange
) -> TimeRange:
    """
    クリップ内の相対時間を元動画の絶対時間に変換
    
    Args:
        clip_start_sec: クリップの開始時間（元動画基準）
        relative_range: VLMが返したクリップ内相対時間
    
    Returns:
        元動画での絶対時間
    
    Example:
        clip_start_sec = 864  # 14:24（バッファ込みクリップ開始）
        relative_range = TimeRange(36, 225)  # クリップ内 0:36-3:45
        → TimeRange(900, 1089)  # 元動画 15:00-18:09
    """
    return TimeRange(
        start_sec=clip_start_sec + relative_range.start_sec,
        end_sec=clip_start_sec + relative_range.end_sec
    )
```

---

## 6. ユースケース実装

### 6.1 メインユースケース（統合）

```python
# src/application/usecases/extract_segments.py
from dataclasses import dataclass
from typing import Optional
import tempfile
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.domain.entities import (
    Video, Subtitle, TimeRange, VideoSegment, SearchResult
)
from src.domain.time_utils import convert_relative_to_absolute
from src.application.interfaces.youtube_searcher import YouTubeSearcher
from src.application.interfaces.subtitle_fetcher import SubtitleFetcher
from src.application.interfaces.llm_client import LLMClient
from src.application.interfaces.video_extractor import VideoExtractor
from src.application.interfaces.vlm_client import VLMClient


@dataclass
class ExtractSegmentsConfig:
    """ユースケースの設定"""
    max_search_results: int = 10
    max_final_results: int = 5
    buffer_ratio: float = 0.2  # バッファ割合（20%）
    min_confidence: float = 0.3  # 最低確信度
    enable_vlm_refinement: bool = True  # VLM精密化を有効にするか


class ExtractSegmentsUseCase:
    """
    メインユースケース: ユーザークエリから関連動画セグメントを抽出
    """
    
    def __init__(
        self,
        youtube_searcher: YouTubeSearcher,
        subtitle_fetcher: SubtitleFetcher,
        llm_client: LLMClient,
        video_extractor: VideoExtractor,
        vlm_client: VLMClient,
        config: Optional[ExtractSegmentsConfig] = None
    ):
        self.youtube_searcher = youtube_searcher
        self.subtitle_fetcher = subtitle_fetcher
        self.llm_client = llm_client
        self.video_extractor = video_extractor
        self.vlm_client = vlm_client
        self.config = config or ExtractSegmentsConfig()
    
    def execute(self, user_query: str) -> SearchResult:
        """
        メイン実行フロー
        
        Args:
            user_query: ユーザーの検索クエリ
        
        Returns:
            SearchResult: 抽出されたセグメントのリスト
        """
        import time
        start_time = time.time()
        
        # Phase 1: クエリ変換
        search_query = self.llm_client.convert_to_search_query(user_query)
        
        # Phase 2: YouTube検索
        videos = self.youtube_searcher.search(
            query=search_query,
            max_results=self.config.max_search_results
        )
        
        if not videos:
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time
            )
        
        # Phase 3: 字幕取得 & 粗い範囲特定（並列処理）
        candidates = self._process_videos_parallel(videos, user_query)
        
        # 上位N件に絞り込み
        candidates = sorted(
            candidates, 
            key=lambda x: x[2],  # confidence
            reverse=True
        )[:self.config.max_final_results]
        
        # Phase 4: 精密時刻特定（VLM使用）
        if self.config.enable_vlm_refinement:
            segments = self._refine_with_vlm(candidates, user_query)
        else:
            # VLMスキップ時は字幕ベースの結果をそのまま使用
            segments = [
                VideoSegment(
                    video=video,
                    time_range=time_range,
                    summary=summary,
                    confidence=confidence
                )
                for video, time_range, confidence, summary in candidates
            ]
        
        processing_time = time.time() - start_time
        
        return SearchResult(
            query=user_query,
            segments=segments,
            processing_time_sec=processing_time
        )
    
    def _process_videos_parallel(
        self, 
        videos: list[Video],
        user_query: str
    ) -> list[tuple[Video, TimeRange, float, str]]:
        """
        複数動画を並列処理して候補を抽出
        
        Returns:
            [(Video, TimeRange, confidence, summary), ...]
        """
        candidates = []
        
        # ThreadPoolExecutorで並列処理
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    self._process_single_video, 
                    video, 
                    user_query
                ): video
                for video in videos
            }
            
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    if result:
                        candidates.extend(result)
                except Exception as e:
                    # 個別の動画処理失敗は無視して続行
                    print(f"Error processing video: {e}")
                    continue
        
        return candidates
    
    def _process_single_video(
        self, 
        video: Video,
        user_query: str
    ) -> list[tuple[Video, TimeRange, float, str]]:
        """
        単一動画の処理: 字幕取得 → 範囲特定
        """
        # 字幕取得
        subtitle = self.subtitle_fetcher.fetch(video.video_id)
        if not subtitle:
            return []
        
        # LLMで粗い範囲特定
        ranges = self.llm_client.find_relevant_ranges(
            subtitle_text=subtitle.full_text,
            subtitle_chunks=subtitle.chunks,
            user_query=user_query
        )
        
        # 確信度フィルタ
        results = [
            (video, time_range, confidence, summary)
            for time_range, confidence, summary in ranges
            if confidence >= self.config.min_confidence
        ]
        
        return results
    
    def _refine_with_vlm(
        self,
        candidates: list[tuple[Video, TimeRange, float, str]],
        user_query: str
    ) -> list[VideoSegment]:
        """
        VLMで精密な時刻を特定
        """
        segments = []
        
        for video, estimated_range, _, _ in candidates:
            try:
                # バッファ追加
                buffered_range = estimated_range.with_buffer(
                    self.config.buffer_ratio
                )
                
                # 一時ファイルに部分ダウンロード
                with tempfile.NamedTemporaryFile(
                    suffix=".mp4", 
                    delete=False
                ) as tmp:
                    clip_path = tmp.name
                
                self.video_extractor.extract_clip(
                    video_url=video.url,
                    time_range=buffered_range,
                    output_path=clip_path
                )
                
                # VLMで精密分析
                relative_range, confidence, summary = \
                    self.vlm_client.analyze_video_clip(
                        video_path=clip_path,
                        user_query=user_query
                    )
                
                # 相対時間 → 絶対時間
                absolute_range = convert_relative_to_absolute(
                    clip_start_sec=buffered_range.start_sec,
                    relative_range=relative_range
                )
                
                segments.append(VideoSegment(
                    video=video,
                    time_range=absolute_range,
                    summary=summary,
                    confidence=confidence
                ))
                
            except Exception as e:
                print(f"Error refining video {video.video_id}: {e}")
                # VLM失敗時は元の推定範囲を使用
                segments.append(VideoSegment(
                    video=video,
                    time_range=estimated_range,
                    summary="（精密分析失敗）",
                    confidence=0.5
                ))
            
            finally:
                # 一時ファイル削除
                try:
                    Path(clip_path).unlink()
                except:
                    pass
        
        return segments
```

---

## 7. UI仕様（Streamlit）

### 7.1 画面構成

```
┌─────────────────────────────────────────────────────────────┐
│  🎯 PinPoint.video                                          │
│  YouTube動画からピンポイントで情報を抽出                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🔍 何を知りたいですか？                              │   │
│  │ ┌─────────────────────────────────────────────────┐ │   │
│  │ │ Claude Codeのultrathinkの使い方                 │ │   │
│  │ └─────────────────────────────────────────────────┘ │   │
│  │                                    [🔎 検索]        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ⏳ 処理中... 字幕を分析しています (3/5)                    │
│  ████████████░░░░░░░░ 60%                                   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  📊 検索結果 (3件, 処理時間: 45秒)                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1️⃣ Claude Code Tutorial - Advanced Features         │   │
│  │    📺 TechChannel | ⏱️ 15:00 - 18:09               │   │
│  │    ────────────────────────────────────────────     │   │
│  │    │  [YouTube Player Embed (start=900, end=1089)]│   │
│  │    ────────────────────────────────────────────     │   │
│  │    💡 ultrathinkモードの有効化方法と、実際の        │   │
│  │       使用例を説明しています。                      │   │
│  │    🔗 元動画を開く | 📋 リンクをコピー              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 2️⃣ Getting Started with Claude Code                 │   │
│  │    ...                                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 実装

```python
# app/main.py
import streamlit as st
import streamlit.components.v1 as components
from src.application.usecases.extract_segments import (
    ExtractSegmentsUseCase,
    ExtractSegmentsConfig
)
from src.infrastructure.youtube_data_api import YouTubeDataAPIClient
from src.infrastructure.youtube_transcript import YouTubeTranscriptClient
from src.infrastructure.gemini_llm_client import GeminiLLMClient
from src.infrastructure.ytdlp_extractor import YtdlpVideoExtractor
from src.infrastructure.gemini_vlm_client import GeminiVLMClient
from config.settings import Settings


def init_usecase() -> ExtractSegmentsUseCase:
    """
    DIでユースケースを組み立て
    
    環境変数:
        YOUTUBE_API_KEY: YouTube Data API キー
        GEMINI_API_KEY: Gemini API キー（google-genaiが自動取得）
    """
    settings = Settings()
    
    return ExtractSegmentsUseCase(
        youtube_searcher=YouTubeDataAPIClient(settings.YOUTUBE_API_KEY),
        subtitle_fetcher=YouTubeTranscriptClient(),  # インスタンス化が必要（v1.0+）
        llm_client=GeminiLLMClient(),   # api_key不要（環境変数から自動取得）
        video_extractor=YtdlpVideoExtractor(),
        vlm_client=GeminiVLMClient(),   # api_key不要（環境変数から自動取得）
        config=ExtractSegmentsConfig(
            max_search_results=10,
            max_final_results=5,
            buffer_ratio=0.2,
            enable_vlm_refinement=True
        )
    )


def render_youtube_embed(video_id: str, start_sec: int, end_sec: int):
    """タイムスタンプ付きYouTube埋め込み"""
    embed_url = f"https://www.youtube.com/embed/{video_id}?start={start_sec}&end={end_sec}"
    components.iframe(embed_url, height=315, width=560)


def main():
    st.set_page_config(
        page_title="PinPoint.video",
        page_icon="🎯",
        layout="wide"
    )
    
    st.title("🎯 PinPoint.video")
    st.markdown("YouTube動画からピンポイントで情報を抽出")
    
    # 検索フォーム
    with st.form("search_form"):
        query = st.text_input(
            "🔍 何を知りたいですか？",
            placeholder="例: Claude Codeのultrathinkの使い方"
        )
        submitted = st.form_submit_button("🔎 検索")
    
    if submitted and query:
        usecase = init_usecase()
        
        # プログレス表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("⏳ YouTube動画を検索中...")
        progress_bar.progress(10)
        
        # 実行
        result = usecase.execute(query)
        
        progress_bar.progress(100)
        status_text.text(f"✅ 完了 (処理時間: {result.processing_time_sec:.1f}秒)")
        
        # 結果表示
        if not result.segments:
            st.warning("該当する動画が見つかりませんでした。")
        else:
            st.success(f"📊 {len(result.segments)}件のセグメントが見つかりました")
            
            for i, segment in enumerate(result.segments, 1):
                with st.expander(
                    f"{i}️⃣ {segment.video.title}",
                    expanded=(i == 1)
                ):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        # YouTube埋め込み
                        params = segment.time_range.to_youtube_embed_params()
                        render_youtube_embed(
                            video_id=segment.video.video_id,
                            start_sec=params["start"],
                            end_sec=params["end"]
                        )
                    
                    with col2:
                        st.markdown(f"**📺 {segment.video.channel_name}**")
                        
                        start_min = int(segment.time_range.start_sec // 60)
                        start_sec = int(segment.time_range.start_sec % 60)
                        end_min = int(segment.time_range.end_sec // 60)
                        end_sec = int(segment.time_range.end_sec % 60)
                        
                        st.markdown(
                            f"**⏱️ {start_min}:{start_sec:02d} - {end_min}:{end_sec:02d}**"
                        )
                        st.markdown(f"**🎯 確信度: {segment.confidence:.0%}**")
                    
                    st.markdown("---")
                    st.markdown(f"💡 {segment.summary}")
                    
                    # リンク
                    col_a, col_b = st.columns(2)
                    with col_a:
                        full_url = (
                            f"https://youtube.com/watch?v={segment.video.video_id}"
                            f"&t={params['start']}"
                        )
                        st.link_button("🔗 元動画を開く", full_url)
                    
                    with col_b:
                        embed_url = segment.embed_url
                        if st.button(f"📋 リンクをコピー", key=f"copy_{i}"):
                            st.code(embed_url)


if __name__ == "__main__":
    main()
```

---

## 8. 設定・環境変数

### 8.1 設定ファイル

```python
# config/settings.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # API Keys
    YOUTUBE_API_KEY: str
    GEMINI_API_KEY: str
    
    # Processing
    MAX_SEARCH_RESULTS: int = 10
    MAX_FINAL_RESULTS: int = 5
    BUFFER_RATIO: float = 0.2
    ENABLE_VLM_REFINEMENT: bool = True
    
    # Timeouts
    YOUTUBE_SEARCH_TIMEOUT: int = 10
    SUBTITLE_FETCH_TIMEOUT: int = 10
    CLIP_EXTRACT_TIMEOUT: int = 120
    VLM_ANALYSIS_TIMEOUT: int = 60
    
    # Paths
    TEMP_DIR: str = "/tmp/pinpoint_video"
    FFMPEG_PATH: str = "ffmpeg"
    YTDLP_PATH: str = "yt-dlp"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 8.2 環境変数テンプレート

```bash
# .env.example
YOUTUBE_API_KEY=your_youtube_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Optional overrides
MAX_SEARCH_RESULTS=10
MAX_FINAL_RESULTS=5
BUFFER_RATIO=0.2
ENABLE_VLM_REFINEMENT=true
```

---

## 9. 依存パッケージ

### 9.1 requirements.txt

```
# Web Framework
streamlit>=1.30.0

# YouTube
google-api-python-client>=2.100.0
youtube-transcript-api>=1.2.0   # ⚠️ v1.0.0でAPI破壊的変更あり
yt-dlp>=2025.12.0               # ⚠️ 最新版推奨（yt-dlp-ejs依存）

# AI/ML
google-genai>=1.0.0             # ⚠️ 新SDK（google-generativeaiは非推奨）

# Settings
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0

# Utilities
httpx>=0.25.0
tenacity>=8.2.0  # リトライ処理
```

### 9.2 システム依存

```bash
# ffmpeg（動画処理に必須）
sudo apt-get install ffmpeg

# または Homebrew (macOS)
brew install ffmpeg

# yt-dlp の JavaScript runtime（deno推奨）
# YouTube n/sig値の復号に必要
curl -fsSL https://deno.land/install.sh | sh
# または: brew install deno / npm install -g deno
```

### 9.3 ⚠️ ライブラリ移行に関する注意

| 旧ライブラリ | 新ライブラリ | 備考 |
|-------------|-------------|------|
| `google-generativeai` | `google-genai` | 2025/11/30でサポート終了 |
| youtube-transcript-api < 1.0 | >= 1.2.0 | APIが完全に変更 |

---

## 10. エラーハンドリング

### 10.1 例外定義

```python
# src/domain/exceptions.py

class PinPointVideoError(Exception):
    """基底例外クラス"""
    pass


class YouTubeSearchError(PinPointVideoError):
    """YouTube検索エラー"""
    pass


class SubtitleNotFoundError(PinPointVideoError):
    """字幕が見つからない"""
    pass


class VideoExtractionError(PinPointVideoError):
    """動画クリップ抽出エラー"""
    pass


class LLMError(PinPointVideoError):
    """LLM API エラー"""
    pass


class VLMError(PinPointVideoError):
    """VLM API エラー"""
    pass


class TimeoutError(PinPointVideoError):
    """タイムアウト"""
    pass
```

### 10.2 リトライ戦略

```python
# src/infrastructure/retry.py
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import httpx

# API呼び出し用デコレータ
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, TimeoutError))
)
```

---

## 11. テスト戦略

### 11.1 ユニットテスト

```python
# tests/unit/test_entities.py
import pytest
from src.domain.entities import TimeRange

class TestTimeRange:
    def test_duration(self):
        tr = TimeRange(start_sec=100, end_sec=200)
        assert tr.duration_sec == 100
    
    def test_with_buffer(self):
        tr = TimeRange(start_sec=100, end_sec=200)
        buffered = tr.with_buffer(0.2)
        assert buffered.start_sec == 80  # 100 - 20
        assert buffered.end_sec == 220   # 200 + 20
    
    def test_buffer_not_negative(self):
        tr = TimeRange(start_sec=10, end_sec=50)
        buffered = tr.with_buffer(0.5)
        assert buffered.start_sec == 0  # max(0, 10-20)
    
    def test_invalid_range(self):
        with pytest.raises(ValueError):
            TimeRange(start_sec=200, end_sec=100)
```

### 11.2 インテグレーションテスト

```python
# tests/integration/test_usecase.py
import pytest
from src.application.usecases.extract_segments import (
    ExtractSegmentsUseCase,
    ExtractSegmentsConfig
)

# モック実装を注入してテスト
class MockYouTubeSearcher:
    def search(self, query, **kwargs):
        return [...]  # テスト用データ

class MockSubtitleFetcher:
    def fetch(self, video_id, **kwargs):
        return ...  # テスト用データ

# ...
```

---

## 12. デプロイ

### 12.1 ローカル実行

```bash
# 環境構築
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .env を編集してAPIキーを設定

# 実行
streamlit run app/main.py
```

### 12.2 Streamlit Cloud（将来）

```yaml
# .streamlit/config.toml
[theme]
primaryColor = "#FF4B4B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"
```

---

## 13. 制限事項・既知の課題

### 13.1 現行の制限

| 制限 | 詳細 | 将来的な対応 |
|------|------|-------------|
| 字幕なし動画 | 処理不可 | Whisper統合 |
| 動画長上限 | gemini-2.5-flash: 1時間（1Mコンテキスト） | gemini-2.5-pro（2M）で2時間 |
| 並列処理数 | 5動画まで | キュー管理 |
| 言語 | 日本語・英語のみ | 多言語対応 |

### 13.2 既知の課題

1. **キーフレーム問題**: ffmpegのシークはキーフレーム単位のため、±数秒のズレが発生する可能性
2. **字幕の品質**: 自動生成字幕は誤認識が含まれる場合がある
3. **API制限**: YouTube Data API の日次クォータ制限（10,000ユニット/日）
4. **IPブロック**: youtube-transcript-api でIPブロックされる可能性（Webshareプロキシで対応可）

### 13.3 ライブラリ更新に関する注意

| ライブラリ | 注意点 |
|-----------|--------|
| youtube-transcript-api | v1.0.0でAPI破壊的変更。旧コードは動作しない |
| google-generativeai | 2025/11/30でサポート終了。google-genai に移行必須 |
| yt-dlp | yt-dlp-ejs と JavaScript runtime が必要 |

---

## 14. 開発ロードマップ

### 14.1 MVP（ハッカソン当日）

- [x] 基本的な検索 → 字幕分析 → セグメント抽出フロー
- [x] 部分ダウンロード機能
- [x] VLM精密化
- [x] Streamlit UI

### 14.2 将来拡張（ハッカソン後）

- [ ] Whisper統合（字幕なし動画対応）
- [ ] バッチ処理（複数クエリ一括）
- [ ] 結果キャッシュ
- [ ] ユーザー認証
- [ ] API公開

---

## 付録

### A. YouTube URL クエリパラメータ

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| `t` | 開始秒数 | `?t=120` (2分から開始) |
| `start` | 埋め込み開始秒 | `?start=120` |
| `end` | 埋め込み終了秒 | `?end=180` |

### B. ffmpeg コマンド解説

```bash
ffmpeg \
  -ss 00:15:00 \     # 入力のシーク位置（Range Requestで高速）
  -i VIDEO_URL \     # video stream
  -ss 00:15:00 \     # audio も同位置にシーク
  -i AUDIO_URL \     # audio stream
  -t 00:04:00 \      # 切り出し長さ
  -map 0:v \         # 1つ目の入力からvideo
  -map 1:a \         # 2つ目の入力からaudio
  -c:v libx264 \     # video codec
  -c:a aac \         # audio codec
  -movflags +faststart \  # Web再生用最適化
  output.mp4
```

### C. Gemini モデル選択ガイド

| モデル | 用途 | 特徴 |
|--------|------|------|
| gemini-2.5-flash | テキスト処理・動画分析 | 高速、低コスト、動画対応 |
| gemini-2.5-pro | 複雑な分析 | 高精度、2Mコンテキスト |

### D. SDK移行ガイド

#### 旧SDK → 新SDK 対応表

| 旧 (google-generativeai) | 新 (google-genai) |
|--------------------------|-------------------|
| `import google.generativeai as genai` | `from google import genai` |
| `genai.configure(api_key=...)` | `client = genai.Client(api_key=...)` |
| `genai.GenerativeModel("model")` | `client.models.generate_content(model="model", ...)` |
| `model.generate_content(prompt)` | `client.models.generate_content(model=..., contents=...)` |
| `genai.upload_file(path)` | `client.files.upload(file=path)` |
| `genai.delete_file(name)` | `client.files.delete(name=name)` |

#### 環境変数

```bash
# 新SDKは環境変数から自動でAPIキーを取得
export GEMINI_API_KEY=your_api_key
# または
export GOOGLE_API_KEY=your_api_key
```

---

*最終更新: 2026-01-10*
*バージョン: 1.1.0*
*変更履歴: youtube-transcript-api v1.2+, google-genai SDK対応*
