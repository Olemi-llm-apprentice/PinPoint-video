# 🎯 PinPoint.video

YouTube動画から、ユーザーが求める情報が含まれる部分だけをピンポイントで抽出し、タイムスタンプ付きリンクとして提供するAIツール。

**[English](./README.md)** | **[中文](./README_zh.md)**

## 🎯 解決する課題

- 20分の動画の中で、必要な情報は40秒しかないのに、全編を視聴する時間の無駄
- 2時間のカンファレンス動画から特定のトピックを探す困難さ
- 技術チュートリアル動画で「この機能の使い方だけ知りたい」というニーズ

## 🚀 主要な価値

- **時間短縮**: 20分 → 40秒（必要な部分だけ）
- **精度**: AIによる内容理解で、字幕検索より高精度
- **即座にアクセス**: タイムスタンプ付きYouTubeリンクで即座に該当部分へ
- **統合サマリー**: 複数のセグメントを1つのまとめにAIが統合
- **Final Clip**: 全セグメントを1つの動画ファイルに自動結合
- **ビジュアルコンテンツ**: 検索結果からインフォグラフィック・漫画をAI生成

## 📋 必要条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Pythonパッケージマネージャー)
- ffmpeg (動画処理)
- yt-dlp (YouTube動画ダウンロード)

### システム依存のインストール

**Windows (winget):**
```powershell
winget install ffmpeg
pip install yt-dlp
```

**macOS (Homebrew):**
```bash
brew install ffmpeg yt-dlp
```

**Linux (apt):**
```bash
sudo apt-get install ffmpeg
pip install yt-dlp
```

## 🛠️ セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/Olemi-llm-apprentice/PinPoint-video.git
cd PinPoint-video
```

### 2. 依存関係をインストール

```bash
uv sync
```

### 3. 環境変数を設定

```bash
cp .env.example .env
```

`.env` ファイルを編集して、以下のAPIキーを設定してください：

#### 必須のAPIキー

| APIキー | 取得方法 | 用途 |
|---------|----------|------|
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → YouTube Data API v3を有効化 | YouTube動画検索 |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | AI分析（LLM + VLM） |

#### オプションのAPIキー

| APIキー | 取得方法 | 用途 |
|---------|----------|------|
| `LANGSMITH_API_KEY` | [LangSmith](https://smith.langchain.com/settings) | 観測性・トレーシング |

> ⚠️ **注意**: YouTube Data APIには日次クォータ制限があります（10,000ユニット/日）。1回の検索で約100ユニット消費します。

### 4. アプリケーションを起動

```bash
uv run streamlit run app/main.py
```

ブラウザで http://localhost:8501 を開いてください。

## 📁 プロジェクト構成

```
pinpoint_video/
├── app/
│   └── main.py                    # Streamlit エントリポイント
├── src/
│   ├── domain/
│   │   ├── entities.py            # Video, Subtitle, TimeRange, SearchResult
│   │   ├── exceptions.py          # ドメイン固有の例外
│   │   └── time_utils.py          # 時間変換ユーティリティ
│   ├── application/
│   │   ├── interfaces/            # Protocol定義
│   │   └── usecases/              # ユースケース実装
│   └── infrastructure/
│       ├── youtube_data_api.py    # YouTube Data API v3
│       ├── youtube_transcript.py  # youtube-transcript-api
│       ├── ytdlp_extractor.py     # yt-dlp + ffmpeg
│       ├── gemini_llm_client.py   # Gemini Flash (テキスト)
│       └── gemini_vlm_client.py   # Gemini Pro Vision (動画)
├── config/
│   └── settings.py                # 設定管理
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
├── .env.example
└── README.md
```

## 🔄 処理フロー

1. **クエリ変換** (1-2秒): LLMでユーザークエリをYouTube検索に最適化
2. **マルチ戦略YouTube検索** (2-3秒): 複数のクエリと戦略（関連度、日付、最新）で検索
3. **タイトルフィルタリング** (1-2秒): LLMで動画タイトルの関連性を評価
4. **字幕分析** (2-5秒): AIで字幕から該当範囲を粗く特定
5. **VLM精密分析** (10-30秒/動画): 最大3並列で処理
   - 該当部分のみ部分ダウンロード
   - Gemini VLMで実際の動画内容を分析
   - 失敗時は自動リトライ（最大3回）
6. **結果生成**:
   - 個別セグメント結果（タイムスタンプ付き）
   - **統合サマリー**: AIが全セグメントのサマリーを1つに統合
   - **Final Clip**: 全クリップを1つの動画ファイルに結合

**合計処理時間**: 30秒〜2分（セグメント数により変動）

## 📂 出力フォルダ構成

検索結果は `outputs/` ディレクトリに保存されます：

```
outputs/
└── 20260110_153324_検索クエリ/
    ├── result.json          # 検索結果（セグメント、タイムスタンプ、サマリー）
    ├── result.md            # Markdown形式の結果
    ├── metadata.json        # セッションメタデータ
    ├── queries.json         # 生成された検索クエリ
    ├── integrated_summary.txt  # AI生成の統合サマリー
    ├── log.txt              # 処理ログ
    ├── final_clip.mp4       # 全セグメントの結合動画
    ├── clips/               # 個別の動画クリップ
    │   ├── videoId_seg0.mp4
    │   └── videoId_seg1.mp4
    ├── subtitles/           # ダウンロードした字幕
    │   └── videoId.json
    └── generated_images/    # AI生成ビジュアルコンテンツ
        ├── infographic.png
        └── manga.png
```

## 🧪 テスト実行

```bash
uv run pytest tests/
```

## 📝 設定オプション

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `DEFAULT_MODEL` | gemini-2.5-flash | デフォルトLLMモデル |
| `QUERY_CONVERT_MODEL` | (DEFAULT_MODEL) | クエリ変換用モデル |
| `SUBTITLE_ANALYSIS_MODEL` | (DEFAULT_MODEL) | 字幕分析用モデル |
| `VIDEO_ANALYSIS_MODEL` | (DEFAULT_MODEL) | 動画分析用モデル（VLM） |
| `IMAGE_GENERATION_MODEL` | gemini-3-pro-image-preview | 画像生成用モデル |
| `MAX_SEARCH_RESULTS` | 30 | YouTube検索結果の最大取得件数 |
| `MAX_FINAL_RESULTS` | 5 | 最終的に表示するセグメント数 |
| `BUFFER_RATIO` | 0.2 | クリップ抽出時のバッファ割合 |
| `ENABLE_VLM_REFINEMENT` | true | VLM精密分析の有効/無効 |
| `DURATION_MIN_SEC` | 60 | 対象動画の最小長さ（秒） |
| `DURATION_MAX_SEC` | 7200 | 対象動画の最大長さ（秒） |
| `PUBLISHED_AFTER` | - | この日時以降の動画のみ（ISO 8601形式） |
| `PUBLISHED_BEFORE` | - | この日時以前の動画のみ（ISO 8601形式） |

## ⚠️ 制限事項

- 字幕なし動画は処理不可
- 動画長上限: 2時間（ソース動画）。Geminiは個別クリップを処理（音声あり約45分 / 音声なし約1時間）
- 言語: 日本語・英語が主にサポート
- YouTube Data API の日次クォータ制限（10,000ユニット/日）
- 非常に短いクリップ（3秒未満）はVLM分析が失敗する可能性あり

## 📄 ライセンス

MIT License
