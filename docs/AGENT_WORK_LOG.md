# Agent Work Log

---

[2026-01-10 12:03:56]

## 作業内容

PinPoint.video プロジェクトの初期構築（uv環境）

### 実施した作業

- uvプロジェクト初期化とpyproject.toml作成
- クリーンアーキテクチャに基づくディレクトリ構造作成
- ドメイン層実装（entities, exceptions, time_utils）
- アプリケーション層 - Protocol定義（YouTubeSearcher, SubtitleFetcher, VideoExtractor, LLMClient, VLMClient）
- アプリケーション層 - ユースケース実装（ExtractSegmentsUseCase）
- インフラ層 - YouTube Data API クライアント
- インフラ層 - youtube-transcript-api クライアント（v1.2+対応）
- インフラ層 - Gemini LLM/VLM クライアント（google-genai SDK使用）
- インフラ層 - yt-dlp + ffmpeg 動画抽出
- 設定管理（pydantic-settings）
- Streamlit UI実装
- ユニットテスト作成（10テスト全パス）
- .env.example, README.md, .gitignore作成

### 追加機能実装

- LLMモデルを環境変数で設定可能に（DEFAULT_MODEL, QUERY_CONVERT_MODEL, SUBTITLE_ANALYSIS_MODEL, VIDEO_ANALYSIS_MODEL）
- 最大動画長を2時間（7200秒）に拡張
- 検索取得件数を30件に変更
- YouTube動画のアップロード日時範囲フィルター追加（PUBLISHED_AFTER, PUBLISHED_BEFORE）

### 変更したファイル

- `pyproject.toml` - 新規作成（依存関係定義）
- `app/main.py` - Streamlitエントリポイント
- `src/domain/entities.py` - Video, Subtitle, TimeRange等
- `src/domain/exceptions.py` - ドメイン例外
- `src/domain/time_utils.py` - 時間変換ユーティリティ
- `src/application/interfaces/*.py` - Protocol定義（5ファイル）
- `src/application/usecases/extract_segments.py` - メインユースケース
- `src/infrastructure/youtube_data_api.py` - YouTube API
- `src/infrastructure/youtube_transcript.py` - 字幕取得
- `src/infrastructure/gemini_llm_client.py` - Gemini LLM
- `src/infrastructure/gemini_vlm_client.py` - Gemini VLM
- `src/infrastructure/ytdlp_extractor.py` - 動画抽出
- `config/settings.py` - 設定管理
- `tests/unit/test_entities.py` - エンティティテスト
- `tests/unit/test_time_utils.py` - 時間変換テスト
- `.env.example` - 環境変数テンプレート
- `README.md` - プロジェクトドキュメント
- `.gitignore` - Git除外設定

### 備考

- 仕様書 `docs/pinpoint_video_spec_v1.1.md` に基づいて実装
- youtube-transcript-api v1.2+の新APIに対応
- google-genai SDK（旧google-generativeaiは2025/11/30でサポート終了）を使用

---

[2026-01-10 12:08:56]

## 作業内容

README多言語対応

### 実施した作業

- README.mdを英語版に書き換え
- 日本語版README（README_ja.md）を新規作成
- 中国語版README（README_zh.md）を新規作成
- 各READMEに他言語版へのリンクを追加

### 変更したファイル

- `README.md` - 英語版に書き換え、多言語リンク追加
- `README_ja.md` - 日本語版を新規作成
- `README_zh.md` - 中国語版を新規作成

### 備考

- メインREADMEは英語で記述し、日本語・中国語版は別ファイルとして参照する構成

---

[2026-01-10 13:30:00]

## 作業内容

YouTube検索の精度向上のためマルチクエリ・マルチ戦略検索を実装

### 背景・問題

- 「Claude Code 2.1.2の主な変更点」で検索しても結果が0件になる問題を調査
- YouTube Data APIの`relevance`順では新しい動画が出にくいことが判明
- LLMによるクエリ変換で日本語→英語にすると関連動画がヒットしなくなることが判明

### 実施した作業

1. **LLMクライアント拡張** (`gemini_llm_client.py`)
   - `generate_search_queries()` メソッド追加
   - 3種類のクエリを生成: original（そのまま）, optimized（英語最適化）, simplified（キーワード抽出）

2. **YouTubeクライアント拡張** (`youtube_data_api.py`)
   - `search_multi_strategy()` メソッド追加
   - 3パターンの検索戦略: relevance, date, relevance_recent（過去1ヶ月）
   - video_idによる重複排除を内蔵

3. **インターフェース更新**
   - `SearchQueryVariants` データクラス追加 (`llm_client.py`)
   - `MultiSearchResult` データクラス追加 (`youtube_searcher.py`)

4. **ユースケース更新** (`extract_segments.py`)
   - Phase 1: 複数クエリ生成（旧: 単一クエリ変換）
   - Phase 2: マルチ戦略検索（旧: 単一検索）
   - 重複排除後に字幕分析へ進む新フロー

### 変更したファイル

