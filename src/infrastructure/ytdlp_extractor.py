"""yt-dlp + ffmpeg による動画クリップ抽出"""

import subprocess

from src.domain.entities import TimeRange
from src.domain.exceptions import VideoExtractionError


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

            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=120,  # 2分でタイムアウト
            )

            return output_path

        except subprocess.TimeoutExpired as e:
            raise VideoExtractionError(f"Timeout extracting clip: {e}") from e
        except subprocess.CalledProcessError as e:
            raise VideoExtractionError(
                f"ffmpeg error: {e.stderr.decode() if e.stderr else e.stdout}"
            ) from e
