"""yt-dlp ベースの字幕取得クライアント"""

import json
import os
import re
import tempfile
from pathlib import Path

import yt_dlp

from src.domain.entities import Subtitle, SubtitleChunk
from src.infrastructure.logging_config import get_logger, trace_tool

logger = get_logger(__name__)


class YouTubeTranscriptClient:
    """
    yt-dlp を使用した字幕取得クライアント

    youtube-transcript-api から移行:
    - IPブロックされにくい（yt-dlpの内部処理を利用）
    - より堅牢なエラーハンドリング
    - 動画ダウンロード機能と統一

    インターフェースは従来と互換性を維持
    """

    def __init__(self) -> None:
        pass

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

        # 一時ディレクトリで字幕をダウンロード
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = self._download_subtitle(url, video_id, tmpdir, preferred_languages)
                if not result:
                    logger.debug(f"[字幕] 字幕取得失敗: {video_id}")
                    return None

                subtitle_path, selected_lang, is_auto_generated = result

                # 字幕ファイルをパース
                chunks = self._parse_subtitle_file(subtitle_path)

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
                return None

    def _download_subtitle(
        self,
        url: str,
        video_id: str,
        tmpdir: str,
        preferred_languages: list[str],
    ) -> tuple[str, str, bool] | None:
        """
        yt-dlp を使って字幕をダウンロード

        Returns:
            (字幕ファイルパス, 言語コード, 自動生成フラグ) または None
        """
        # まず動画情報を取得して利用可能な字幕を確認
        info_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }

        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return None

        manual_subs = info.get("subtitles", {})
        auto_subs = info.get("automatic_captions", {})

        # 利用可能な字幕をログ出力
        available_manual = list(manual_subs.keys()) if manual_subs else []
        available_auto = list(auto_subs.keys()) if auto_subs else []
        logger.debug(f"  利用可能な字幕: 手動={available_manual[:5]}..., 自動={len(available_auto)}言語")

        # 優先言語で字幕を探す
        selected_lang = None
        is_auto_generated = False

        for lang in preferred_languages:
            if lang in manual_subs:
                selected_lang = lang
                is_auto_generated = False
                logger.debug(f"  手動字幕を使用: {lang}")
                break
            elif lang in auto_subs:
                selected_lang = lang
                is_auto_generated = True
                logger.debug(f"  自動生成字幕を使用: {lang}")
                break

        if not selected_lang:
            logger.debug(f"  対応する字幕なし (優先言語: {preferred_languages})")
            return None

        # 字幕をダウンロード
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

        download_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": not is_auto_generated,
            "writeautomaticsub": is_auto_generated,
            "subtitleslangs": [selected_lang],
            "subtitlesformat": "json3/srv3/srv2/srv1/vtt/ttml/best",
            "outtmpl": output_template,
        }

        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        # ダウンロードされた字幕ファイルを探す
        subtitle_extensions = [".json3", ".srv3", ".srv2", ".srv1", ".vtt", ".ttml", ".srt"]
        for ext in subtitle_extensions:
            # yt-dlp は video_id.lang.ext の形式で保存
            possible_paths = [
                os.path.join(tmpdir, f"{video_id}.{selected_lang}{ext}"),
                os.path.join(tmpdir, f"{video_id}{ext}"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    logger.debug(f"  字幕ファイル: {os.path.basename(path)}")
                    return path, selected_lang, is_auto_generated

        # ファイルが見つからない場合、ディレクトリ内を検索
        for file in os.listdir(tmpdir):
            if video_id in file:
                path = os.path.join(tmpdir, file)
                logger.debug(f"  字幕ファイル（検索）: {file}")
                return path, selected_lang, is_auto_generated

        logger.debug(f"  字幕ファイルが見つかりません: {os.listdir(tmpdir)}")
        return None

    def _parse_subtitle_file(self, filepath: str) -> list[SubtitleChunk]:
        """字幕ファイルをパース"""
        ext = Path(filepath).suffix.lower()
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()

        if ext == ".json3" or filepath.endswith(".json3"):
            return self._parse_json3(data)
        elif ext in (".srv3", ".srv2", ".srv1", ".ttml") or any(
            filepath.endswith(e) for e in [".srv3", ".srv2", ".srv1", ".ttml"]
        ):
            return self._parse_xml_subtitle(data)
        elif ext == ".vtt" or filepath.endswith(".vtt"):
            return self._parse_vtt(data)
        elif ext == ".srt" or filepath.endswith(".srt"):
            return self._parse_srt(data)
        else:
            # 拡張子が不明な場合、内容から判断
            if data.strip().startswith("{"):
                return self._parse_json3(data)
            elif data.strip().startswith("WEBVTT"):
                return self._parse_vtt(data)
            elif "<text" in data or "<p" in data:
                return self._parse_xml_subtitle(data)
            else:
                return self._parse_srt(data)

    def _parse_json3(self, data: str) -> list[SubtitleChunk]:
        """json3 形式をパース"""
        parsed = json.loads(data)
        chunks = []

        events = parsed.get("events", [])
        for event in events:
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
        chunks = []

        # <text start="0.0" dur="1.5">テキスト</text> 形式
        pattern1 = re.compile(
            r'<text[^>]*start="([^"]+)"[^>]*dur="([^"]+)"[^>]*>(.*?)</text>',
            re.DOTALL,
        )
        # <p begin="00:00:00.000" end="00:00:01.500">テキスト</p> 形式
        pattern2 = re.compile(
            r'<p[^>]*begin="([^"]+)"[^>]*end="([^"]+)"[^>]*>(.*?)</p>',
            re.DOTALL,
        )

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
        chunks = []

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

    def _parse_srt(self, data: str) -> list[SubtitleChunk]:
        """SRT 形式をパース"""
        chunks = []

        # SRT形式: 番号 → タイムスタンプ → テキスト → 空行
        pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
        )

        blocks = re.split(r"\n\s*\n", data.strip())
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 2:
                continue

            # タイムスタンプ行を探す
            for i, line in enumerate(lines):
                match = pattern.match(line)
                if match:
                    start = self._parse_timestamp(match.group(1))
                    end = self._parse_timestamp(match.group(2))
                    text = " ".join(lines[i + 1 :])
                    text = re.sub(r"<[^>]+>", "", text).strip()
                    if text:
                        chunks.append(
                            SubtitleChunk(
                                start_sec=start,
                                end_sec=end,
                                text=text,
                            )
                        )
                    break

        return chunks

    def _parse_timestamp(self, ts: str) -> float:
        """タイムスタンプを秒に変換"""
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