- `src/application/interfaces/llm_client.py` - SearchQueryVariants追加、generate_search_queries定義
- `src/application/interfaces/youtube_searcher.py` - MultiSearchResult追加、search_multi_strategy定義
- `src/infrastructure/gemini_llm_client.py` - generate_search_queries実装
- `src/infrastructure/youtube_data_api.py` - search_multi_strategy実装
- `src/application/usecases/extract_segments.py` - 新フロー統合

### テスト結果

- 改善前: 2026年1月の動画 0件
- 改善後: 2026年1月の動画 3件（relevance_recent戦略で取得）

### 備考

- 全ての処理でログ出力・LangSmithトレーシング対応済み
- 3クエリ × 3戦略 = 最大9回の検索を実行し、重複排除して母数を増やす設計

---

[2026-01-10 13:35:00]

## 作業内容

UI/UX改善とセッション履歴機能の実装

### 実施した作業

1. **詳細プログレス表示の実装**
   - `ProgressDetails`データクラス追加（phase, step, details）
   - 各処理フェーズで詳細情報を送信するように変更
   - フェーズ別アイコン表示（🔄🔍📝🎬✅）
   - 詳細ステータスexpanderでリアルタイム情報表示

2. **LangSmithトレース改善**
   - 毎回新しい`run_id`（UUID）を生成して上書き防止
   - 自動的にセッションID・タイムスタンプをmetadataに追加
   - `.env`ファイルの読み込み問題を修正（`load_dotenv()`追加）
   - `is_langsmith_enabled()`がSettingsから値を取得するように変更

3. **セッション履歴機能の実装**
   - `SessionStorage`クラス新規作成（履歴の永続化）
   - 各セッションごとに保存: metadata.json, result.json, result.md, log.txt, clips/
   - サイドバーに検索履歴一覧をChatGPT風に表示
   - 履歴選択で過去の結果を表示（結果/クリップ/ログ/Markdownタブ）
   - 動画クリップの保存オプション追加
   - 履歴の削除機能

4. **その他の修正**
   - `main.py`でプロジェクトルートをsys.pathに追加
   - `.gitignore`に`outputs/`ディレクトリを追加

### 変更したファイル

- `app/main.py` - 履歴UI、詳細プログレス表示、dotenv読み込み追加
- `src/application/usecases/extract_segments.py` - ProgressDetails追加、clip_save_callback追加
- `src/infrastructure/logging_config.py` - LangSmithトレース改善
- `src/infrastructure/session_storage.py` - 新規作成（履歴管理）
- `.gitignore` - outputs/追加
- `outputs/.gitkeep` - 新規作成

### 備考

- 検索結果は`outputs/`ディレクトリにセッションごとに保存される
- VLM精密分析時のクリップも保存可能（オプション）
- LangSmithトレースは毎回新しいIDで記録され、上書きされない

---

[2026-01-10 16:14:08]

## 作業内容

字幕取得429エラー時のYouTube URLフォールバック機能を実装

### 背景・問題

- YouTubeの字幕APIが429 (Too Many Requests) エラーを返すケースが発生
- レート制限により字幕取得が失敗すると、動画分析ができなくなる問題

### 実施した作業

1. **設定ファイル拡張** (`config/settings.py`)
   - `ENABLE_YOUTUBE_URL_FALLBACK` - フォールバック機能のオン/オフ設定
   - `YOUTUBE_URL_FALLBACK_MAX_DURATION` - フォールバック対象の最大動画長（デフォルト20分=1200秒）

2. **LLMクライアントインターフェース拡張** (`llm_client.py`)
   - `analyze_youtube_video()` メソッドをProtocolに追加

3. **Gemini LLMクライアント実装** (`gemini_llm_client.py`)
   - `analyze_youtube_video()` メソッド実装
   - `types.Part.from_uri()` でYouTube URLを直接Geminiに渡して動画を分析
   - 字幕と同様のJSON形式でセグメント情報を取得

4. **ユースケース拡張** (`extract_segments.py`)
   - `ExtractSegmentsConfig` にフォールバック設定を追加
   - `_should_use_youtube_url_fallback()` - フォールバック使用判定
   - `_process_with_youtube_url_fallback()` - フォールバック処理実行
   - `_process_single_video()` で字幕取得失敗時に自動的にフォールバックを試行

5. **設定の反映** (`app/main.py`)
   - `ExtractSegmentsConfig` にフォールバック設定を渡すように修正

6. **ドキュメント更新** (`.env.example`)
   - 新しい設定項目の説明を追加

### 変更したファイル

- `config/settings.py` - フォールバック設定を追加
- `src/application/interfaces/llm_client.py` - analyze_youtube_video メソッド追加
- `src/infrastructure/gemini_llm_client.py` - YouTube URL直接分析実装
- `src/application/usecases/extract_segments.py` - フォールバック処理追加
- `app/main.py` - 設定の反映
- `.env.example` - 新設定の説明追加

### 動作フロー

