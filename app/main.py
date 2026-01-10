"""Streamlit アプリケーションエントリーポイント"""

import streamlit as st
import streamlit.components.v1 as components

from config.settings import get_settings
from src.application.usecases.extract_segments import (
    ExtractSegmentsConfig,
    ExtractSegmentsUseCase,
)
from src.infrastructure.gemini_llm_client import GeminiLLMClient
from src.infrastructure.gemini_vlm_client import GeminiVLMClient
from src.infrastructure.youtube_data_api import YouTubeDataAPIClient
from src.infrastructure.youtube_transcript import YouTubeTranscriptClient
from src.infrastructure.ytdlp_extractor import YtdlpVideoExtractor


def init_usecase() -> ExtractSegmentsUseCase:
    """
    DIでユースケースを組み立て

    環境変数:
        YOUTUBE_API_KEY: YouTube Data API キー
        GEMINI_API_KEY: Gemini API キー（google-genaiが自動取得）
        各種モデル設定
    """
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


def main() -> None:
    """Streamlitアプリケーションのメイン関数"""
    st.set_page_config(
        page_title="PinPoint.video",
        page_icon="🎯",
        layout="wide",
    )

    st.title("🎯 PinPoint.video")
    st.markdown("YouTube動画からピンポイントで情報を抽出")

    # サイドバー設定
    with st.sidebar:
        st.header("⚙️ 設定")
        enable_vlm = st.checkbox(
            "VLM精密分析を有効化",
            value=True,
            help="動画を実際にダウンロードして精密な時刻を特定します。無効にすると高速ですが精度が下がります。",
        )

    # 検索フォーム
    with st.form("search_form"):
        query = st.text_input(
            "🔍 何を知りたいですか？",
            placeholder="例: Claude Codeのultrathinkの使い方",
        )
        submitted = st.form_submit_button("🔎 検索", use_container_width=True)

    if submitted and query:
        try:
            usecase = init_usecase()
            # VLM設定を上書き
            usecase.config.enable_vlm_refinement = enable_vlm

            # プログレス表示
            progress_bar = st.progress(0)
            status_text = st.empty()

            def progress_callback(stage: str, progress: float) -> None:
                status_text.text(f"⏳ {stage}")
                progress_bar.progress(progress)

            # 実行
            result = usecase.execute(query, progress_callback=progress_callback)

            progress_bar.progress(1.0)
            status_text.text(
                f"✅ 完了 (処理時間: {result.processing_time_sec:.1f}秒)"
            )

            # 結果表示
            if not result.segments:
                st.warning("該当する動画が見つかりませんでした。")
            else:
                st.success(f"📊 {len(result.segments)}件のセグメントが見つかりました")

                for i, segment in enumerate(result.segments, 1):
                    with st.expander(
                        f"{i}️⃣ {segment.video.title}",
                        expanded=(i == 1),
                    ):
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            # YouTube埋め込み
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
                            st.code(embed_url, language=None)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            st.exception(e)


if __name__ == "__main__":
    main()
