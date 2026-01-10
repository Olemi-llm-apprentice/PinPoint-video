# 🎯 PinPoint.video

YouTube動画から、ユーザーが求める情報が含まれる部分だけをピンポイントで抽出し、タイムスタンプ付きリンクとして提供するAIツール。

## 🎯 解決する課題

- 20分の動画の中で、必要な情報は40秒しかないのに、全編を視聴する時間の無駄
- 2時間のカンファレンス動画から特定のトピックを探す困難さ
- 技術チュートリアル動画で「この機能の使い方だけ知りたい」というニーズ

## 🚀 主要な価値

- **時間短縮**: 20分 → 40秒（必要な部分だけ）
- **精度**: AIによる内容理解で、字幕検索より高精度
- **即座にアクセス**: タイムスタンプ付きYouTubeリンクで即座に該当部分へ

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
git clone https://github.com/yourusername/pinpoint-video.git
cd pinpoint-video
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

- `YOUTUBE_API_KEY`: [Google Cloud Console](https://console.cloud.google.com/)でYouTube Data API v3を有効化して取得
- `GEMINI_API_KEY`: [Google AI Studio](https://aistudio.google.com/)で取得

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

1. **クエリ変換** (1-2秒): ユーザークエリをYouTube検索に最適化
2. **YouTube検索** (1-2秒): 関連動画を検索・フィルタリング
3. **字幕分析** (2-3秒): 字幕からAIで該当範囲を粗く特定
4. **精密分析** (10-30秒/動画): 部分ダウンロード + VLMで精密時刻特定
5. **結果表示**: タイムスタンプ付きYouTube埋め込み

**合計処理時間**: 30秒〜1分

## 🧪 テスト実行

```bash
uv run pytest tests/
```

## 📝 設定オプション

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `MAX_SEARCH_RESULTS` | 10 | YouTube検索結果の最大取得件数 |
| `MAX_FINAL_RESULTS` | 5 | 最終的に表示するセグメント数 |
| `BUFFER_RATIO` | 0.2 | クリップ抽出時のバッファ割合 |
| `ENABLE_VLM_REFINEMENT` | true | VLM精密分析の有効/無効 |
| `DURATION_MIN_SEC` | 60 | 対象動画の最小長さ（秒） |
| `DURATION_MAX_SEC` | 1800 | 対象動画の最大長さ（秒） |

## ⚠️ 制限事項

- 字幕なし動画は処理不可（将来Whisper統合予定）
- 動画長上限: 1時間（gemini-2.5-flash）
- 言語: 日本語・英語のみ
- YouTube Data API の日次クォータ制限（10,000ユニット/日）

## 📄 ライセンス

MIT License