1. 字幕取得を試みる
2. 429エラー等で失敗した場合:
   - フォールバック機能が有効 (`ENABLE_YOUTUBE_URL_FALLBACK=true`) かつ
   - 動画長が20分以下の場合
   → Gemini 2.5にYouTube URLを直接渡して分析
3. 後続のVLM処理はそのまま実行

### 備考

- Gemini 2.5はYouTube URLを直接理解できるため、字幕なしでも動画内容を分析可能
- 動画長制限（20分）はGeminiの処理能力と精度を考慮した実用的な値
- 設定でオン/オフ可能なため、既存動作への影響なし

---

[2026-01-10 17:23:04]

## 作業内容

Gemini画像生成機能の実装（インフォグラフィック・漫画）

### 背景・要件

- 検索結果と結合動画（Final Clip）を入力として、視覚的なコンテンツを自動生成したい
- グラフィックインフォ（1枚スライド）と漫画の2種類を生成
- 新規検索後と過去ログタブの両方から実行可能にする

### 実施した作業

1. **設定ファイル拡張** (`config/settings.py`)
   - `IMAGE_GENERATION_MODEL` - 画像生成用モデル設定を追加（デフォルト: gemini-2.0-flash-exp）
   - `get_model()` メソッドに "image_generation" 用途を追加

2. **LLMクライアント拡張** (`gemini_llm_client.py`)
   - `__init__` に `image_generation_model` パラメータを追加
   - `generate_infographic()` - 動画とサマリーからインフォグラフィック画像を生成
   - `generate_manga_prompt()` - 動画からユーザー指定フォーマットの漫画プロンプトを生成
   - `generate_manga_image()` - プロンプトから漫画画像を生成
   - `generate_manga()` - プロンプト生成＋画像生成の統合メソッド
   - `response_modalities=["IMAGE", "TEXT"]` でGemini画像生成機能を使用

3. **セッションストレージ拡張** (`session_storage.py`)
   - `save_generated_image()` - 生成画像とプロンプトをセッションに保存
   - `get_generated_image()` - セッションの生成画像を取得
   - `get_all_generated_images()` - 全種類の生成画像を取得
   - 保存先: `outputs/<session_id>/generated_images/`

4. **Streamlit UI拡張** (`app/main.py`)
   - `generate_visual_content()` - 画像生成のヘルパー関数
   - 新規検索後: Final Clip結合成功時に自動で画像生成を実行（Phase 3として追加）
   - 履歴ビュー: 「🎨 ビジュアル」タブを追加
     - 生成済み画像の表示
     - 個別の再生成ボタン（インフォグラフィック / 漫画）
     - 画像ダウンロードボタン
     - 漫画プロンプトの表示

### 変更したファイル

- `config/settings.py` - IMAGE_GENERATION_MODEL 設定追加
- `src/infrastructure/gemini_llm_client.py` - 画像生成メソッド追加（4メソッド）
- `src/infrastructure/session_storage.py` - 画像保存・取得メソッド追加（3メソッド）
- `app/main.py` - ビジュアルコンテンツ生成UI追加

### 漫画プロンプト仕様

ユーザー指定のフォーマットに従い、以下の構成で出力:
- 縦長フォーマット（9:16）
- 日本式視線誘導（右上→左下）
- 5〜8コマ構成
- 英語プロンプト＋日本語セリフ
- タイトル→導入→本編（3-5ポイント）→結論の構成

### 備考

- Gemini 2.0 Flash Experimental を使用（画像生成対応モデル）
- 動画ファイルはGemini Files APIでアップロード後に分析
- 生成失敗時も検索結果は正常に保存される（エラーハンドリング実装済み）

---

[2026-01-10 17:30:00]

## 作業内容

画像生成モデルを gemini-3-pro-image-preview に更新

### 背景

- ユーザーから最新モデル `gemini-3-pro-image-preview` の存在を指摘
- Web検索でAPIリファレンスを確認し、正しい実装に修正

### gemini-3-pro-image-preview の特徴

- 2025年11月リリース（別名: Nano Banana Pro）
- 4K解像度対応
- テキストレンダリング改善
- マルチモーダル入出力対応
- 会話的な画像編集が可能
- 注: `gemini-2.5-flash-image-preview` は 2026/1/15 でシャットダウン予定

### 実施した作業

1. **設定ファイル修正** (`config/settings.py`)
   - デフォルトモデルを `gemini-3-pro-image-preview` に変更

2. **LLMクライアント修正** (`gemini_llm_client.py`)
   - `GenerateContentConfig` と `Modality` を正式にインポート
   - 画像生成設定を `Modality.TEXT, Modality.IMAGE` enum を使用するように修正
   - テキストレスポンスもログ出力するように追加

### 変更したファイル

- `config/settings.py` - デフォルトモデル変更
- `src/infrastructure/gemini_llm_client.py` - API呼び出し形式を修正

### API使用方法（修正後）

```python
from google.genai.types import GenerateContentConfig, Modality

config = GenerateContentConfig(
    response_modalities=[Modality.TEXT, Modality.IMAGE],
)
response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[video_file, prompt],
    config=config,
)
```

---
