"""メインユースケース: ユーザークエリから関連動画セグメントを抽出"""

import tempfile
import time
from collections.abc import Callable
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
from src.infrastructure.logging_config import get_logger, trace_chain

logger = get_logger(__name__)


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

    @trace_chain(name="extract_segments")
    def execute(
        self,
        user_query: str,
        progress_callback: Callable[[str, float], None] | None = None,
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
        logger.info("=" * 60)
        logger.info(f"[START] ExtractSegments ユースケース開始")
        logger.info(f"  ユーザークエリ: {user_query!r}")
        logger.info(f"  設定: max_search={self.config.max_search_results}, "
                    f"max_final={self.config.max_final_results}, "
                    f"vlm_enabled={self.config.enable_vlm_refinement}")

        def update_progress(stage: str, progress: float) -> None:
            if progress_callback:
                progress_callback(stage, progress)

        # Phase 1: 複数クエリ生成
        logger.info("-" * 40)
        logger.info("[Phase 1] 複数クエリ生成開始")
        update_progress("クエリを最適化中...", 0.05)
        query_variants = self.llm_client.generate_search_queries(user_query)
        logger.info(f"  生成されたクエリ:")
        logger.info(f"    original: {query_variants.original!r}")
        logger.info(f"    optimized: {query_variants.optimized!r}")
        logger.info(f"    simplified: {query_variants.simplified!r}")

        # Phase 2: マルチ戦略YouTube検索（3クエリ × 3戦略 = 最大9回検索）
        logger.info("-" * 40)
        logger.info("[Phase 2] マルチ戦略YouTube検索開始")
        logger.info(f"  動画長フィルタ: {self.config.duration_min_sec}s - {self.config.duration_max_sec}s")
        update_progress("YouTube動画を検索中...", 0.1)

        # 3種類のクエリをリストにまとめる
        search_queries = [
            query_variants.original,
            query_variants.optimized,
            query_variants.simplified,
        ]
        # 重複クエリを除去
        unique_queries = list(dict.fromkeys(search_queries))
        logger.info(f"  検索クエリ数: {len(unique_queries)}（重複除去後）")

        search_result = self.youtube_searcher.search_multi_strategy(
            queries=unique_queries,
            max_results_per_query=self.config.max_search_results // 3,  # 各クエリの取得件数
            duration_min_sec=self.config.duration_min_sec,
            duration_max_sec=self.config.duration_max_sec,
        )

        videos = search_result.videos
        logger.info(f"  検索結果: {len(videos)}件の動画が見つかりました（重複排除済み）")
        logger.info(f"  検索統計: {search_result.search_stats}")
        for i, video in enumerate(videos[:5]):  # 最初の5件だけログ
            logger.debug(f"    [{i+1}] {video.title[:50]}... (id={video.video_id}, {video.duration_sec}s)")

        if not videos:
            logger.warning("[RESULT] 動画が見つかりませんでした")
            logger.info("=" * 60)
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time,
            )

        # Phase 3: 字幕取得 & 粗い範囲特定（並列処理）
        logger.info("-" * 40)
        logger.info("[Phase 3] 字幕取得＆範囲特定開始")
        logger.info(f"  処理対象: {len(videos)}件の動画")
        update_progress("字幕を分析中...", 0.4)
        candidates = self._process_videos_parallel(videos, user_query)
        logger.info(f"  候補セグメント: {len(candidates)}件")
        for i, (video, tr, conf, summary) in enumerate(candidates[:5]):
            logger.debug(f"    [{i+1}] {video.title[:30]}... "
                        f"time={tr.start_sec:.1f}-{tr.end_sec:.1f}s, conf={conf:.2f}")

        # 上位N件に絞り込み
        candidates = sorted(
            candidates,
            key=lambda x: x[2],  # confidence
            reverse=True,
        )[: self.config.max_final_results]
        logger.info(f"  上位{self.config.max_final_results}件に絞り込み: {len(candidates)}件")

        if not candidates:
            logger.warning("[RESULT] 関連するセグメントが見つかりませんでした")
            logger.info("=" * 60)
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time,
            )

        # Phase 4: 精密時刻特定（VLM使用）
        if self.config.enable_vlm_refinement and candidates:
            logger.info("-" * 40)
            logger.info("[Phase 4] VLM精密分析開始")
            update_progress("動画を精密分析中...", 0.6)
            segments = self._refine_with_vlm(candidates, user_query, update_progress)
        else:
            logger.info("[Phase 4] VLM精密分析スキップ（設定またはcandidatesなし）")
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

        logger.info("-" * 40)
        logger.info(f"[RESULT] 処理完了")
        logger.info(f"  結果セグメント数: {len(segments)}")
        logger.info(f"  処理時間: {processing_time:.2f}秒")
        for i, seg in enumerate(segments):
            logger.info(f"    [{i+1}] {seg.video.title[:40]}... "
                       f"time={seg.time_range.start_sec:.1f}-{seg.time_range.end_sec:.1f}s, "
                       f"conf={seg.confidence:.2f}")
        logger.info("=" * 60)

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
        success_count = 0
        error_count = 0
        no_subtitle_count = 0
        no_match_count = 0

        logger.debug(f"  並列処理開始: {len(videos)}件の動画")

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
                video = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        candidates.extend(result)
                        success_count += 1
                        logger.debug(f"    ✓ {video.video_id}: {len(result)}件のセグメント")
                    else:
                        no_match_count += 1
                        logger.debug(f"    - {video.video_id}: 該当セグメントなし")
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)
                    if "subtitle" in error_msg.lower() or "transcript" in error_msg.lower():
                        no_subtitle_count += 1
                        logger.debug(f"    ✗ {video.video_id}: 字幕取得失敗")
                    else:
                        logger.warning(f"    ✗ {video.video_id}: エラー - {e}")
                    continue

        logger.info(f"  並列処理完了: 成功={success_count}, "
                   f"該当なし={no_match_count}, 字幕なし={no_subtitle_count}, "
                   f"エラー={error_count}")

        return candidates

    def _process_single_video(
        self,
        video: Video,
        user_query: str,
    ) -> list[tuple[Video, TimeRange, float, str]]:
        """
        単一動画の処理: 字幕取得 → 範囲特定
        """
        logger.debug(f"    処理開始: {video.video_id} ({video.title[:30]}...)")
        
        # 字幕取得
        subtitle = self.subtitle_fetcher.fetch(video.video_id)
        if not subtitle:
            logger.debug(f"    {video.video_id}: 字幕なし")
            return []
        
        logger.debug(f"    {video.video_id}: 字幕取得成功 "
                    f"(lang={subtitle.language_code}, chunks={len(subtitle.chunks)}, "
                    f"auto={subtitle.is_auto_generated})")

        # LLMで粗い範囲特定
        ranges = self.llm_client.find_relevant_ranges(
            subtitle_text=subtitle.full_text,
            subtitle_chunks=subtitle.chunks,
            user_query=user_query,
        )
        logger.debug(f"    {video.video_id}: LLM分析結果 {len(ranges)}件")

        # 確信度フィルタ
        results = [
            (video, time_range, confidence, summary)
            for time_range, confidence, summary in ranges
            if confidence >= self.config.min_confidence
        ]
        
        filtered_out = len(ranges) - len(results)
        if filtered_out > 0:
            logger.debug(f"    {video.video_id}: 確信度フィルタで{filtered_out}件除外 "
                        f"(min_confidence={self.config.min_confidence})")

        return results

    def _refine_with_vlm(
        self,
        candidates: list[tuple[Video, TimeRange, float, str]],
        user_query: str,
        update_progress: Callable[[str, float], None],
    ) -> list[VideoSegment]:
        """
        VLMで精密な時刻を特定
        """
        segments = []
        total = len(candidates)
        logger.info(f"  VLM精密分析: {total}件の候補を処理")

        for i, (video, estimated_range, _, _) in enumerate(candidates):
            clip_path = None
            logger.info(f"  [{i+1}/{total}] VLM分析: {video.video_id}")
            logger.debug(f"    推定範囲: {estimated_range.start_sec:.1f}s - {estimated_range.end_sec:.1f}s")
            
            try:
                # 進捗更新
                progress = 0.6 + (0.3 * (i / total))
                update_progress(
                    f"動画を精密分析中... ({i + 1}/{total})",
                    progress,
                )

                # バッファ追加
                buffered_range = estimated_range.with_buffer(self.config.buffer_ratio)
                logger.debug(f"    バッファ追加後: {buffered_range.start_sec:.1f}s - {buffered_range.end_sec:.1f}s")

                # 一時ファイルに部分ダウンロード
                with tempfile.NamedTemporaryFile(
                    suffix=".mp4",
                    delete=False,
                ) as tmp:
                    clip_path = tmp.name

                logger.debug(f"    クリップ抽出開始: {clip_path}")
                self.video_extractor.extract_clip(
                    video_url=video.url,
                    time_range=buffered_range,
                    output_path=clip_path,
                )
                
                # ファイルサイズを確認
                clip_size = Path(clip_path).stat().st_size / (1024 * 1024)  # MB
                logger.debug(f"    クリップ抽出完了: {clip_size:.2f} MB")

                # VLMで精密分析
                logger.debug(f"    VLM分析開始")
                relative_range, confidence, summary = self.vlm_client.analyze_video_clip(
                    video_path=clip_path,
                    user_query=user_query,
                )
                logger.debug(f"    VLM結果: 相対時間={relative_range.start_sec:.1f}s-{relative_range.end_sec:.1f}s, "
                            f"conf={confidence:.2f}")

                # 相対時間 → 絶対時間
                absolute_range = convert_relative_to_absolute(
                    clip_start_sec=buffered_range.start_sec,
                    relative_range=relative_range,
                )
                logger.info(f"    ✓ 成功: {absolute_range.start_sec:.1f}s-{absolute_range.end_sec:.1f}s, "
                           f"conf={confidence:.2f}")

                segments.append(
                    VideoSegment(
                        video=video,
                        time_range=absolute_range,
                        summary=summary,
                        confidence=confidence,
                    )
                )

            except Exception as e:
                logger.error(f"    ✗ VLM分析失敗: {video.video_id} - {e}")
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
                        logger.debug(f"    一時ファイル削除完了")
                    except Exception:
                        pass

        return segments
