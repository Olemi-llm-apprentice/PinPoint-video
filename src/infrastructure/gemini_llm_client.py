"""Gemini LLM クライアント（テキスト処理用）"""

import json

from google import genai

from src.domain.entities import SubtitleChunk, TimeRange
from src.domain.exceptions import LLMError


class GeminiLLMClient:
    """
    Google GenAI SDK (google-genai) を使用

    ⚠️ 旧SDK (google-generativeai) は 2025/11/30 でサポート終了

    環境変数:
        GEMINI_API_KEY: APIキー（自動で読み込まれる）
    """

    def __init__(
        self,
        api_key: str | None = None,
        query_convert_model: str = "gemini-2.5-flash",
        subtitle_analysis_model: str = "gemini-2.5-flash",
    ):
        """
        Args:
            api_key: APIキー。Noneの場合はGEMINI_API_KEY環境変数から自動取得
            query_convert_model: クエリ変換用モデル
            subtitle_analysis_model: 字幕分析用モデル
        """
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()  # 環境変数から自動取得

        self.query_convert_model = query_convert_model
        self.subtitle_analysis_model = subtitle_analysis_model

    def convert_to_search_query(self, user_query: str) -> str:
        """
        ユーザークエリをYouTube検索クエリに変換

        Args:
            user_query: ユーザーの入力クエリ

        Returns:
            YouTube検索に最適化されたクエリ

        Raises:
            LLMError: API呼び出しエラー
        """
        prompt = f"""あなたはYouTube検索クエリの最適化専門家です。

ユーザーの質問を、YouTube検索で最も関連性の高い結果が得られる
検索クエリに変換してください。

ルール:
- 英語のキーワードを含める（技術用語は英語が効果的）
- 5-7語程度に収める
- 「tutorial」「how to」「explained」などの修飾語を適宜追加

ユーザーの質問: {user_query}

検索クエリのみを出力してください（説明不要）:"""

        try:
            response = self.client.models.generate_content(
                model=self.query_convert_model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            raise LLMError(f"Failed to convert query: {e}") from e

    def find_relevant_ranges(
        self,
        subtitle_text: str,
        subtitle_chunks: list[SubtitleChunk],
        user_query: str,
    ) -> list[tuple[TimeRange, float, str]]:
        """
        字幕から該当する時間範囲を特定

        Args:
            subtitle_text: 字幕全文（未使用だが将来の拡張用）
            subtitle_chunks: 字幕チャンクリスト
            user_query: ユーザークエリ

        Returns:
            [(TimeRange, confidence, summary), ...]

        Raises:
            LLMError: API呼び出しエラー
        """
        # 字幕チャンクを時間付きで整形
        formatted_chunks = "\n".join(
            [
                f"[{chunk.start_sec:.1f}s - {chunk.end_sec:.1f}s] {chunk.text}"
                for chunk in subtitle_chunks
            ]
        )

        prompt = f"""あなたは動画内容分析の専門家です。

以下の字幕データから、ユーザーの質問に関連する部分を特定してください。

ユーザーの質問: {user_query}

字幕データ:
{formatted_chunks}

以下のJSON形式で回答してください:
{{
  "segments": [
    {{
      "start_sec": <開始秒>,
      "end_sec": <終了秒>,
      "confidence": <0.0-1.0の確信度>,
      "summary": "<この部分で話されている内容の要約>"
    }}
  ]
}}

ルール:
- 関連性の高い部分を最大3つまで抽出
- 関連する部分がない場合は空配列を返す
- confidenceは内容の関連性に基づいて設定
- summaryは日本語で50文字以内

JSONのみを出力してください:"""

        try:
            response = self.client.models.generate_content(
                model=self.subtitle_analysis_model,
                contents=prompt,
            )

            # JSON部分を抽出してパース
            json_str = response.text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            json_str = json_str.strip()

            data = json.loads(json_str)

            results = []
            for seg in data.get("segments", []):
                time_range = TimeRange(
                    start_sec=float(seg["start_sec"]),
                    end_sec=float(seg["end_sec"]),
                )
                confidence = float(seg["confidence"])
                summary = seg["summary"]
                results.append((time_range, confidence, summary))

            return results

        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e
        except (KeyError, ValueError) as e:
            raise LLMError(f"Invalid LLM response format: {e}") from e
        except Exception as e:
            raise LLMError(f"LLM API error: {e}") from e
