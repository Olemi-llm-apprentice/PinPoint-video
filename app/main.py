"""Streamlit アプリケーションエントリーポイント"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを最初に読み込む（LangSmith等の環境変数を設定するため）
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import streamlit as st
import streamlit.components.v1 as components

from config.settings import get_settings
from src.application.usecases.extract_segments import (
    ExtractSegmentsConfig,
    ExtractSegmentsUseCase,
    ProgressDetails,
)
from src.domain.entities import SearchResult, VideoSegment
from src.infrastructure.gemini_llm_client import GeminiLLMClient
from src.infrastructure.gemini_vlm_client import GeminiVLMClient
from src.infrastructure.logging_config import get_logger, is_langsmith_enabled, setup_logging
from src.infrastructure.session_storage import SessionMetadata, SessionStorage
from src.infrastructure.youtube_data_api import YouTubeDataAPIClient
from src.infrastructure.youtube_transcript import YouTubeTranscriptClient
from src.infrastructure.ytdlp_extractor import YtdlpVideoExtractor

# ロギング初期化
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
setup_logging(level=log_level)

logger = get_logger(__name__)

# セッションストレージ初期化
storage = SessionStorage()


def init_usecase() -> ExtractSegmentsUseCase:
    """DIでユースケースを組み立て"""
    settings = get_settings()

    return ExtractSegmentsUseCase(
        youtube_searcher=YouTubeDataAPIClient(
            api_key=settings.YOUTUBE_API_KEY,
            published_after=settings.PUBLISHED_AFTER,
            published_before=settings.PUBLISHED_BEFORE,
        ),
        subtitle_fetcher=YouTubeTranscriptClient(),
        llm_client=GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            query_convert_model=settings.get_model("query_convert"),
            subtitle_analysis_model=settings.get_model("subtitle_analysis"),
        ),
        video_extractor=YtdlpVideoExtractor(
            ffmpeg_path=settings.FFMPEG_PATH,
            ytdlp_path=settings.YTDLP_PATH,
        ),
        vlm_client=GeminiVLMClient(
            api_key=settings.GEMINI_API_KEY,
            video_analysis_model=settings.get_model("video_analysis"),
        ),
        config=ExtractSegmentsConfig(
            max_search_results=settings.MAX_SEARCH_RESULTS,
            max_final_results=settings.MAX_FINAL_RESULTS,
            buffer_ratio=settings.BUFFER_RATIO,
            min_confidence=settings.MIN_CONFIDENCE,
            enable_vlm_refinement=settings.ENABLE_VLM_REFINEMENT,
            duration_min_sec=settings.DURATION_MIN_SEC,
            duration_max_sec=settings.DURATION_MAX_SEC,
        ),
    )


def render_youtube_embed(video_id: str, start_sec: int, end_sec: int) -> None:
    """タイムスタンプ付きYouTube埋め込み"""
    embed_url = (
        f"https://www.youtube.com/embed/{video_id}?start={start_sec}&end={end_sec}"
    )
    components.iframe(embed_url, height=315, width=560)


def format_time(seconds: float) -> str:
    """秒をMM:SS形式に変換"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def format_datetime(iso_string: str) -> str:
    """ISO形式の日時を見やすく変換"""
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return iso_string[:16]


def render_result_segments(segments: list[VideoSegment]) -> None:
    """検索結果のセグメントを表示"""
    if not segments:
        st.warning("該当する動画が見つかりませんでした。")
        return

    st.success(f"📊 {len(segments)}件のセグメントが見つかりました")

    for i, segment in enumerate(segments, 1):
        with st.expander(
            f"{i}️⃣ {segment.video.title}",
            expanded=(i == 1),
        ):
            col1, col2 = st.columns([2, 1])

            with col1:
                params = segment.time_range.to_youtube_embed_params()
                render_youtube_embed(
                    video_id=segment.video.video_id,
                    start_sec=params["start"],
                    end_sec=params["end"],
                )

            with col2:
                st.markdown(f"**📺 {segment.video.channel_name}**")

                start_time = format_time(segment.time_range.start_sec)
                end_time = format_time(segment.time_range.end_sec)
                st.markdown(f"**⏱️ {start_time} - {end_time}**")

                st.markdown(f"**🎯 確信度: {segment.confidence:.0%}**")

            st.markdown("---")
            st.markdown(f"💡 {segment.summary}")

            col_a, col_b = st.columns(2)
            with col_a:
                full_url = (
                    f"https://youtube.com/watch?v={segment.video.video_id}"
                    f"&t={params['start']}"
                )
                st.link_button("🔗 元動画を開く", full_url)

            with col_b:
                embed_url = segment.embed_url
                st.code(embed_url, language=None)


