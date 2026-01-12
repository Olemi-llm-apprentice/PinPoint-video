"""セッション履歴の永続化ストレージ"""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.entities import SearchResult, TimeRange, Video, VideoSegment
from src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

# デフォルトの出力ディレクトリ
DEFAULT_OUTPUT_DIR = Path("outputs")


@dataclass
class SessionMetadata:
    """セッションのメタデータ"""

    session_id: str
    query: str
    created_at: str  # ISO format
    segment_count: int
    processing_time_sec: float
    vlm_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "created_at": self.created_at,
            "segment_count": self.segment_count,
            "processing_time_sec": self.processing_time_sec,
            "vlm_enabled": self.vlm_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        return cls(
            session_id=data["session_id"],
            query=data["query"],
            created_at=data["created_at"],
            segment_count=data["segment_count"],
            processing_time_sec=data["processing_time_sec"],
            vlm_enabled=data.get("vlm_enabled", True),
        )


def _video_to_dict(video: Video) -> dict[str, Any]:
    """VideoをJSON化"""
    return {
        "video_id": video.video_id,
        "title": video.title,
        "channel_name": video.channel_name,
        "duration_sec": video.duration_sec,
        "published_at": video.published_at,
        "thumbnail_url": video.thumbnail_url,
    }


def _video_from_dict(data: dict[str, Any]) -> Video:
    """JSONからVideoを復元"""
    return Video(
        video_id=data["video_id"],
        title=data["title"],
        channel_name=data["channel_name"],
        duration_sec=data["duration_sec"],
        published_at=data["published_at"],
        thumbnail_url=data["thumbnail_url"],
    )


def _time_range_to_dict(tr: TimeRange) -> dict[str, float]:
    """TimeRangeをJSON化"""
    return {
        "start_sec": tr.start_sec,
        "end_sec": tr.end_sec,
    }


def _time_range_from_dict(data: dict[str, float]) -> TimeRange:
    """JSONからTimeRangeを復元"""
    return TimeRange(
        start_sec=data["start_sec"],
        end_sec=data["end_sec"],
    )


def _segment_to_dict(segment: VideoSegment) -> dict[str, Any]:
    """VideoSegmentをJSON化"""
    return {
        "video": _video_to_dict(segment.video),
        "time_range": _time_range_to_dict(segment.time_range),
        "summary": segment.summary,
        "confidence": segment.confidence,
    }


def _segment_from_dict(data: dict[str, Any]) -> VideoSegment:
    """JSONからVideoSegmentを復元"""
    return VideoSegment(
        video=_video_from_dict(data["video"]),
        time_range=_time_range_from_dict(data["time_range"]),
        summary=data["summary"],
        confidence=data["confidence"],
    )


def search_result_to_dict(result: SearchResult) -> dict[str, Any]:
    """SearchResultをJSON化"""
    return {
        "query": result.query,
        "segments": [_segment_to_dict(s) for s in result.segments],
        "processing_time_sec": result.processing_time_sec,
    }


def search_result_from_dict(data: dict[str, Any]) -> SearchResult:
    """JSONからSearchResultを復元"""
    return SearchResult(
        query=data["query"],
        segments=[_segment_from_dict(s) for s in data["segments"]],
        processing_time_sec=data["processing_time_sec"],
    )


