"""メインユースケース: ユーザークエリから関連動画セグメントを抽出"""

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from src.application.interfaces.llm_client import LLMClient
from src.application.interfaces.subtitle_fetcher import SubtitleFetcher
from src.application.interfaces.video_extractor import VideoExtractor
from src.application.interfaces.vlm_client import VLMClient
from src.application.interfaces.youtube_searcher import YouTubeSearcher
from src.domain.entities import (
    SearchResult,
    TimeRange,
    Video,
    VideoSegment,
)
from src.domain.time_utils import convert_relative_to_absolute


@dataclass
class ExtractSegmentsConfig:
    """ユースケースの設定"""

    max_search_results: int = 30
    max_final_results: int = 5
    buffer_ratio: float = 0.2  # バッファ割合（20%）
    min_confidence: float = 0.3  # 最低確信度
    enable_vlm_refinement: bool = True  # VLM精密化を有効にするか
    duration_min_sec: int = 60  # 最小動画長（秒）
    duration_max_sec: int = 7200  # 最大動画長（秒）= 2時間


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
        config: ExtractSegmentsConfig | None = None,
    ):
        self.youtube_searcher = youtube_searcher
        self.subtitle_fetcher = subtitle_fetcher
        self.llm_client = llm_client
        self.video_extractor = video_extractor
        self.vlm_client = vlm_client
        self.config = config or ExtractSegmentsConfig()

    def execute(
        self,
        user_query: str,
        progress_callback: callable | None = None,
    ) -> SearchResult:
        """
        メイン実行フロー

        Args:
            user_query: ユーザーの検索クエリ
            progress_callback: 進捗コールバック (stage: str, progress: float)

        Returns:
            SearchResult: 抽出されたセグメントのリスト
        """
        start_time = time.time()

        def update_progress(stage: str, progress: float) -> None:
            if progress_callback:
                progress_callback(stage, progress)

        # Phase 1: クエリ変換
        update_progress("クエリを最適化中...", 0.1)
        search_query = self.llm_client.convert_to_search_query(user_query)

        # Phase 2: YouTube検索
        update_progress("YouTube動画を検索中...", 0.2)
        videos = self.youtube_searcher.search(
            query=search_query,
            max_results=self.config.max_search_results,
            duration_min_sec=self.config.duration_min_sec,
            duration_max_sec=self.config.duration_max_sec,
        )

        if not videos:
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time,
            )

        # Phase 3: 字幕取得 & 粗い範囲特定（並列処理）
        update_progress("字幕を分析中...", 0.4)
        candidates = self._process_videos_parallel(videos, user_query)

        # 上位N件に絞り込み
        candidates = sorted(
            candidates,
            key=lambda x: x[2],  # confidence
            reverse=True,
        )[: self.config.max_final_results]

        # Phase 4: 精密時刻特定（VLM使用）
        if self.config.enable_vlm_refinement and candidates:
            update_progress("動画を精密分析中...", 0.6)
            segments = self._refine_with_vlm(candidates, user_query, update_progress)
        else:
            # VLMスキップ時は字幕ベースの結果をそのまま使用
            segments = [
                VideoSegment(
                    video=video,
                    time_range=time_range,
                    summary=summary,
                    confidence=confidence,
                )
                for video, time_range, confidence, summary in candidates
            ]

        processing_time = time.time() - start_time
        update_progress("完了", 1.0)

        return SearchResult(
            query=user_query,
            segments=segments,
            processing_time_sec=processing_time,
        )

    def _process_videos_parallel(
        self,
        videos: list[Video],
        user_query: str,
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
                    user_query,
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
        user_query: str,
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
            user_query=user_query,
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
        user_query: str,
        update_progress: callable,
    ) -> list[VideoSegment]:
        """
        VLMで精密な時刻を特定
        """
        segments = []
        total = len(candidates)

        for i, (video, estimated_range, _, _) in enumerate(candidates):
            clip_path = None
            try:
                # 進捗更新
                progress = 0.6 + (0.3 * (i / total))
                update_progress(
                    f"動画を精密分析中... ({i + 1}/{total})",
                    progress,
                )

                # バッファ追加
                buffered_range = estimated_range.with_buffer(self.config.buffer_ratio)

                # 一時ファイルに部分ダウンロード
                with tempfile.NamedTemporaryFile(
                    suffix=".mp4",
                    delete=False,
                ) as tmp:
                    clip_path = tmp.name

                self.video_extractor.extract_clip(
                    video_url=video.url,
                    time_range=buffered_range,
                    output_path=clip_path,
                )

                # VLMで精密分析
                relative_range, confidence, summary = self.vlm_client.analyze_video_clip(
                    video_path=clip_path,
                    user_query=user_query,
                )

                # 相対時間 → 絶対時間
                absolute_range = convert_relative_to_absolute(
                    clip_start_sec=buffered_range.start_sec,
                    relative_range=relative_range,
                )

                segments.append(
                    VideoSegment(
                        video=video,
                        time_range=absolute_range,
                        summary=summary,
                        confidence=confidence,
                    )
                )

            except Exception as e:
                print(f"Error refining video {video.video_id}: {e}")
                # VLM失敗時は元の推定範囲を使用
                segments.append(
                    VideoSegment(
                        video=video,
                        time_range=estimated_range,
                        summary="（精密分析失敗）",
                        confidence=0.5,
                    )
                )

            finally:
                # 一時ファイル削除
                if clip_path:
                    try:
                        Path(clip_path).unlink()
                    except Exception:
                        pass

        return segments
