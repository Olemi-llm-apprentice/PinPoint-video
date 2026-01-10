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
class ProgressDetails:
    """進捗の詳細情報"""

    phase: str  # 現在のフェーズ名
    step: str  # 現在のステップの説明
    details: dict | None = None  # 追加の詳細情報


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
    # YouTube URL フォールバック（字幕取得429エラー時）
    enable_youtube_url_fallback: bool = True  # フォールバック機能を有効にするか
    youtube_url_fallback_max_duration: int = 1200  # フォールバック対象の最大動画長（秒）= 20分


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
        progress_callback: Callable[[ProgressDetails, float], None] | None = None,
        clip_save_callback: Callable[[str, Path], None] | None = None,
        subtitle_callback: Callable[[str, dict], None] | None = None,
    ) -> SearchResult:
        """
        メイン実行フロー

        Args:
            user_query: ユーザーの検索クエリ
            progress_callback: 進捗コールバック (details: ProgressDetails, progress: float)
            clip_save_callback: クリップ保存コールバック (video_id: str, clip_path: Path)
                               VLM分析後、クリップを削除する前に呼ばれる
            subtitle_callback: 字幕取得コールバック (video_id: str, subtitle_data: dict)
                              字幕取得成功時に呼ばれる

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

        def update_progress(
            phase: str,
            step: str,
            progress: float,
            details: dict | None = None,
        ) -> None:
            if progress_callback:
                progress_callback(
                    ProgressDetails(phase=phase, step=step, details=details),
                    progress,
                )

        # Phase 1: 複数クエリ生成
        logger.info("-" * 40)
        logger.info("[Phase 1] 複数クエリ生成開始")
        update_progress(
            phase="クエリ最適化",
            step="LLMでクエリを最適化中...",
            progress=0.05,
            details={"user_query": user_query},
        )
        query_variants = self.llm_client.generate_search_queries(user_query)
        logger.info(f"  生成されたクエリ:")
        logger.info(f"    original: {query_variants.original!r}")
        logger.info(f"    optimized: {query_variants.optimized!r}")
        logger.info(f"    simplified: {query_variants.simplified!r}")
        update_progress(
            phase="クエリ最適化",
            step="クエリ生成完了",
            progress=0.08,
            details={
                "original": query_variants.original,
                "optimized": query_variants.optimized,
                "simplified": query_variants.simplified,
            },
        )

        # Phase 2: マルチ戦略YouTube検索（3クエリ × 3戦略 = 最大9回検索）
        logger.info("-" * 40)
        logger.info("[Phase 2] マルチ戦略YouTube検索開始")
        logger.info(f"  動画長フィルタ: {self.config.duration_min_sec}s - {self.config.duration_max_sec}s")

        # 3種類のクエリをリストにまとめる
        search_queries = [
            query_variants.original,
            query_variants.optimized,
            query_variants.simplified,
        ]
        # 重複クエリを除去
        unique_queries = list(dict.fromkeys(search_queries))
        logger.info(f"  検索クエリ数: {len(unique_queries)}（重複除去後）")

        update_progress(
            phase="YouTube検索",
            step="YouTube Data APIで動画を検索中...",
            progress=0.1,
            details={
                "query_count": len(unique_queries),
                "queries": unique_queries,
            },
        )

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

        update_progress(
            phase="YouTube検索",
            step=f"{len(videos)}件の動画が見つかりました",
            progress=0.2,
            details={
                "video_count": len(videos),
                "videos": [
                    {"title": v.title, "channel": v.channel_name, "duration_sec": v.duration_sec}
                    for v in videos[:10]  # 上位10件のみ
                ],
                "search_stats": search_result.search_stats,
            },
        )

        if not videos:
            logger.warning("[RESULT] 動画が見つかりませんでした")
            logger.info("=" * 60)
            update_progress(
                phase="YouTube検索",
                step="動画が見つかりませんでした",
                progress=1.0,
                details={"video_count": 0},
            )
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time,
            )

        # Phase 2.5: タイトルベースの事前フィルタリング
        logger.info("-" * 40)
        logger.info("[Phase 2.5] タイトル関連性チェック開始")
        logger.info(f"  チェック対象: {len(videos)}件の動画")
        update_progress(
            phase="タイトルフィルタ",
            step="動画タイトルの関連性をチェック中...",
            progress=0.22,
            details={"total_videos": len(videos)},
        )

        # タイトルリストを作成
        video_titles = [(v.video_id, v.title) for v in videos]

        # LLMでフィルタリング（最大10件に絞る）
        max_title_filter = min(10, self.config.max_search_results)
        relevant_video_ids = self.llm_client.filter_videos_by_title(
            video_titles=video_titles,
            user_query=user_query,
            max_results=max_title_filter,
        )

        # フィルタリング結果を適用
        filtered_videos = [v for v in videos if v.video_id in relevant_video_ids]
        
        # フィルタで0件になった場合は元の上位件数を使用
        if not filtered_videos:
            logger.warning("  タイトルフィルタで0件、上位件数を使用")
            filtered_videos = videos[:max_title_filter]

        logger.info(f"  フィルタ結果: {len(videos)}件 → {len(filtered_videos)}件")
        for i, v in enumerate(filtered_videos[:5]):
            logger.debug(f"    [{i+1}] {v.title[:50]}...")

        update_progress(
            phase="タイトルフィルタ",
            step=f"関連性の高い{len(filtered_videos)}件を選択",
            progress=0.24,
            details={
                "original_count": len(videos),
                "filtered_count": len(filtered_videos),
                "filtered_videos": [
                    {"title": v.title, "video_id": v.video_id}
                    for v in filtered_videos[:5]
                ],
            },
        )

        videos = filtered_videos  # 以降はフィルタ済みリストを使用

        # Phase 3: 字幕取得 & 粗い範囲特定（並列処理）
        logger.info("-" * 40)
        logger.info("[Phase 3] 字幕取得＆範囲特定開始")
        logger.info(f"  処理対象: {len(videos)}件の動画")
        update_progress(
            phase="字幕分析",
            step=f"{len(videos)}件の動画の字幕を取得・分析中...",
            progress=0.25,
            details={"total_videos": len(videos)},
        )
        candidates, subtitle_stats = self._process_videos_parallel(
            videos, user_query, update_progress, subtitle_callback
        )
        logger.info(f"  候補セグメント: {len(candidates)}件")
        for i, (video, tr, conf, summary) in enumerate(candidates[:5]):
            logger.debug(f"    [{i+1}] {video.title[:30]}... "
                        f"time={tr.start_sec:.1f}-{tr.end_sec:.1f}s, conf={conf:.2f}")
        
        update_progress(
            phase="字幕分析",
            step=f"字幕分析完了: {len(candidates)}件の候補セグメント",
            progress=0.5,
            details={
                "candidate_count": len(candidates),
                "stats": subtitle_stats,
            },
        )

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
            update_progress(
                phase="字幕分析",
                step="関連するセグメントが見つかりませんでした",
                progress=1.0,
                details={"candidate_count": 0},
            )
            return SearchResult(
                query=user_query,
                segments=[],
                processing_time_sec=time.time() - start_time,
            )

        update_progress(
            phase="字幕分析",
            step=f"上位{len(candidates)}件に絞り込み完了",
            progress=0.55,
            details={
                "selected_count": len(candidates),
                "selected_videos": [
                    {"title": v.title, "confidence": conf}
                    for v, _, conf, _ in candidates
                ],
            },
        )

        # Phase 4: 精密時刻特定（VLM使用）
        if self.config.enable_vlm_refinement and candidates:
            logger.info("-" * 40)
            logger.info("[Phase 4] VLM精密分析開始")
            update_progress(
                phase="VLM精密分析",
                step=f"{len(candidates)}件の動画を精密分析開始...",
                progress=0.6,
                details={"total_videos": len(candidates)},
            )
            segments = self._refine_with_vlm(
                candidates, user_query, update_progress, clip_save_callback
            )
        else:
            logger.info("[Phase 4] VLM精密分析スキップ（設定またはcandidatesなし）")
            update_progress(
                phase="VLM精密分析",
                step="VLM精密分析をスキップ（無効設定）",
                progress=0.9,
                details={"skipped": True},
            )
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
        update_progress(
            phase="完了",
            step=f"処理完了: {len(segments)}件のセグメント",
            progress=1.0,
            details={
                "segment_count": len(segments),
                "processing_time_sec": round(processing_time, 2),
            },
        )

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
        update_progress: Callable[[str, str, float, dict | None], None],
        subtitle_callback: Callable[[str, dict], None] | None = None,
    ) -> tuple[list[tuple[Video, TimeRange, float, str]], dict]:
        """
        複数動画を並列処理して候補を抽出

        Returns:
            ([(Video, TimeRange, confidence, summary), ...], stats_dict)
        """
        candidates = []
        success_count = 0
        error_count = 0
        no_subtitle_count = 0
        no_match_count = 0
        processed_count = 0
        total = len(videos)

        logger.debug(f"  並列処理開始: {total}件の動画")

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
                    # YouTube URLフォールバック時は60秒以上かかる場合があるため、タイムアウトを延長
                    result, subtitle_data = future.result(timeout=120)
                    processed_count += 1
                    
                    # 字幕データをコールバックで渡す
                    if subtitle_data and subtitle_callback:
                        try:
                            subtitle_callback(video.video_id, subtitle_data)
                        except Exception as e:
                            logger.warning(f"    字幕コールバック失敗: {video.video_id} - {e}")
                    
                    if result:
                        candidates.extend(result)
                        success_count += 1
                        logger.debug(f"    [OK] {video.video_id}: {len(result)}件のセグメント")
                    else:
                        no_match_count += 1
                        logger.debug(f"    - {video.video_id}: 該当セグメントなし")
                except Exception as e:
                    processed_count += 1
                    error_count += 1
                    error_msg = str(e)
                    if "subtitle" in error_msg.lower() or "transcript" in error_msg.lower():
                        no_subtitle_count += 1
                        logger.debug(f"    [SKIP] {video.video_id}: 字幕取得失敗")
                    else:
                        logger.warning(f"    [ERROR] {video.video_id}: エラー - {e}")
                    continue

                # 進捗更新（10件ごと、または最後）
                if processed_count % 10 == 0 or processed_count == total:
                    progress = 0.25 + (0.2 * processed_count / total)
                    update_progress(
                        "字幕分析",
                        f"字幕を分析中... ({processed_count}/{total})",
                        progress,
                        {
                            "processed": processed_count,
                            "total": total,
                            "success": success_count,
                            "no_match": no_match_count,
                            "no_subtitle": no_subtitle_count,
                            "errors": error_count,
                        },
                    )

        stats = {
            "success": success_count,
            "no_match": no_match_count,
            "no_subtitle": no_subtitle_count,
            "errors": error_count,
        }

        logger.info(f"  並列処理完了: 成功={success_count}, "
                   f"該当なし={no_match_count}, 字幕なし={no_subtitle_count}, "
                   f"エラー={error_count}")

        return candidates, stats

    def _process_single_video(
        self,
        video: Video,
        user_query: str,
    ) -> tuple[list[tuple[Video, TimeRange, float, str]], dict | None]:
        """
        単一動画の処理: 字幕取得 → 範囲特定

        Returns:
            (結果リスト, 字幕データdict)
        """
        logger.debug(f"    処理開始: {video.video_id} ({video.title[:30]}...)")
        
        # 字幕取得
        subtitle = self.subtitle_fetcher.fetch(video.video_id)
        
        if not subtitle:
            # 字幕取得失敗 → フォールバック処理を試行
            if self._should_use_youtube_url_fallback(video):
                logger.info(f"    {video.video_id}: 字幕取得失敗、YouTube URLフォールバックを試行")
                return self._process_with_youtube_url_fallback(video, user_query)
            else:
                logger.debug(f"    {video.video_id}: 字幕なし（フォールバック対象外: "
                           f"動画長={video.duration_sec}s > {self.config.youtube_url_fallback_max_duration}s）")
                return [], None
        
        logger.debug(f"    {video.video_id}: 字幕取得成功 "
                    f"(lang={subtitle.language_code}, chunks={len(subtitle.chunks)}, "
                    f"auto={subtitle.is_auto_generated})")

        # 字幕データをdict化
        subtitle_data = {
            "video_id": subtitle.video_id,
            "language": subtitle.language,
            "language_code": subtitle.language_code,
            "is_auto_generated": subtitle.is_auto_generated,
            "full_text": subtitle.full_text,
            "chunks": [
                {
                    "start_sec": chunk.start_sec,
                    "end_sec": chunk.end_sec,
                    "text": chunk.text,
                }
                for chunk in subtitle.chunks
            ],
        }

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

        return results, subtitle_data

    def _should_use_youtube_url_fallback(self, video: Video) -> bool:
        """
        YouTube URLフォールバックを使用すべきか判定

        条件:
        - フォールバック機能が有効
        - 動画長が設定された最大値以下
        """
        if not self.config.enable_youtube_url_fallback:
            return False
        if video.duration_sec > self.config.youtube_url_fallback_max_duration:
            return False
        return True

    def _process_with_youtube_url_fallback(
        self,
        video: Video,
        user_query: str,
    ) -> tuple[list[tuple[Video, TimeRange, float, str]], dict | None]:
        """
        YouTube URLを直接LLMに渡して分析（フォールバック処理）

        字幕取得が429エラー等で失敗した場合に使用。
        Gemini 2.5はYouTube URLを直接理解できる。

        Returns:
            (結果リスト, None)  # 字幕データは取得できないためNone
        """
        try:
            logger.debug(f"    {video.video_id}: YouTube URL直接分析開始")
            logger.debug(f"      URL: {video.url}")
            logger.debug(f"      動画長: {video.duration_sec}s")

            # LLMでYouTube URLを直接分析
            ranges = self.llm_client.analyze_youtube_video(
                video_url=video.url,
                user_query=user_query,
            )

            logger.debug(f"    {video.video_id}: YouTube URL分析結果 {len(ranges)}件")

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

            if results:
                logger.info(f"    {video.video_id}: YouTube URLフォールバック成功 ({len(results)}件)")
            else:
                logger.debug(f"    {video.video_id}: YouTube URLフォールバック結果なし")

            return results, None  # 字幕データは取得できない

        except Exception as e:
            logger.warning(f"    {video.video_id}: YouTube URLフォールバック失敗 - {e}")
            return [], None

    def _refine_with_vlm(
        self,
        candidates: list[tuple[Video, TimeRange, float, str]],
        user_query: str,
        update_progress: Callable[[str, str, float, dict | None], None],
        clip_save_callback: Callable[[str, Path], None] | None = None,
    ) -> list[VideoSegment]:
        """
        VLMで精密な時刻を特定（並列処理・リトライ対応）

        Args:
            candidates: 候補リスト
            user_query: ユーザークエリ
            update_progress: 進捗更新コールバック
            clip_save_callback: クリップ保存コールバック（削除前に呼ばれる）
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(candidates)
        logger.info(f"  VLM精密分析: {total}件の候補を並列処理")

        # 並列処理の設定
        max_workers = min(3, total)  # 最大3並列
        stagger_delay = 3.0  # 各タスクの開始遅延（秒）
        max_retries = 3  # 最大リトライ回数
        retry_delay = 2.0  # リトライ間の遅延（秒）

        # スレッドセーフな結果格納
        results_lock = threading.Lock()
        results: list[tuple[int, VideoSegment]] = []  # (index, segment)
        completed_count = [0]  # リストでラップしてnonlocalの代わりに

        def process_candidate(
            index: int,
            video: Video,
            estimated_range: TimeRange,
        ) -> tuple[int, VideoSegment]:
            """1つの候補を処理（遅延スタート・リトライ対応）"""
            clip_path = None

            # 遅延スタート（APIレート制限対策）
            if index > 0:
                delay = index * stagger_delay
                logger.debug(f"    [{index+1}/{total}] {delay:.1f}秒待機後に開始...")
                time.sleep(delay)

            logger.info(f"  [{index+1}/{total}] VLM分析開始: {video.video_id}")
            logger.debug(f"    推定範囲: {estimated_range.start_sec:.1f}s - {estimated_range.end_sec:.1f}s")

            try:
                # バッファ追加
                buffered_range = estimated_range.with_buffer(self.config.buffer_ratio)

                # 一時ファイルに部分ダウンロード
                with tempfile.NamedTemporaryFile(
                    suffix=".mp4",
                    delete=False,
                ) as tmp:
                    clip_path = tmp.name

                logger.debug(f"    [{index+1}] クリップ抽出開始")
                self.video_extractor.extract_clip(
                    video_url=video.url,
                    time_range=buffered_range,
                    output_path=clip_path,
                )

                clip_size = Path(clip_path).stat().st_size / (1024 * 1024)
                logger.debug(f"    [{index+1}] クリップ抽出完了: {clip_size:.2f} MB")

                # VLMで精密分析（リトライ付き）
                last_error = None
                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            logger.info(f"    [{index+1}] リトライ {attempt+1}/{max_retries}...")
                            time.sleep(retry_delay * attempt)  # 指数バックオフ的な遅延

                        relative_range, confidence, summary = self.vlm_client.analyze_video_clip(
                            video_path=clip_path,
                            user_query=user_query,
                        )

                        # 成功
                        absolute_range = convert_relative_to_absolute(
                            clip_start_sec=buffered_range.start_sec,
                            relative_range=relative_range,
                        )
                        logger.info(f"    [{index+1}] [OK] 成功: {absolute_range.start_sec:.1f}s-{absolute_range.end_sec:.1f}s, "
                                   f"conf={confidence:.2f}")

                        segment = VideoSegment(
                            video=video,
                            time_range=absolute_range,
                            summary=summary,
                            confidence=confidence,
                        )

                        # 進捗更新（スレッドセーフ、Streamlitエラーは無視）
                        with results_lock:
                            completed_count[0] += 1
                            try:
                                update_progress(
                                    "VLM精密分析",
                                    f"分析完了 ({completed_count[0]}/{total}): {video.title[:30]}...",
                                    0.6 + (0.35 * completed_count[0] / total),
                                    {
                                        "current": completed_count[0],
                                        "total": total,
                                        "video_title": video.title,
                                        "status": "completed",
                                        "confidence": round(confidence, 2),
                                    },
                                )
                            except Exception:
                                pass  # Streamlit NoSessionContext等は無視

                        return index, segment

                    except Exception as e:
                        last_error = e
                        logger.warning(f"    [{index+1}] VLM分析失敗 (attempt {attempt+1}): {e}")

                # 全リトライ失敗
                raise last_error or Exception("Unknown error after retries")

            except Exception as e:
                logger.error(f"    [{index+1}] [FAIL] VLM分析失敗: {video.video_id} - {e}")

                # 失敗時は元の推定範囲を使用
                segment = VideoSegment(
                    video=video,
                    time_range=estimated_range,
                    summary="（精密分析失敗）",
                    confidence=0.5,
                )

                with results_lock:
                    completed_count[0] += 1
                    try:
                        update_progress(
                            "VLM精密分析",
                            f"分析失敗 ({completed_count[0]}/{total}): {video.title[:30]}...",
                            0.6 + (0.35 * completed_count[0] / total),
                            {
                                "current": completed_count[0],
                                "total": total,
                                "video_title": video.title,
                                "status": "error",
                                "error": str(e)[:100],
                            },
                        )
                    except Exception:
                        pass  # Streamlit NoSessionContext等は無視

                return index, segment

            finally:
                # クリップ保存コールバック
                if clip_path and clip_save_callback:
                    try:
                        clip_save_callback(video.video_id, Path(clip_path))
                    except Exception as e:
                        logger.warning(f"    [{index+1}] クリップ保存コールバック失敗: {e}")

                # 一時ファイル削除
                if clip_path:
                    try:
                        Path(clip_path).unlink()
                    except Exception:
                        pass

        # 並列実行
        update_progress(
            "VLM精密分析",
            f"{total}件の動画を並列分析中... (最大{max_workers}並列)",
            0.6,
            {"total": total, "max_workers": max_workers, "status": "starting"},
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    process_candidate,
                    i,
                    video,
                    estimated_range,
                ): i
                for i, (video, estimated_range, _, _) in enumerate(candidates)
            }

            for future in as_completed(futures):
                try:
                    index, segment = future.result()
                    with results_lock:
                        results.append((index, segment))
                except Exception as e:
                    logger.error(f"  並列処理エラー: {e}")

        # インデックス順にソートして返す
        results.sort(key=lambda x: x[0])
        return [segment for _, segment in results]
