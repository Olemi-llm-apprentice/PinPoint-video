"""Gemini LLM クライアント（テキスト処理用）"""

import json

from google import genai
from google.genai import types
from google.genai.types import Modality

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
        image_generation_model: str = "gemini-2.0-flash-exp",
    ):
        """
        Args:
            api_key: APIキー。Noneの場合はGEMINI_API_KEY環境変数から自動取得
            query_convert_model: クエリ変換用モデル
            subtitle_analysis_model: 字幕分析用モデル
            image_generation_model: 画像生成用モデル
        """
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()  # 環境変数から自動取得

        self.query_convert_model = query_convert_model
        self.subtitle_analysis_model = subtitle_analysis_model
        self.image_generation_model = image_generation_model

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

    @trace_llm(name="analyze_youtube_video", metadata={"purpose": "youtube_url_direct_analysis"})
    def analyze_youtube_video(
        self,
        video_url: str,
        user_query: str,
    ) -> list[tuple[TimeRange, float, str]]:
        """
        YouTube動画URLを直接Geminiに渡して関連範囲を特定

        字幕取得が429エラーで失敗した場合のフォールバック用。
        Gemini 2.5はYouTube URLを直接理解できる。

        Args:
            video_url: YouTube動画のURL
            user_query: ユーザークエリ

        Returns:
            [(TimeRange, confidence, summary), ...]

        Raises:
            LLMError: API呼び出しエラー
        """
        logger.info(f"[LLM] YouTube URL直接分析開始")
        logger.debug(f"  URL: {video_url}")
        logger.debug(f"  クエリ: {user_query!r}")
        logger.debug(f"  モデル: {self.subtitle_analysis_model}")

        prompt = f"""あなたは動画内容分析の専門家です。

この動画を視聴して、ユーザーの質問に関連する部分を特定してください。

ユーザーの質問: {user_query}

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
- 動画を視聴して、質問に関連する部分を最大3つまで抽出
- 関連する部分がない場合は空配列を返す
- start_sec, end_secは動画の時間（秒単位）を正確に指定
- confidenceは内容の関連性に基づいて設定
- summaryは日本語で50文字以内

JSONのみを出力してください:"""

        try:
            # YouTube URLをPart.from_uriで渡す
            video_part = types.Part.from_uri(
                file_uri=video_url,
                mime_type="video/*",
            )

            response = self.client.models.generate_content(
                model=self.subtitle_analysis_model,
                contents=[video_part, prompt],
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
                try:
                    start = float(seg["start_sec"])
                    end = float(seg["end_sec"])
                    # 不正な値はスキップ
                    if start >= end or start < 0:
                        logger.warning(f"  無効な時間範囲をスキップ: {start}s-{end}s")
                        continue
                    time_range = TimeRange(
                        start_sec=start,
                        end_sec=end,
                    )
                    confidence = float(seg["confidence"])
                    summary = seg["summary"]
                    results.append((time_range, confidence, summary))
                except (KeyError, ValueError) as e:
                    logger.warning(f"  セグメントのパースエラー: {e}")
                    continue

            logger.info(f"[LLM] YouTube URL直接分析完了: {len(results)}件")
            for i, (tr, conf, summ) in enumerate(results):
                logger.debug(f"    [{i+1}] {tr.start_sec:.1f}s-{tr.end_sec:.1f}s, conf={conf:.2f}, summary={summ[:30]}...")

            return results

        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSONパースエラー: {e}")
            logger.error(f"  生出力: {json_str[:500] if 'json_str' in dir() else 'N/A'}")
            raise LLMError(f"Failed to parse LLM response as JSON: {e}") from e
        except Exception as e:
            logger.error(f"[LLM] YouTube URL分析エラー: {e}")
            raise LLMError(f"YouTube URL analysis failed: {e}") from e

    @trace_llm(name="generate_infographic", metadata={"purpose": "image_generation"})
    def generate_infographic(
        self,
        video_path: str,
        user_query: str,
        integrated_summary: str,
        segment_summaries: list[dict],
        subtitle_texts: list[str] | None = None,
    ) -> bytes | None:
        """
        検索結果からインフォグラフィック画像を生成

        Note: gemini-3-pro-image-previewは動画入力をサポートしないため、
        テキスト情報のみを使用して画像を生成します。

        Args:
            video_path: 結合動画ファイルのパス（現在未使用）
            user_query: ユーザーの検索クエリ
            integrated_summary: 統合サマリー
            segment_summaries: セグメントサマリーのリスト
            subtitle_texts: 字幕テキストのリスト（オプション）

        Returns:
            生成された画像のバイトデータ（失敗時はNone）
        """
        logger.info(f"[LLM] インフォグラフィック生成開始")
        logger.debug(f"  クエリ: {user_query!r}")
        logger.debug(f"  モデル: {self.image_generation_model}")

        # セグメント情報を整形
        segments_text = "\n".join(
            f"• {seg.get('video_title', '')[:30]}... : {seg.get('summary', '')}"
            for seg in segment_summaries[:5]
        )

        # 字幕テキストを整形（先頭2000文字まで）
        subtitle_section = ""
        if subtitle_texts:
            combined_subtitles = "\n---\n".join(subtitle_texts)
            # 長すぎる場合は切り詰め
            if len(combined_subtitles) > 2000:
                combined_subtitles = combined_subtitles[:2000] + "..."
            subtitle_section = f"""

## 動画の字幕内容（参考）
{combined_subtitles}
"""

        prompt = f"""あなたはプロのインフォグラフィックデザイナーです。

以下の調査結果を元に、1枚のインフォグラフィックスライドを生成してください。

## 調査クエリ
{user_query}

## 調査結果サマリー
{integrated_summary}

## 主要ポイント
{segments_text}
{subtitle_section}
## 画像生成要件
- **言語**: 日本語テキストを使用
- **スタイル**: モダンでクリーンなインフォグラフィックデザイン
- 視覚的な階層構造（タイトル→主要ポイント→結論）
- アイコンや図解を活用
- 読みやすいフォントと適切な余白
- カラフルだが統一感のある配色

## 構成
1. キャッチーなタイトル（クエリに対する答えを一言で）
2. 3-5個の主要ポイント（アイコン付き）
3. 結論・まとめ

上記の要件に基づいて高解像度のインフォグラフィック画像を生成してください。"""

        try:
            # 画像生成（gemini-3-pro-image-preview用の設定）
            # Note: このモデルは動画/音声入力をサポートしないため、テキストのみ
            config = types.GenerateContentConfig(
                response_modalities=[Modality.TEXT, Modality.IMAGE],
                image_config=types.ImageConfig(
                    aspect_ratio="9:16",  # 縦長フォーマット
                    image_size="2K",
                ),
            )
            response = self.client.models.generate_content(
                model=self.image_generation_model,
                contents=prompt,  # テキストプロンプトのみ
                config=config,
            )

            # 画像データを抽出
            image_parts = [part for part in response.parts if part.inline_data]
            if image_parts:
                image_data = image_parts[0].inline_data.data
                logger.info(f"[LLM] インフォグラフィック生成完了: {len(image_data)} bytes")
                return image_data

            logger.warning("[LLM] 画像データが見つかりません")
            return None

        except Exception as e:
            logger.error(f"[LLM] インフォグラフィック生成失敗: {e}")
            return None

    @trace_llm(name="generate_manga_prompt", metadata={"purpose": "manga_prompt_generation"})
    def generate_manga_prompt(
        self,
        video_path: str,
        user_query: str,
        subtitle_texts: list[str] | None = None,
    ) -> str | None:
        """
        動画を分析して漫画生成プロンプトを作成

        Args:
            video_path: 結合動画ファイルのパス
            user_query: ユーザーの検索クエリ
            subtitle_texts: 字幕テキストのリスト（オプション）

        Returns:
            漫画生成用プロンプト（失敗時はNone）
        """
        logger.info(f"[LLM] 漫画プロンプト生成開始")
        logger.debug(f"  動画パス: {video_path}")
        logger.debug(f"  クエリ: {user_query!r}")

        # 字幕テキストを整形（先頭3000文字まで）
        subtitle_section = ""
        if subtitle_texts:
            combined_subtitles = "\n---\n".join(subtitle_texts)
            # 長すぎる場合は切り詰め
            if len(combined_subtitles) > 3000:
                combined_subtitles = combined_subtitles[:3000] + "..."
            subtitle_section = f"""

## 動画の字幕内容（重要な参考情報）
以下の字幕テキストから、クエリに関連する重要な情報を抽出してください：

{combined_subtitles}
"""

        prompt = f"""あなたは「情報デザイナー」兼「AIアートディレクター」です。
私が提供する【動画ファイル（複数クリップの結合）】と【調査クエリ】を元に、**画像生成AIでそのまま使える1ページの情報漫画プロンプト** を作成してください。

## 調査クエリ
{user_query}
{subtitle_section}

## あなたのタスク
1. **動画を分析**: 各クリップから、ユーザーのクエリに関連する重要な情報・ファクトを抽出する。
2. **情報を整理**: 抽出した情報を、漫画として伝わりやすい順序・構成に再編成する。
3. **漫画プロンプトを生成**: 下記のフォーマットに従い、1ページの漫画生成プロンプトを出力する。

## 制作要件
1. **出力形式**:
   - プロンプトの言語は **英語 (English)** だが、セリフ・テキスト指定のみ **日本語** とすること。
   - `Vertical 9:16 aspect ratio` を前提とした構成にすること。

2. **情報漫画の構成原則**:
   - **見出し（タイトル）**: クエリに対する答えが一目でわかるキャッチーなタイトル。
   - **導入**: 「なぜこの情報が重要か」を1コマで示す。
   - **本編**: 動画から抽出した3〜5個の重要ポイントを、各コマで視覚的に表現。
   - **結論/まとめ**: 読者が持ち帰れる「一言メッセージ」で締める。

3. **コマ構成ルール**:
   - 1ページに **5〜8コマ** を配置。
   - 情報の重要度に応じてコマのサイズを変える（重要＝大きく）。
   - アイコン、図解、比較表現を積極的に活用すること。
   - 視線誘導: 右上 → 左下（日本式）を意識。

## 出力テンプレート
以下のフォーマットで出力してください：

Generate a high-resolution professional Japanese manga page, FULL COLOR, Vertical 9:16 aspect ratio (Portrait), INFOGRAPHIC STYLE. --ar 9:16

# TOPIC
- Query: [ユーザーのクエリをここに記載]
- Key Insight: [動画から得られた最重要ポイント]

# PANEL LAYOUT & VISUALS (5-8 Panels, Top-Right to Bottom-Left)

Panel 1 (Top - Title Banner):
- Visual: [タイトルと目を引くビジュアル]
- Text: 「[キャッチーなタイトル]」

Panel 2 (Upper-Right):
- Visual: [導入・問題提起のビジュアル]
- Text: 「[なぜこれが重要か]」

Panel 3 (Upper-Left):
- Visual: [ポイント1のビジュアル・アイコン]
- Text: 「[ポイント1の説明]」

Panel 4 (Middle-Right):
- Visual: [ポイント2のビジュアル]
- Text: 「[ポイント2の説明]」

Panel 5 (Middle-Left):
- Visual: [ポイント3のビジュアル]
- Text: 「[ポイント3の説明]」

Panel 6 (Lower):
- Visual: [補足情報や比較図解]
- Text: 「[追加ポイント]」

Panel 7 (Bottom - Conclusion):
- Visual: [まとめのビジュアル、強調表現]
- Text: 「[結論・持ち帰りメッセージ]」

# STYLE
- Japanese Manga style, full color, infographic elements, clean design, bold text, icon-based visuals, high contrast, easy to read.

# SOURCE NOTES
- Based on: [動画の主な情報源・クリップの概要]

---

動画を分析し、上記フォーマットで漫画プロンプトを生成してください。プロンプトのみを出力してください。"""

        try:
            # 動画ファイルをアップロード
            video_file = self.client.files.upload(file=video_path)
            logger.debug(f"  ファイルアップロード完了: {video_file.name}")

            # ファイルがACTIVE状態になるまで待機
            import time
            start_time = time.time()
            while True:
                file_info = self.client.files.get(name=video_file.name)
                state = file_info.state.name if hasattr(file_info.state, 'name') else str(file_info.state)
                if state == "ACTIVE":
                    break
                if state == "FAILED" or time.time() - start_time > 120:
                    raise LLMError(f"File processing failed or timeout: {video_file.name}")
                time.sleep(1)

            # プロンプト生成
            response = self.client.models.generate_content(
                model=self.subtitle_analysis_model,  # テキスト生成なのでsubtitle_analysis_modelを使用
                contents=[video_file, prompt],
            )

            manga_prompt = response.text.strip()
            logger.info(f"[LLM] 漫画プロンプト生成完了: {len(manga_prompt)} chars")
            return manga_prompt

        except Exception as e:
            logger.error(f"[LLM] 漫画プロンプト生成失敗: {e}")
            return None

        finally:
            # アップロードしたファイルを削除
            try:
                self.client.files.delete(name=video_file.name)
            except Exception:
                pass

    @trace_llm(name="generate_manga_image", metadata={"purpose": "manga_image_generation"})
    def generate_manga_image(
        self,
        manga_prompt: str,
    ) -> bytes | None:
        """
        漫画プロンプトから画像を生成

        Args:
            manga_prompt: 漫画生成用プロンプト

        Returns:
            生成された画像のバイトデータ（失敗時はNone）
        """
        logger.info(f"[LLM] 漫画画像生成開始")
        logger.debug(f"  プロンプト長: {len(manga_prompt)} chars")
        logger.debug(f"  モデル: {self.image_generation_model}")

        try:
            # 画像生成（gemini-3-pro-image-preview用の設定）
            config = types.GenerateContentConfig(
                response_modalities=[Modality.TEXT, Modality.IMAGE],
                image_config=types.ImageConfig(
                    aspect_ratio="9:16",  # 縦長フォーマット
                    image_size="2K",
                ),
            )
            response = self.client.models.generate_content(
                model=self.image_generation_model,
                contents=[manga_prompt],
                config=config,
            )

            # 画像データを抽出
            image_parts = [part for part in response.parts if part.inline_data]
            if image_parts:
                image_data = image_parts[0].inline_data.data
                logger.info(f"[LLM] 漫画画像生成完了: {len(image_data)} bytes")
                return image_data

            logger.warning("[LLM] 画像データが見つかりません")
            return None

        except Exception as e:
            logger.error(f"[LLM] 漫画画像生成失敗: {e}")
            return None

    def generate_manga(
        self,
        video_path: str,
        user_query: str,
        subtitle_texts: list[str] | None = None,
    ) -> tuple[str | None, bytes | None]:
        """
        動画から漫画を生成（プロンプト生成 + 画像生成の統合メソッド）

        Args:
            video_path: 結合動画ファイルのパス
            user_query: ユーザーの検索クエリ
            subtitle_texts: 字幕テキストのリスト（オプション）

        Returns:
            (漫画プロンプト, 画像バイトデータ) のタプル
        """
        # Step 1: 漫画プロンプトを生成
        manga_prompt = self.generate_manga_prompt(video_path, user_query, subtitle_texts)
        if not manga_prompt:
            return None, None

        # Step 2: プロンプトから画像を生成
        image_data = self.generate_manga_image(manga_prompt)

        return manga_prompt, image_data