def generate_result_markdown(result: SearchResult, metadata: SessionMetadata) -> str:
    """検索結果をMarkdown形式で出力"""
    lines = [
        f"# PinPoint.video 検索結果",
        f"",
        f"**検索クエリ:** {result.query}",
        f"",
        f"**実行日時:** {metadata.created_at}",
        f"**処理時間:** {result.processing_time_sec:.1f}秒",
        f"**VLM精密分析:** {'有効' if metadata.vlm_enabled else '無効'}",
        f"",
        f"---",
        f"",
        f"## 検索結果: {len(result.segments)}件",
        f"",
    ]

    for i, segment in enumerate(result.segments, 1):
        start_min = int(segment.time_range.start_sec // 60)
        start_sec = int(segment.time_range.start_sec % 60)
        end_min = int(segment.time_range.end_sec // 60)
        end_sec = int(segment.time_range.end_sec % 60)

        lines.extend([
            f"### {i}. {segment.video.title}",
            f"",
            f"- **チャンネル:** {segment.video.channel_name}",
            f"- **時間範囲:** {start_min}:{start_sec:02d} - {end_min}:{end_sec:02d}",
            f"- **確信度:** {segment.confidence:.0%}",
            f"- **要約:** {segment.summary}",
            f"",
            f"**リンク:**",
            f"- [元動画を開く](https://youtube.com/watch?v={segment.video.video_id}&t={int(segment.time_range.start_sec)})",
            f"- 埋め込みURL: `{segment.embed_url}`",
            f"",
        ])

    return "\n".join(lines)


class SessionStorage:
    """セッション履歴を管理するストレージ"""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"SessionStorage initialized: {self.output_dir}")

    def _generate_session_id(self, query: str) -> str:
        """セッションIDを生成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # クエリの最初の20文字をサニタイズして使用
        safe_query = "".join(c if c.isalnum() else "_" for c in query[:20])
        return f"{timestamp}_{safe_query}"

    def _get_session_dir(self, session_id: str) -> Path:
        """セッションのディレクトリパスを取得"""
        return self.output_dir / session_id

    def save_session(
        self,
        result: SearchResult,
        vlm_enabled: bool,
        logs: list[str] | None = None,
        search_queries: dict[str, str] | None = None,
        search_videos: list[Video] | None = None,
        search_stats: dict[str, Any] | None = None,
    ) -> str:
        """
        セッションを保存

        Args:
            result: 検索結果
            vlm_enabled: VLM精密分析が有効だったか
            logs: 処理ログのリスト
            search_queries: 生成された検索クエリ {"original": ..., "optimized": ..., "simplified": ...}
            search_videos: 検索でヒットした全動画リスト
            search_stats: 検索統計情報

        Returns:
            セッションID
        """
        session_id = self._generate_session_id(result.query)
        session_dir = self._get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # メタデータ
        metadata = SessionMetadata(
            session_id=session_id,
            query=result.query,
            created_at=datetime.now().isoformat(),
            segment_count=len(result.segments),
            processing_time_sec=result.processing_time_sec,
            vlm_enabled=vlm_enabled,
        )

        # metadata.json
        with open(session_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, ensure_ascii=False, indent=2)

        # result.json
        with open(session_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(search_result_to_dict(result), f, ensure_ascii=False, indent=2)

        # result.md
        markdown_content = generate_result_markdown(result, metadata)
        with open(session_dir / "result.md", "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # log.txt
        if logs:
            with open(session_dir / "log.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(logs))

        # queries.json - 生成された検索クエリ
        if search_queries:
            with open(session_dir / "queries.json", "w", encoding="utf-8") as f:
                json.dump(search_queries, f, ensure_ascii=False, indent=2)

        # videos.json - 検索でヒットした全動画
        if search_videos:
            videos_data = {
                "count": len(search_videos),
                "stats": search_stats or {},
                "videos": [_video_to_dict(v) for v in search_videos],
            }
            with open(session_dir / "videos.json", "w", encoding="utf-8") as f:
                json.dump(videos_data, f, ensure_ascii=False, indent=2)

        # clipsディレクトリを作成
        clips_dir = session_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        # subtitlesディレクトリを作成
        subtitles_dir = session_dir / "subtitles"
        subtitles_dir.mkdir(exist_ok=True)

        logger.info(f"Session saved: {session_id}")
        return session_id

    def save_subtitle(
        self,
        session_id: str,
        video_id: str,
        subtitle_data: dict[str, Any],
    ) -> bool:
        """
        字幕データをセッションに保存

        Args:
            session_id: セッションID
            video_id: 動画ID
            subtitle_data: 字幕データ（language, chunks等）

        Returns:
            成功したかどうか
        """
        session_dir = self._get_session_dir(session_id)
        subtitles_dir = session_dir / "subtitles"
        subtitles_dir.mkdir(exist_ok=True)

        try:
            with open(subtitles_dir / f"{video_id}.json", "w", encoding="utf-8") as f:
                json.dump(subtitle_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Subtitle saved: {video_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save subtitle: {video_id} - {e}")
            return False

    def get_session_subtitles(self, session_id: str) -> dict[str, dict[str, Any]]:
        """セッションの字幕データを取得"""
        subtitles_dir = self._get_session_dir(session_id) / "subtitles"
        if not subtitles_dir.exists():
            return {}

        subtitles = {}
        for subtitle_file in subtitles_dir.glob("*.json"):
            video_id = subtitle_file.stem
            try:
                with open(subtitle_file, encoding="utf-8") as f:
                    subtitles[video_id] = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load subtitle: {subtitle_file} - {e}")

        return subtitles

    def get_session_queries(self, session_id: str) -> dict[str, str] | None:
        """セッションの検索クエリを取得"""
        queries_path = self._get_session_dir(session_id) / "queries.json"
        if not queries_path.exists():
            return None
        with open(queries_path, encoding="utf-8") as f:
            return json.load(f)

    def get_session_videos(self, session_id: str) -> dict[str, Any] | None:
        """セッションの検索動画一覧を取得"""
        videos_path = self._get_session_dir(session_id) / "videos.json"
        if not videos_path.exists():
            return None
        with open(videos_path, encoding="utf-8") as f:
            return json.load(f)

    def save_clip(
        self,
        session_id: str,
        video_id: str,
        clip_path: Path,
        segment_index: int | None = None,
    ) -> Path | None:
        """
        動画クリップをセッションに保存

        Args:
            session_id: セッションID
            video_id: 動画ID
            clip_path: 元のクリップファイルパス
            segment_index: セグメント番号（同一動画で複数セグメントがある場合）

        Returns:
            保存先のパス（失敗時はNone）
        """
        session_dir = self._get_session_dir(session_id)
        clips_dir = session_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        # セグメント番号がある場合はファイル名に含める
        if segment_index is not None:
            dest_path = clips_dir / f"{video_id}_seg{segment_index}.mp4"
        else:
            dest_path = clips_dir / f"{video_id}.mp4"
        try:
            shutil.copy2(clip_path, dest_path)
            logger.debug(f"Clip saved: {dest_path}")
            return dest_path
        except Exception as e:
            logger.error(f"Failed to save clip: {e}")
            return None

    def save_integrated_summary(
        self,
        session_id: str,
        summary: str,
    ) -> bool:
        """
        統合サマリーをセッションに保存

        Args:
            session_id: セッションID
            summary: 統合サマリーテキスト

        Returns:
            成功したかどうか
        """
        session_dir = self._get_session_dir(session_id)
        summary_path = session_dir / "integrated_summary.txt"

        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            logger.debug(f"Integrated summary saved: {summary_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save integrated summary: {e}")
            return False

    def get_integrated_summary(self, session_id: str) -> str | None:
        """セッションの統合サマリーを取得"""
        summary_path = self._get_session_dir(session_id) / "integrated_summary.txt"
        if not summary_path.exists():
            return None
        with open(summary_path, encoding="utf-8") as f:
            return f.read()

    def save_final_clip(
        self,
        session_id: str,
        clip_path: Path,
    ) -> Path | None:
        """
        結合された最終クリップをセッションに保存

        Args:
            session_id: セッションID
            clip_path: 元のクリップファイルパス

        Returns:
            保存先のパス（失敗時はNone）
        """
        session_dir = self._get_session_dir(session_id)
        dest_path = session_dir / "final_clip.mp4"

        try:
            shutil.copy2(clip_path, dest_path)
            logger.info(f"Final clip saved: {dest_path}")
            return dest_path
        except Exception as e:
            logger.error(f"Failed to save final clip: {e}")
            return None

    def get_final_clip(self, session_id: str) -> Path | None:
        """セッションの最終クリップパスを取得"""
        final_clip_path = self._get_session_dir(session_id) / "final_clip.mp4"
        if not final_clip_path.exists():
            return None
        return final_clip_path

    def list_sessions(self, limit: int = 50) -> list[SessionMetadata]:
        """
        セッション一覧を取得（新しい順）

        Args:
            limit: 最大取得件数

        Returns:
            セッションメタデータのリスト
        """
        sessions = []
        
        if not self.output_dir.exists():
            return sessions

        # ディレクトリを新しい順にソート
        session_dirs = sorted(
            [d for d in self.output_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )

        for session_dir in session_dirs[:limit]:
            metadata_path = session_dir / "metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path, encoding="utf-8") as f:
                        data = json.load(f)
                    sessions.append(SessionMetadata.from_dict(data))
                except Exception as e:
                    logger.warning(f"Failed to load session metadata: {session_dir} - {e}")

        return sessions

    def load_session(self, session_id: str) -> tuple[SessionMetadata, SearchResult] | None:
        """
        セッションを読み込む

        Args:
            session_id: セッションID

        Returns:
            (メタデータ, 検索結果) または None
        """
        session_dir = self._get_session_dir(session_id)
        
        if not session_dir.exists():
            logger.warning(f"Session not found: {session_id}")
            return None

        try:
            # メタデータ読み込み
            with open(session_dir / "metadata.json", encoding="utf-8") as f:
                metadata = SessionMetadata.from_dict(json.load(f))

            # 結果読み込み
            with open(session_dir / "result.json", encoding="utf-8") as f:
                result = search_result_from_dict(json.load(f))

            return metadata, result
        except Exception as e:
            logger.error(f"Failed to load session: {session_id} - {e}")
            return None

    def get_session_clips(self, session_id: str) -> list[Path]:
        """セッションのクリップファイル一覧を取得"""
        clips_dir = self._get_session_dir(session_id) / "clips"
        if not clips_dir.exists():
            return []
        return list(clips_dir.glob("*.mp4"))

    def get_session_log(self, session_id: str) -> str | None:
        """セッションのログを取得"""
        log_path = self._get_session_dir(session_id) / "log.txt"
        if not log_path.exists():
            return None
        with open(log_path, encoding="utf-8") as f:
            return f.read()

    def delete_session(self, session_id: str) -> bool:
        """セッションを削除"""
        session_dir = self._get_session_dir(session_id)
        if not session_dir.exists():
            return False
        try:
            shutil.rmtree(session_dir)
            logger.info(f"Session deleted: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session: {session_id} - {e}")
            return False

    def save_generated_image(
        self,
        session_id: str,
        image_type: str,
        image_data: bytes,
        prompt: str | None = None,
    ) -> Path | None:
        """
        生成された画像をセッションに保存

        Args:
            session_id: セッションID
            image_type: 画像タイプ（"infographic" または "manga"）
            image_data: 画像のバイトデータ
            prompt: 生成に使用したプロンプト（漫画の場合）

        Returns:
            保存先のパス（失敗時はNone）
        """
        session_dir = self._get_session_dir(session_id)
        images_dir = session_dir / "generated_images"
        images_dir.mkdir(exist_ok=True)

        # 画像を保存
        image_path = images_dir / f"{image_type}.png"
        try:
            with open(image_path, "wb") as f:
                f.write(image_data)
            logger.info(f"Generated image saved: {image_path}")

            # プロンプトがあれば保存
            if prompt:
                prompt_path = images_dir / f"{image_type}_prompt.txt"
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(prompt)
                logger.debug(f"Prompt saved: {prompt_path}")

            return image_path
        except Exception as e:
            logger.error(f"Failed to save generated image: {e}")
            return None

    def get_generated_image(
        self,
        session_id: str,
        image_type: str,
    ) -> tuple[Path | None, str | None]:
        """
        セッションの生成画像を取得

        Args:
            session_id: セッションID
            image_type: 画像タイプ（"infographic" または "manga"）

        Returns:
            (画像パス, プロンプト) のタプル
        """
        session_dir = self._get_session_dir(session_id)
        images_dir = session_dir / "generated_images"

        image_path = images_dir / f"{image_type}.png"
        prompt_path = images_dir / f"{image_type}_prompt.txt"

        result_image = image_path if image_path.exists() else None
        result_prompt = None
        if prompt_path.exists():
            try:
                with open(prompt_path, encoding="utf-8") as f:
                    result_prompt = f.read()
            except Exception:
                pass

        return result_image, result_prompt

    def get_all_generated_images(self, session_id: str) -> dict[str, tuple[Path | None, str | None]]:
        """
        セッションの全生成画像を取得

        Returns:
            {"infographic": (path, prompt), "manga": (path, prompt)} の辞書
        """
        return {
            "infographic": self.get_generated_image(session_id, "infographic"),
            "manga": self.get_generated_image(session_id, "manga"),
        }
