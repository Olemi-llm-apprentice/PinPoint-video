"""Gemini VLM クライアント（動画分析用）"""

import json
from pathlib import Path

from google import genai
from google.genai import types

from src.domain.entities import TimeRange
from src.domain.exceptions import VLMError


class GeminiVLMClient:
    """
    Google GenAI SDK (google-genai) を使用した動画分析

    動画理解の仕様:
    - 最大動画長: 1Mコンテキスト=1時間、2Mコンテキスト=2時間
    - サンプリング: デフォルト1FPS（カスタマイズ可能）
    - トークン計算: 約300tokens/秒（低解像度: 100tokens/秒）
    """

    def __init__(
        self,
        api_key: str | None = None,
        video_analysis_model: str = "gemini-2.5-flash",
    ):
        """
        Args:
            api_key: APIキー。Noneの場合はGEMINI_API_KEY環境変数から自動取得
            video_analysis_model: 動画分析用モデル
        """
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

        self.video_analysis_model = video_analysis_model

    def analyze_video_clip(
        self,
        video_path: str,
        user_query: str,
    ) -> tuple[TimeRange, float, str]:
        """
        動画クリップを分析し、クエリに該当する部分の時間を特定

        Args:
            video_path: ローカルの動画ファイルパス
            user_query: ユーザーの検索クエリ

        Returns:
            (relative_time_range, confidence, summary)
            relative_time_range: クリップ内での相対時間

        Raises:
            VLMError: API呼び出しエラー

        Note:
        - gemini-2.5-flash は動画分析に対応
        - 部分ダウンロードしたクリップは通常5分以下なので余裕
        """
        video_file = None
        try:
            # 動画ファイルをアップロード
            video_file = self.client.files.upload(file=video_path)

            prompt = f"""あなたは動画内容分析の専門家です。

この動画クリップを分析し、以下の質問に関連する部分を特定してください。

質問: {user_query}

以下のJSON形式で回答してください:
{{
  "start_sec": <クリップ内での開始秒>,
  "end_sec": <クリップ内での終了秒>,
  "confidence": <0.0-1.0の確信度>,
  "summary": "<該当部分で話されている内容の要約>"
}}

ルール:
- start_sec, end_sec はこの動画クリップ内での相対時間（0秒から開始）
- 該当する部分がない場合は confidence を 0.0 にする
- summary は日本語で100文字以内
- 映像と音声の両方を考慮して判断する

JSONのみを出力してください:"""

            response = self.client.models.generate_content(
                model=self.video_analysis_model,
                contents=[video_file, prompt],
            )

            json_str = response.text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            json_str = json_str.strip()

            data = json.loads(json_str)

            time_range = TimeRange(
                start_sec=float(data["start_sec"]),
                end_sec=float(data["end_sec"]),
            )
            confidence = float(data["confidence"])
            summary = data["summary"]

            return time_range, confidence, summary

        except json.JSONDecodeError as e:
            raise VLMError(f"Failed to parse VLM response as JSON: {e}") from e
        except (KeyError, ValueError) as e:
            raise VLMError(f"Invalid VLM response format: {e}") from e
        except Exception as e:
            raise VLMError(f"VLM API error: {e}") from e

        finally:
            # アップロードしたファイルを削除
            if video_file:
                try:
                    self.client.files.delete(name=video_file.name)
                except Exception:
                    pass

    def analyze_video_clip_with_custom_fps(
        self,
        video_path: str,
        user_query: str,
        fps: float = 1.0,
    ) -> tuple[TimeRange, float, str]:
        """
        カスタムFPSで動画を分析（長い動画や高速動画向け）

        Args:
            video_path: ローカルの動画ファイルパス
            user_query: ユーザーの検索クエリ
            fps: サンプリングFPS（デフォルト1.0）
                 - 長い動画: 0.5以下推奨
                 - 高速アクション: 2.0以上推奨

        Returns:
            (relative_time_range, confidence, summary)

        Raises:
            VLMError: API呼び出しエラー
        """
        try:
            video_bytes = Path(video_path).read_bytes()

            prompt = f"""質問: {user_query}

この動画クリップを分析し、質問に関連する部分を特定してください。

JSON形式で回答:
{{"start_sec": <開始秒>, "end_sec": <終了秒>, "confidence": <確信度>, "summary": "<要約>"}}"""

            response = self.client.models.generate_content(
                model=self.video_analysis_model,
                contents=types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=video_bytes,
                                mime_type="video/mp4",
                            ),
                            video_metadata=types.VideoMetadata(fps=fps),
                        ),
                        types.Part(text=prompt),
                    ]
                ),
            )

            json_str = response.text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            json_str = json_str.strip()

            data = json.loads(json_str)

            time_range = TimeRange(
                start_sec=float(data["start_sec"]),
                end_sec=float(data["end_sec"]),
            )
            confidence = float(data["confidence"])
            summary = data["summary"]

            return time_range, confidence, summary

        except json.JSONDecodeError as e:
            raise VLMError(f"Failed to parse VLM response as JSON: {e}") from e
        except (KeyError, ValueError) as e:
            raise VLMError(f"Invalid VLM response format: {e}") from e
        except Exception as e:
            raise VLMError(f"VLM API error: {e}") from e
