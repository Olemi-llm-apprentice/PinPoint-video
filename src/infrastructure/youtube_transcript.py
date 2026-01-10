"""yt-dlp ベースの字幕取得クライアント"""

import yt_dlp

from src.domain.entities import Subtitle, SubtitleChunk
from src.infrastructure.logging_config import get_logger, trace_tool

logger = get_logger(__name__)


class YouTubeTranscriptClient:
    """
    yt-dlp を使用した字幕取得クライアント

    youtube-transcript-api から移行:
    - IPブロックされにくい
    - より堅牢なエラーハンドリング
    - 動画ダウンロード機能と統一

    インターフェースは従来と互換性を維持
    """

    def __init__(self) -> None:
        # yt-dlp のオプション（字幕取得用）
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": False,  # ファイル書き出しはしない
            "writeautomaticsub": False,
        }

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

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                logger.debug(f"[字幕] 動画情報取得失敗: {video_id}")
                return None

            # 手動字幕と自動生成字幕を取得
            manual_subs = info.get("subtitles", {})
            auto_subs = info.get("automatic_captions", {})

            # 利用可能な字幕をログ出力
            available_manual = list(manual_subs.keys()) if manual_subs else []
            available_auto = list(auto_subs.keys()) if auto_subs else []
            logger.debug(
                f"  利用可能な字幕: 手動={available_manual}, 自動={available_auto}"
            )

            # 優先言語で字幕を探す（手動字幕を優先）
            selected_lang = None
            is_auto_generated = False
            subtitle_data = None

            for lang in preferred_languages:
                if lang in manual_subs:
                    selected_lang = lang
                    subtitle_data = manual_subs[lang]
                    is_auto_generated = False
                    logger.debug(f"  手動字幕を使用: {lang}")
                    break
                elif lang in auto_subs:
                    selected_lang = lang
                    subtitle_data = auto_subs[lang]
                    is_auto_generated = True
                    logger.debug(f"  自動生成字幕を使用: {lang}")
                    break

            if not subtitle_data:
                logger.debug(
                    f"  {video_id}: 対応する字幕なし (優先言語: {preferred_languages})"
                )
                return None

            # 字幕データを取得（json3 または srv3 形式を優先）
            chunks = self._extract_chunks(subtitle_data, video_id)

            if not chunks:
                logger.debug(f"[字幕] チャンク抽出失敗: {video_id}")
                return None

            total_duration = chunks[-1].end_sec if chunks else 0
            logger.debug(
                f"[字幕] 取得成功: {video_id} - {len(chunks)}チャンク, {total_duration:.1f}秒"
            )

            return Subtitle(
                video_id=video_id,
                language=selected_lang,
                language_code=selected_lang,
                chunks=chunks,
                is_auto_generated=is_auto_generated,
            )

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Private video" in error_msg:
                logger.debug(f"[字幕] 非公開動画: {video_id}")
            elif "Video unavailable" in error_msg:
                logger.debug(f"[字幕] 動画が利用不可: {video_id}")
            else:
                logger.error(f"[字幕] ダウンロードエラー: {video_id} - {e}")
            return None
        except Exception as e:
            logger.error(f"[字幕] エラー: {video_id} - {e}")
            raise RuntimeError(f"Failed to fetch transcript: {e}") from e

    def _extract_chunks(
        self, subtitle_data: list[dict], video_id: str
    ) -> list[SubtitleChunk]:
        """
        yt-dlp の字幕データからチャンクを抽出

        subtitle_data は [{"url": "...", "ext": "json3"}, ...] の形式
        """
        import json
        import urllib.request

        # json3 形式を優先（タイムスタンプが正確）
        preferred_formats = ["json3", "srv3", "srv2", "srv1", "vtt", "ttml"]

        for fmt in preferred_formats:
            for sub_info in subtitle_data:
                if sub_info.get("ext") == fmt and "url" in sub_info:
                    try:
                        return self._fetch_and_parse_subtitle(
                            sub_info["url"], fmt, video_id
                        )
                    except Exception as e:
                        logger.debug(f"  {fmt} 形式の取得失敗: {e}")
                        continue

        # どの形式も取得できなかった場合
        return []

    def _fetch_and_parse_subtitle(
        self, url: str, fmt: str, video_id: str
    ) -> list[SubtitleChunk]:
        """字幕URLからデータを取得してパース"""
        import json
        import urllib.request

        logger.debug(f"  字幕取得: {fmt} 形式")

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8")

        if fmt == "json3":
            return self._parse_json3(data)
        elif fmt in ("srv3", "srv2", "srv1", "ttml"):
            return self._parse_xml_subtitle(data)
        elif fmt == "vtt":
            return self._parse_vtt(data)
        else:
            return []

    def _parse_json3(self, data: str) -> list[SubtitleChunk]:
        """json3 形式をパース"""
        import json

        parsed = json.loads(data)
        chunks = []

        events = parsed.get("events", [])
        for event in events:
            # tStartMs: 開始時間（ミリ秒）
            # dDurationMs: 継続時間（ミリ秒）
            # segs: セグメント（テキスト）
            start_ms = event.get("tStartMs", 0)
            duration_ms = event.get("dDurationMs", 0)
            segs = event.get("segs", [])

            if not segs:
                continue

            text = "".join(seg.get("utf8", "") for seg in segs).strip()
            if not text or text == "\n":
                continue

            chunks.append(
                SubtitleChunk(
                    start_sec=start_ms / 1000.0,
                    end_sec=(start_ms + duration_ms) / 1000.0,
                    text=text,
                )
            )

        return chunks

    def _parse_xml_subtitle(self, data: str) -> list[SubtitleChunk]:
        """srv3/srv2/srv1/ttml 形式（XML）をパース"""
        import re

        chunks = []

        # <text start="0.0" dur="1.5">テキスト</text> 形式
        # または <p begin="00:00:00.000" end="00:00:01.500">テキスト</p> 形式
        pattern1 = re.compile(
            r'<text[^>]*start="([^"]+)"[^>]*dur="([^"]+)"[^>]*>(.*?)</text>',
            re.DOTALL,
        )
        pattern2 = re.compile(
            r'<p[^>]*begin="([^"]+)"[^>]*end="([^"]+)"[^>]*>(.*?)</p>',
            re.DOTALL,
        )

        # pattern1 を試す
        matches = pattern1.findall(data)
        if matches:
            for start_str, dur_str, text in matches:
                try:
                    start = float(start_str)
                    dur = float(dur_str)
                    clean_text = re.sub(r"<[^>]+>", "", text).strip()
                    if clean_text:
                        chunks.append(
                            SubtitleChunk(
                                start_sec=start,
                                end_sec=start + dur,
                                text=clean_text,
                            )
                        )
                except ValueError:
                    continue
            return chunks

        # pattern2 を試す（TTML形式）
        matches = pattern2.findall(data)
        for begin_str, end_str, text in matches:
            try:
                start = self._parse_timestamp(begin_str)
                end = self._parse_timestamp(end_str)
                clean_text = re.sub(r"<[^>]+>", "", text).strip()
                if clean_text:
                    chunks.append(
                        SubtitleChunk(
                            start_sec=start,
                            end_sec=end,
                            text=clean_text,
                        )
                    )
            except ValueError:
                continue

        return chunks

    def _parse_vtt(self, data: str) -> list[SubtitleChunk]:
        """VTT 形式をパース"""
        import re

        chunks = []

        # 00:00:00.000 --> 00:00:01.500
        pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
        )

        lines = data.split("\n")
        i = 0
        while i < len(lines):
            match = pattern.match(lines[i])
            if match:
                start = self._parse_timestamp(match.group(1))
                end = self._parse_timestamp(match.group(2))
                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1
                text = " ".join(text_lines)
                # タグを除去
                text = re.sub(r"<[^>]+>", "", text).strip()
                if text:
                    chunks.append(
                        SubtitleChunk(
                            start_sec=start,
                            end_sec=end,
                            text=text,
                        )
                    )
            else:
                i += 1

        return chunks

    def _parse_timestamp(self, ts: str) -> float:
        """タイムスタンプを秒に変換（00:00:00.000 形式）"""
        ts = ts.replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600 + float(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return float(m) * 60 + float(s)
        else:
            return float(ts)

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
        subtitle = self.fetch(video_id, preferred_languages)
        if not subtitle:
            return None

        return [
            {
                "text": chunk.text,
                "start": chunk.start_sec,
                "duration": chunk.end_sec - chunk.start_sec,
            }
            for chunk in subtitle.chunks
        ]
