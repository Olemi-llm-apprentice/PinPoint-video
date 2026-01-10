"""Gemini LLM クライアント（テキスト処理用）"""

import json

from google import genai

from src.application.interfaces.llm_client import SearchQueryVariants
from src.domain.entities import SubtitleChunk, TimeRange
from src.domain.exceptions import LLMError
from src.infrastructure.logging_config import get_logger, trace_llm

logger = get_logger(__name__)


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

    @trace_llm(name="convert_to_search_query", metadata={"purpose": "query_optimization"})
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
        logger.info(f"[LLM] クエリ変換開始")
        logger.debug(f"  入力: {user_query!r}")
        logger.debug(f"  モデル: {self.query_convert_model}")
        
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
            logger.debug(f"  プロンプト長: {len(prompt)} chars")
            response = self.client.models.generate_content(
                model=self.query_convert_model,
                contents=prompt,
            )
            result = response.text.strip()
            logger.info(f"[LLM] クエリ変換完了: {result!r}")
            return result
        except Exception as e:
            logger.error(f"[LLM] クエリ変換失敗: {e}")
            raise LLMError(f"Failed to convert query: {e}") from e

    @trace_llm(name="generate_search_queries", metadata={"purpose": "multi_query_generation"})
    def generate_search_queries(self, user_query: str) -> SearchQueryVariants:
        """
        ユーザークエリから複数の検索クエリバリエーションを生成

        3種類のクエリを生成:
        1. original: ユーザー入力そのまま
        2. optimized: LLMで最適化（英語キーワード追加など）
        3. simplified: シンプルなキーワードに分割

        Args:
            user_query: ユーザーの入力クエリ

        Returns:
            SearchQueryVariants: 3種類のクエリバリエーション
        """
        logger.info(f"[LLM] 複数クエリ生成開始")
        logger.debug(f"  入力: {user_query!r}")

        prompt = f"""あなたはYouTube検索クエリの最適化専門家です。

ユーザーの質問から、YouTube検索用のクエリを2種類生成してください。

ユーザーの質問: {user_query}

以下のJSON形式で回答してください:
{{
  "optimized": "<英語キーワードを含む最適化クエリ（5-7語）>",
  "simplified": "<核となるキーワードのみ（2-4語、固有名詞・技術用語中心）>"
}}

ルール:
- optimized: 英語の修飾語（tutorial, explained, how to等）を適宜追加
- simplified: 余計な言葉を省いて核となるキーワードのみ抽出
  例: "Claude Code 2.1.2の主な変更点" → "Claude Code 2.1.2"
  例: "Pythonでファイルを読み込む方法" → "Python ファイル 読み込み"

JSONのみを出力してください:"""

        try:
            response = self.client.models.generate_content(
                model=self.query_convert_model,
                contents=prompt,
            )

            json_str = response.text.strip()
            logger.debug(f"  LLM生出力: {json_str}")

            # JSON部分を抽出
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            json_str = json_str.strip()

            data = json.loads(json_str)

            result = SearchQueryVariants(
                original=user_query,
                optimized=data.get("optimized", user_query),
                simplified=data.get("simplified", user_query),
            )

            logger.info(f"[LLM] 複数クエリ生成完了:")
            logger.info(f"  original: {result.original!r}")
            logger.info(f"  optimized: {result.optimized!r}")
            logger.info(f"  simplified: {result.simplified!r}")

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"[LLM] JSONパースエラー、フォールバック使用: {e}")
            # フォールバック: 全て元のクエリを使用
            return SearchQueryVariants(
                original=user_query,
                optimized=user_query,
                simplified=user_query,
            )
        except Exception as e:
            logger.error(f"[LLM] クエリ生成失敗: {e}")
            raise LLMError(f"Failed to generate search queries: {e}") from e

    @trace_llm(name="find_relevant_ranges", metadata={"purpose": "subtitle_analysis"})
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
        logger.debug(f"[LLM] 関連範囲特定開始")
        logger.debug(f"  クエリ: {user_query!r}")
        logger.debug(f"  字幕チャンク数: {len(subtitle_chunks)}")
        logger.debug(f"  モデル: {self.subtitle_analysis_model}")
        
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

        logger.debug(f"  プロンプト長: {len(prompt)} chars")

        try:
            response = self.client.models.generate_content(
                model=self.subtitle_analysis_model,
                contents=prompt,
            )

            # JSON部分を抽出してパース
            json_str = response.text.strip()
            logger.debug(f"  LLM生出力: {json_str[:200]}..." if len(json_str) > 200 else f"  LLM生出力: {json_str}")
            
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

            logger.debug(f"[LLM] 関連範囲特定完了: {len(results)}件")
            for i, (tr, conf, summ) in enumerate(results):
                logger.debug(f"    [{i+1}] {tr.start_sec:.1f}s-{tr.end_sec:.1f}s, conf={conf:.2f}, summary={summ[:30]}...")
            
            return results

        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSONパースエラー: {e}")
            logger.error(f"  生出力: {json_str[:500] if json_str else 'N/A'}")
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e
        except (KeyError, ValueError) as e:
            logger.error(f"[LLM] レスポンス形式エラー: {e}")
            raise LLMError(f"Invalid LLM response format: {e}") from e
        except Exception as e:
            logger.error(f"[LLM] APIエラー: {e}")
            raise LLMError(f"LLM API error: {e}") from e

    @trace_llm(name="filter_videos_by_title", metadata={"purpose": "title_relevance_check"})
    def filter_videos_by_title(
        self,
        video_titles: list[tuple[str, str]],  # [(video_id, title), ...]
        user_query: str,
        max_results: int = 10,
    ) -> list[str]:
        """
        タイトルベースで関連性の高い動画をフィルタリング

        字幕取得の前に、タイトルで事前フィルタリングすることで
        APIリクエスト数を削減する

        Args:
            video_titles: [(video_id, title), ...] のリスト
            user_query: ユーザークエリ
            max_results: 返す最大件数

        Returns:
            関連性の高い動画のvideo_idリスト
        """
        if not video_titles:
            return []

        logger.info(f"[LLM] タイトルフィルタリング開始")
        logger.debug(f"  クエリ: {user_query!r}")
        logger.debug(f"  候補数: {len(video_titles)}件")

        # タイトルリストを整形
        titles_text = "\n".join(
            f"{i+1}. [{vid}] {title}"
            for i, (vid, title) in enumerate(video_titles)
        )

        prompt = f"""あなたは動画検索の専門家です。

以下の動画タイトル一覧から、ユーザーの質問に関連する可能性が高い動画を選んでください。

ユーザーの質問: {user_query}

動画タイトル一覧:
{titles_text}

以下のJSON形式で回答してください:
{{
  "relevant_video_ids": ["video_id1", "video_id2", ...]
}}

ルール:
- 関連性が高そうな動画を最大{max_results}件まで選択
- タイトルにクエリのキーワードや関連トピックが含まれているものを優先
- 関連性が低いと判断した動画は含めない
- video_idは角括弧内の文字列をそのまま使用

JSONのみを出力してください:"""

        try:
            response = self.client.models.generate_content(
                model=self.query_convert_model,
                contents=prompt,
            )

            json_str = response.text.strip()
            logger.debug(f"  LLM生出力: {json_str}")

            # JSON部分を抽出
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            json_str = json_str.strip()

            data = json.loads(json_str)
            relevant_ids = data.get("relevant_video_ids", [])

            # 有効なIDのみフィルタ
            valid_ids = {vid for vid, _ in video_titles}
            filtered_ids = [vid for vid in relevant_ids if vid in valid_ids]

            logger.info(f"[LLM] タイトルフィルタリング完了: {len(video_titles)}件 → {len(filtered_ids)}件")
            for vid in filtered_ids[:5]:
                title = next((t for v, t in video_titles if v == vid), "")
                logger.debug(f"    [OK] {vid}: {title[:40]}...")

            return filtered_ids[:max_results]

        except json.JSONDecodeError as e:
            logger.warning(f"[LLM] JSONパースエラー、全件を返す: {e}")
            # フォールバック: 全件を返す
            return [vid for vid, _ in video_titles[:max_results]]
        except Exception as e:
            logger.error(f"[LLM] タイトルフィルタリング失敗: {e}")
            # エラー時も全件を返す（字幕取得でフィルタされる）
            return [vid for vid, _ in video_titles[:max_results]]

    @trace_llm(name="generate_integrated_summary", metadata={"purpose": "summary_integration"})
    def generate_integrated_summary(
        self,
        user_query: str,
        segment_summaries: list[dict],
    ) -> str:
        """
        複数セグメントのサマリーを統合して一つのまとめを生成

        Args:
            user_query: ユーザーの元のクエリ
            segment_summaries: セグメント情報のリスト
                [{"video_title": str, "summary": str, "time_range": str}, ...]

        Returns:
            統合されたサマリー文

        Raises:
            LLMError: API呼び出しエラー
        """
        if not segment_summaries:
            return "該当するセグメントが見つかりませんでした。"

        logger.info(f"[LLM] 統合サマリー生成開始")
        logger.debug(f"  クエリ: {user_query!r}")
        logger.debug(f"  セグメント数: {len(segment_summaries)}件")

        # セグメント情報を整形
        segments_text = "\n".join(
            f"- 動画「{seg['video_title'][:50]}」({seg['time_range']}): {seg['summary']}"
            for seg in segment_summaries
        )

        prompt = f"""あなたは情報整理の専門家です。

以下の複数の動画セグメントから得られた情報を、ユーザーの質問に対する
一つのまとまった回答として整理してください。

ユーザーの質問: {user_query}

見つかった動画セグメントの内容:
{segments_text}

ルール:
- 複数のセグメントの内容を統合して、一つのまとまった回答を作成
- 重複する情報は統合
- 動画名や時間範囲は言及しない（ユーザーは内容だけを知りたい）
- 日本語で200-400文字程度
- 箇条書きを使って読みやすく整理
- 「〜についてですが」などの前置きは不要、内容のみ記載

統合サマリー:"""

        try:
            response = self.client.models.generate_content(
                model=self.subtitle_analysis_model,
                contents=prompt,
            )
            result = response.text.strip()
            logger.info(f"[LLM] 統合サマリー生成完了: {len(result)}文字")
            return result

        except Exception as e:
            logger.error(f"[LLM] 統合サマリー生成失敗: {e}")
            # フォールバック: 個別サマリーを結合
            fallback = "\n".join(
                f"• {seg['summary']}" for seg in segment_summaries
            )
            return f"【個別サマリー】\n{fallback}"
