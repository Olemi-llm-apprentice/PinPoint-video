"""yt-dlp + ffmpeg による動画クリップ抽出"""

import subprocess
import tempfile
from pathlib import Path

from src.domain.entities import TimeRange
from src.domain.exceptions import VideoExtractionError
from src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def is_valid_mp4(file_path: Path, ffprobe_path: str = "ffprobe") -> bool:
    """
    MP4ファイルが有効かどうかを確認（moov atomの存在チェック）
    
    Args:
        file_path: チェックするファイルパス
        ffprobe_path: ffprobeの実行パス
        
    Returns:
        有効なMP4ならTrue
    """
    if not file_path.exists():
        return False
    
    # ファイルサイズが0または極端に小さい場合は無効
    if file_path.stat().st_size < 1000:  # 1KB未満
        return False
    
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 出力に "video" が含まれていれば有効
        return "video" in result.stdout
    except Exception as e:
        logger.debug(f"MP4検証エラー: {file_path} - {e}")
        return False


class YtdlpVideoExtractor:
    """yt-dlp + ffmpeg による実装"""

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ytdlp_path: str = "yt-dlp",
    ):
        """
        Args:
            ffmpeg_path: ffmpegの実行パス
            ytdlp_path: yt-dlpの実行パス
        """
        self.ffmpeg_path = ffmpeg_path
        self.ytdlp_path = ytdlp_path

    def get_stream_urls(self, video_url: str) -> tuple[str, str]:
        """
        yt-dlp -g でストリーミングURLを取得
        動画全体をダウンロードせず、URLだけ取得（1-2秒）

        Args:
            video_url: YouTube動画URL

        Returns:
            (video_stream_url, audio_stream_url)

        Raises:
            VideoExtractionError: ストリーミングURL取得失敗
        """
        try:
            result = subprocess.run(
                [
                    self.ytdlp_path,
                    "--youtube-skip-dash-manifest",
                    "-g",
                    video_url,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                raise VideoExtractionError(
                    f"Failed to get stream URLs: {result.stdout}"
                )

            return lines[0], lines[1]  # video_url, audio_url

        except subprocess.TimeoutExpired as e:
            raise VideoExtractionError(f"Timeout getting stream URLs: {e}") from e
        except subprocess.CalledProcessError as e:
            raise VideoExtractionError(
                f"yt-dlp error: {e.stderr or e.stdout}"
            ) from e

    def extract_clip(
        self,
        video_url: str,
        time_range: TimeRange,
        output_path: str,
    ) -> str:
        """
        指定範囲だけを部分ダウンロード

        処理フロー:
        1. yt-dlp -g でストリーミングURL取得
        2. ffmpeg -ss でシーク（Range Requestで該当位置から取得）
        3. -t で指定長さだけダウンロード
        4. video + audio をマージして出力

        2時間動画でも、切り出す部分の長さだけで処理時間が決まる

        Args:
            video_url: YouTube動画URL
            time_range: 抽出する時間範囲
            output_path: 出力ファイルパス

        Returns:
            出力ファイルパス

        Raises:
            VideoExtractionError: クリップ抽出失敗
        """
        try:
            video_stream, audio_stream = self.get_stream_urls(video_url)

            ss_time = time_range.to_ffmpeg_ss()
            duration = time_range.to_ffmpeg_t()

            # ffmpeg コマンド構築
            cmd = [
                self.ffmpeg_path,
                "-y",  # 上書き許可
                "-ss",
                ss_time,  # 開始位置（video stream）
                "-i",
                video_stream,
                "-ss",
                ss_time,  # 開始位置（audio stream）
                "-i",
                audio_stream,
                "-t",
                duration,  # 切り出し長さ
                "-map",
                "0:v",  # video streamを使用
                "-map",
                "1:a",  # audio streamを使用
                "-c:v",
                "libx264",  # video codec
                "-c:a",
                "aac",  # audio codec
                "-movflags",
                "+faststart",  # Web再生用最適化
                output_path,
            ]

            # タイムアウトはクリップ長に応じて調整（最低3分、1分あたり+30秒）
            clip_duration = time_range.end_sec - time_range.start_sec
            timeout_sec = max(180, 180 + int(clip_duration * 0.5))
            
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=timeout_sec,
            )

            # 出力ファイルの検証
            output_file = Path(output_path)
            if not is_valid_mp4(output_file, self.ffmpeg_path.replace("ffmpeg", "ffprobe")):
                raise VideoExtractionError(
                    f"Output file is invalid or incomplete: {output_path}"
                )

            return output_path

        except subprocess.TimeoutExpired as e:
            raise VideoExtractionError(f"Timeout extracting clip: {e}") from e
        except subprocess.CalledProcessError as e:
            raise VideoExtractionError(
                f"ffmpeg error: {e.stderr.decode() if e.stderr else e.stdout}"
            ) from e

    def concat_clips(
        self,
        clip_paths: list[Path],
        output_path: Path,
    ) -> bool:
        """
        複数の動画クリップを一つに結合

        ffmpegのconcat demuxerを使用して、複数のクリップを結合します。
        同じ動画からのセグメントをグループ化してから結合することを推奨。

        Args:
            clip_paths: 結合するクリップファイルのパスリスト
            output_path: 出力ファイルパス

        Returns:
            成功した場合はTrue

        Raises:
            VideoExtractionError: 結合失敗時
        """
        if not clip_paths:
            logger.warning("[VideoExtractor] 結合するクリップがありません")
            return False

        # 存在し、有効なMP4のみフィルタ
        ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        valid_clips = []
        for p in clip_paths:
            if p.exists() and is_valid_mp4(p, ffprobe_path):
                valid_clips.append(p)
            else:
                logger.warning(f"[VideoExtractor] 無効なクリップをスキップ: {p}")
        
        if not valid_clips:
            logger.warning("[VideoExtractor] 有効なクリップファイルがありません")
            return False

        if len(valid_clips) == 1:
            # 1つだけの場合はコピー
            import shutil
            shutil.copy2(valid_clips[0], output_path)
            logger.info(f"[VideoExtractor] 単一クリップをコピー: {output_path}")
            return True

        logger.info(f"[VideoExtractor] {len(valid_clips)}件のクリップを結合開始")

        # concat demuxer用のファイルリストを作成
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as f:
                for clip_path in valid_clips:
                    # パスのエスケープ（シングルクォート対応）
                    escaped_path = str(clip_path.absolute()).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
                list_file = f.name

            # ffmpeg concat demuxerで結合
            # 注意: 入力ファイルのコーデックが異なる場合は再エンコードが必要
            cmd = [
                self.ffmpeg_path,
                "-y",  # 上書き許可
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",  # 再エンコードなし（高速）
                str(output_path),
            ]

            logger.debug(f"[VideoExtractor] ffmpeg concat コマンド: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,  # 5分でタイムアウト
            )

            if result.returncode != 0:
                # コーデック不一致の可能性があるので再エンコードを試行
                logger.warning("[VideoExtractor] concat copy失敗、再エンコードを試行")
                cmd_reencode = [
                    self.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", list_file,
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    str(output_path),
                ]

                subprocess.run(
                    cmd_reencode,
                    capture_output=True,
                    check=True,
                    timeout=600,  # 再エンコードは10分
                )

            logger.info(f"[VideoExtractor] クリップ結合完了: {output_path}")
            return True

        except subprocess.TimeoutExpired as e:
            logger.error(f"[VideoExtractor] 結合タイムアウト: {e}")
            raise VideoExtractionError(f"Timeout concatenating clips: {e}") from e
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"[VideoExtractor] 結合失敗: {error_msg}")
            raise VideoExtractionError(f"ffmpeg concat error: {error_msg}") from e
        finally:
            # 一時ファイルを削除
            try:
                Path(list_file).unlink()
            except Exception:
                pass
