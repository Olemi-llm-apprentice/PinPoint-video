# 🎯 PinPoint.video

An AI-powered tool that extracts specific segments from YouTube videos based on user queries and provides timestamped links for instant access.

**[日本語](./README_ja.md)** | **[中文](./README_zh.md)**

## 🎯 Problem Statement

- Wasting time watching a 20-minute video when you only need 40 seconds of information
- Difficulty finding specific topics in 2-hour conference recordings
- "I just want to know how to use this feature" in technical tutorials

## 🚀 Key Value

- **Time Savings**: 20 min → 40 sec (only the relevant parts)
- **Precision**: AI-powered content understanding, more accurate than subtitle search
- **Instant Access**: Timestamped YouTube links for immediate navigation

## 📋 Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- ffmpeg (video processing)
- yt-dlp (YouTube video extraction)

### System Dependencies Installation

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

## 🛠️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/Olemi-llm-apprentice/PinPoint-video.git
cd PinPoint-video
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit the `.env` file and set the following API keys:

- `YOUTUBE_API_KEY`: Enable YouTube Data API v3 at [Google Cloud Console](https://console.cloud.google.com/)
- `GEMINI_API_KEY`: Get from [Google AI Studio](https://aistudio.google.com/)

### 4. Run the application

```bash
uv run streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

## 📁 Project Structure

```
pinpoint_video/
├── app/
│   └── main.py                    # Streamlit entry point
├── src/
│   ├── domain/
│   │   ├── entities.py            # Video, Subtitle, TimeRange, SearchResult
│   │   ├── exceptions.py          # Domain-specific exceptions
│   │   └── time_utils.py          # Time conversion utilities
│   ├── application/
│   │   ├── interfaces/            # Protocol definitions
│   │   └── usecases/              # Use case implementations
│   └── infrastructure/
│       ├── youtube_data_api.py    # YouTube Data API v3
│       ├── youtube_transcript.py  # youtube-transcript-api
│       ├── ytdlp_extractor.py     # yt-dlp + ffmpeg
│       ├── gemini_llm_client.py   # Gemini Flash (text)
│       └── gemini_vlm_client.py   # Gemini Pro Vision (video)
├── config/
│   └── settings.py                # Settings management
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
├── .env.example
└── README.md
```

## 🔄 Processing Flow

1. **Query Conversion** (1-2s): Optimize user query for YouTube search
2. **YouTube Search** (1-2s): Search and filter relevant videos
3. **Subtitle Analysis** (2-3s): AI identifies rough time ranges from subtitles
4. **Precision Analysis** (10-30s/video): Partial download + VLM for precise timestamps
5. **Display Results**: YouTube embed with timestamps

**Total Processing Time**: 30 seconds to 1 minute

## 🧪 Running Tests

```bash
uv run pytest tests/
```

## 📝 Configuration Options

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `DEFAULT_MODEL` | gemini-2.5-flash | Default LLM model |
| `QUERY_CONVERT_MODEL` | (DEFAULT_MODEL) | Model for query conversion |
| `SUBTITLE_ANALYSIS_MODEL` | (DEFAULT_MODEL) | Model for subtitle analysis |
| `VIDEO_ANALYSIS_MODEL` | (DEFAULT_MODEL) | Model for video analysis (VLM) |
| `MAX_SEARCH_RESULTS` | 30 | Maximum YouTube search results |
| `MAX_FINAL_RESULTS` | 5 | Number of segments to display |
| `BUFFER_RATIO` | 0.2 | Buffer ratio for clip extraction |
| `ENABLE_VLM_REFINEMENT` | true | Enable/disable VLM precision analysis |
| `DURATION_MIN_SEC` | 60 | Minimum video length (seconds) |
| `DURATION_MAX_SEC` | 7200 | Maximum video length (seconds) |
| `PUBLISHED_AFTER` | - | Filter videos published after this date (ISO 8601) |
| `PUBLISHED_BEFORE` | - | Filter videos published before this date (ISO 8601) |

## ⚠️ Limitations

- Videos without subtitles cannot be processed (Whisper integration planned)
- Maximum video length: 1 hour (gemini-2.5-flash)
- Languages: Japanese and English only
- YouTube Data API daily quota limit (10,000 units/day)

## 📄 License

MIT License