def render_history_sidebar() -> str | None:
    """サイドバーに履歴一覧を表示し、選択されたセッションIDを返す"""
    with st.sidebar:
        st.header("📚 検索履歴")
        
        # 新規検索ボタン
        if st.button("➕ 新規検索", use_container_width=True, type="primary"):
            st.session_state.selected_session = None
            st.session_state.view_mode = "new"
            st.rerun()

        st.divider()

        # 履歴一覧
        sessions = storage.list_sessions(limit=30)
        
        if not sessions:
            st.caption("まだ検索履歴がありません")
            return None

        for session in sessions:
            # 各履歴をボタンで表示
            label = f"🕐 {format_datetime(session.created_at)}\n{session.query[:25]}..."
            
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    label,
                    key=f"session_{session.session_id}",
                    use_container_width=True,
                ):
                    st.session_state.selected_session = session.session_id
                    st.session_state.view_mode = "history"
                    st.rerun()
            
            with col2:
                if st.button("🗑", key=f"delete_{session.session_id}", help="削除"):
                    storage.delete_session(session.session_id)
                    st.rerun()

    return st.session_state.get("selected_session")


def render_history_view(session_id: str) -> None:
    """履歴の詳細表示"""
    loaded = storage.load_session(session_id)
    
    if not loaded:
        st.error("セッションが見つかりません")
        return

    metadata, result = loaded

    # ヘッダー
    st.markdown(f"## 🔍 {result.query}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("検索日時", format_datetime(metadata.created_at))
    with col2:
        st.metric("結果数", f"{len(result.segments)}件")
    with col3:
        st.metric("処理時間", f"{result.processing_time_sec:.1f}秒")

    # タブで表示を切り替え
    tab_results, tab_clips, tab_log, tab_markdown = st.tabs([
        "📊 結果", "🎬 クリップ", "📝 ログ", "📄 Markdown"
    ])

    with tab_results:
        render_result_segments(result.segments)

    with tab_clips:
        clips = storage.get_session_clips(session_id)
        if clips:
            st.info(f"保存されたクリップ: {len(clips)}件")
            for clip_path in clips:
                st.markdown(f"- `{clip_path.name}`")
                # 動画再生（Streamlitのビデオプレーヤー）
                try:
                    st.video(str(clip_path))
                except Exception:
                    st.caption(f"再生できません: {clip_path}")
        else:
            st.caption("保存されたクリップはありません")
            if not metadata.vlm_enabled:
                st.info("VLM精密分析が無効だったため、クリップは保存されていません")

    with tab_log:
        log_content = storage.get_session_log(session_id)
        if log_content:
            st.code(log_content, language="text")
        else:
            st.caption("ログは保存されていません")

    with tab_markdown:
        # result.mdを表示
        md_path = storage._get_session_dir(session_id) / "result.md"
        if md_path.exists():
            with open(md_path, encoding="utf-8") as f:
                md_content = f.read()
            st.markdown(md_content)
            
            # ダウンロードボタン
            st.download_button(
                "📥 Markdownをダウンロード",
                data=md_content,
                file_name=f"pinpoint_result_{session_id}.md",
                mime="text/markdown",
            )
        else:
            st.caption("Markdownファイルがありません")


def run_new_search(query: str, enable_vlm: bool, save_clips: bool = True) -> None:
    """新規検索を実行"""
    logger.info("=" * 70)
    logger.info(f"[APP] 新規検索リクエスト")
    logger.info(f"  クエリ: {query!r}")
    logger.info(f"  VLM精密分析: {'有効' if enable_vlm else '無効'}")
    
    try:
        usecase = init_usecase()
        usecase.config.enable_vlm_refinement = enable_vlm

        # プログレス表示用のコンテナ
        progress_container = st.container()
        with progress_container:
            progress_bar = st.progress(0)
            status_main = st.empty()
            status_detail = st.empty()
            detail_expander = st.expander("📊 詳細ステータス", expanded=True)
            with detail_expander:
                detail_placeholder = st.empty()

        # ログ収集用
        log_lines: list[str] = []

        def progress_callback(details: ProgressDetails, progress: float) -> None:
            phase_icons = {
                "クエリ最適化": "🔄",
                "YouTube検索": "🔍",
                "字幕分析": "📝",
                "VLM精密分析": "🎬",
                "完了": "✅",
            }
            icon = phase_icons.get(details.phase, "⏳")
            status_main.markdown(f"### {icon} {details.phase}")
            status_detail.text(details.step)
            progress_bar.progress(progress)

            # ログに追加
            log_lines.append(f"[{details.phase}] {details.step}")

            # 詳細情報の構築
            detail_lines = []
            if details.details:
                d = details.details

                if details.phase == "クエリ最適化":
                    if "optimized" in d:
                        detail_lines.append("**生成されたクエリ:**")
                        detail_lines.append(f"- オリジナル: `{d.get('original', '')}`")
                        detail_lines.append(f"- 最適化: `{d.get('optimized', '')}`")
                        detail_lines.append(f"- 簡略化: `{d.get('simplified', '')}`")

                elif details.phase == "YouTube検索":
                    if "video_count" in d:
                        detail_lines.append(f"**検索結果:** {d['video_count']}件の動画")
                        if "videos" in d:
                            detail_lines.append("**発見した動画:**")
                            for v in d["videos"][:5]:
                                duration_min = v.get("duration_sec", 0) // 60
                                detail_lines.append(
                                    f"- {v['title'][:40]}... ({v['channel']}, {duration_min}分)"
                                )
                            if len(d["videos"]) > 5:
                                detail_lines.append(f"  ...他 {len(d['videos']) - 5}件")
                    elif "queries" in d:
                        detail_lines.append(f"**検索クエリ:** {d['query_count']}種類")

                elif details.phase == "字幕分析":
                    if "stats" in d:
                        stats = d["stats"]
                        detail_lines.append("**字幕分析の結果:**")
                        detail_lines.append(f"- ✅ 成功: {stats.get('success', 0)}件")
                        detail_lines.append(f"- ➖ 該当なし: {stats.get('no_match', 0)}件")
                        detail_lines.append(f"- ⚠️ 字幕なし: {stats.get('no_subtitle', 0)}件")
                        if stats.get("errors", 0) > 0:
                            detail_lines.append(f"- ❌ エラー: {stats['errors']}件")
                    elif "processed" in d:
                        detail_lines.append(
                            f"**進捗:** {d['processed']}/{d['total']}件処理完了"
                        )
                    elif "selected_videos" in d:
                        detail_lines.append(f"**選出された動画:** {d['selected_count']}件")
                        for v in d["selected_videos"]:
                            detail_lines.append(
                                f"- {v['title'][:35]}... (確信度: {v['confidence']:.0%})"
                            )

                elif details.phase == "VLM精密分析":
                    if "video_title" in d:
                        status_icon = {
                            "downloading": "⬇️ ダウンロード中",
                            "analyzing": "🤖 AI分析中",
                            "completed": "✅ 完了",
                            "error": "❌ エラー",
                        }.get(d.get("status", ""), "⏳ 処理中")

                        detail_lines.append(f"**現在の動画:** ({d['current']}/{d['total']})")
                        detail_lines.append(f"- タイトル: {d['video_title'][:50]}...")
                        detail_lines.append(f"- ステータス: {status_icon}")

                        if d.get("status") == "downloading":
                            detail_lines.append(f"- 範囲: {d.get('estimated_range', '')}")
                        elif d.get("status") == "analyzing":
                            detail_lines.append(f"- クリップサイズ: {d.get('clip_size_mb', 0):.1f} MB")
                        elif d.get("status") == "completed":
                            detail_lines.append(f"- 確信度: {d.get('confidence', 0):.0%}")
                            detail_lines.append(f"- 時間範囲: {d.get('time_range', '')}")
                        elif d.get("status") == "error":
                            detail_lines.append(f"- エラー: {d.get('error', '不明')}")

                elif details.phase == "完了":
                    detail_lines.append(f"**最終結果:** {d.get('segment_count', 0)}件のセグメント")
                    detail_lines.append(f"**処理時間:** {d.get('processing_time_sec', 0):.1f}秒")

            if detail_lines:
                detail_placeholder.markdown("\n".join(detail_lines))

        # クリップ保存用の一時的なセッションID（実行後に正式なIDを取得）
        saved_clips: list[tuple[str, Path]] = []

        def clip_save_callback(video_id: str, clip_path: Path) -> None:
            # 後でセッションに保存するためにリストに追加
            saved_clips.append((video_id, clip_path))

        # 実行
        result = usecase.execute(
            query,
            progress_callback=progress_callback,
            clip_save_callback=clip_save_callback if (enable_vlm and save_clips) else None,
        )

        progress_bar.progress(1.0)
        status_main.markdown("### ✅ 完了")
        status_detail.text(f"処理時間: {result.processing_time_sec:.1f}秒")
        
        logger.info(f"[APP] 検索完了: {len(result.segments)}件のセグメント")

        # セッションを保存
        session_id = storage.save_session(
            result=result,
            vlm_enabled=enable_vlm,
            logs=log_lines,
        )

        # クリップを保存（VLMが有効だった場合）
        for video_id, clip_path in saved_clips:
            if clip_path.exists():
                storage.save_clip(session_id, video_id, clip_path)

        logger.info(f"[APP] セッション保存完了: {session_id}")

        # 結果表示
        render_result_segments(result.segments)

        # 保存完了メッセージ
        st.info(f"💾 検索結果を保存しました (ID: {session_id[:20]}...)")

    except Exception as e:
        logger.error(f"[APP] エラー発生: {e}", exc_info=True)
        st.error(f"エラーが発生しました: {e}")
        st.exception(e)


def main() -> None:
    """Streamlitアプリケーションのメイン関数"""
    st.set_page_config(
        page_title="PinPoint.video",
        page_icon="🎯",
        layout="wide",
    )

    # セッション状態の初期化
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "new"
    if "selected_session" not in st.session_state:
        st.session_state.selected_session = None

    # LangSmith状態をサイドバーに表示
    with st.sidebar:
        if is_langsmith_enabled():
            project = os.getenv("LANGSMITH_PROJECT", "default")
            st.success(f"🔍 LangSmith: 有効 (project: {project})")
        else:
            st.info("🔍 LangSmith: 無効")

    # サイドバーに履歴を表示
    selected_session = render_history_sidebar()

    # メインコンテンツ
    st.title("🎯 PinPoint.video")
    st.markdown("YouTube動画からピンポイントで情報を抽出")

    # 履歴表示モード
    if st.session_state.view_mode == "history" and selected_session:
        render_history_view(selected_session)
    else:
        # 新規検索モード
        # 設定
        with st.sidebar:
            st.header("⚙️ 設定")
            enable_vlm = st.checkbox(
                "VLM精密分析を有効化",
                value=True,
                help="動画を実際にダウンロードして精密な時刻を特定します。無効にすると高速ですが精度が下がります。",
            )
            save_clips = st.checkbox(
                "動画クリップを保存",
                value=True,
                help="VLM分析時にダウンロードした動画クリップを保存します。",
                disabled=not enable_vlm,
            )

        # 検索フォーム
        with st.form("search_form"):
            query = st.text_input(
                "🔍 何を知りたいですか？",
                placeholder="例: Claude Codeのultrathinkの使い方",
            )
            submitted = st.form_submit_button("🔎 検索", use_container_width=True)

        if submitted and query:
            run_new_search(query, enable_vlm, save_clips)


if __name__ == "__main__":
    main()
