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
- **Integrated Summary**: AI-generated summary combining all relevant segments
- **Final Clip**: Automatically combined video clip of all relevant segments
- **Visual Content**: AI-generated infographics and manga from search results

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

#### Required API Keys

| API Key | How to Get | Purpose |
|---------|------------|---------|
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → Enable YouTube Data API v3 | Search YouTube videos |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | AI analysis (LLM + VLM) |

#### Optional API Keys

| API Key | How to Get | Purpose |
|---------|------------|---------|
| `LANGSMITH_API_KEY` | [LangSmith](https://smith.langchain.com/settings) | Observability & tracing |

> ⚠️ **Note**: YouTube Data API has a daily quota limit (10,000 units/day). Each search uses about 100 units.

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

1. **Query Conversion** (1-2s): Optimize user query for YouTube search using LLM
2. **Multi-Strategy YouTube Search** (2-3s): Search with multiple queries and strategies (relevance, date, recent)
3. **Title Filtering** (1-2s): LLM filters videos by title relevance
4. **Subtitle Analysis** (2-5s): AI identifies rough time ranges from subtitles
5. **VLM Precision Analysis** (10-30s/video): Parallel processing with up to 3 concurrent analyses
   - Partial video download (only relevant segments)
   - Gemini VLM analyzes actual video content
   - Automatic retry on failure (up to 3 times)
6. **Results Generation**:
   - Individual segment results with timestamps
   - **Integrated Summary**: AI combines all segment summaries into one
   - **Final Clip**: All clips merged into a single video file

**Total Processing Time**: 30 seconds to 2 minutes (depending on number of segments)

## 📂 Output Structure

Search results are saved to the `outputs/` directory:

```
outputs/
└── 20260110_153324_search_query/
    ├── result.json          # Search results (segments, timestamps, summaries)
    ├── result.md            # Markdown format results
    ├── metadata.json        # Session metadata
    ├── queries.json         # Generated search queries
    ├── integrated_summary.txt  # AI-generated combined summary
    ├── log.txt              # Processing log
    ├── final_clip.mp4       # Combined video of all segments
    ├── clips/               # Individual video clips
    │   ├── videoId_seg0.mp4
    │   └── videoId_seg1.mp4
    ├── subtitles/           # Downloaded subtitles
    │   └── videoId.json
    └── generated_images/    # AI-generated visual content
        ├── infographic.png
        └── manga.png
```

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
| `IMAGE_GENERATION_MODEL` | gemini-3-pro-image-preview | Model for image generation |
| `MAX_SEARCH_RESULTS` | 30 | Maximum YouTube search results |
| `MAX_FINAL_RESULTS` | 5 | Number of segments to display |
| `BUFFER_RATIO` | 0.2 | Buffer ratio for clip extraction |
| `ENABLE_VLM_REFINEMENT` | true | Enable/disable VLM precision analysis |
| `DURATION_MIN_SEC` | 60 | Minimum video length (seconds) |
| `DURATION_MAX_SEC` | 7200 | Maximum video length (seconds) |
| `PUBLISHED_AFTER` | - | Filter videos published after this date (ISO 8601) |
| `PUBLISHED_BEFORE` | - | Filter videos published before this date (ISO 8601) |

## ⚠️ Limitations

- Videos without subtitles cannot be processed
- Maximum video length: 2 hours (source video). Gemini processes individual clips (~45 min with audio / ~1 hour without audio per clip)
- Languages: Japanese and English primarily supported
- YouTube Data API daily quota limit (10,000 units/day)
- VLM analysis may fail for very short clips (< 3 seconds)

## 📄 License

MIT License
