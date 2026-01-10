# 🎯 PinPoint.video

一款AI驱动的工具，可根据用户查询从YouTube视频中提取特定片段，并提供带时间戳的链接以便即时访问。

**[English](./README.md)** | **[日本語](./README_ja.md)**

## 🎯 解决的问题

- 为了获取40秒的信息，却要浪费时间观看20分钟的视频
- 难以在2小时的会议录像中找到特定主题
- 在技术教程视频中"我只想知道如何使用这个功能"的需求

## 🚀 核心价值

- **节省时间**: 20分钟 → 40秒（仅相关部分）
- **精准度**: AI理解内容，比字幕搜索更准确
- **即时访问**: 带时间戳的YouTube链接，立即跳转到相关部分

## 📋 系统要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python包管理器)
- ffmpeg (视频处理)
- yt-dlp (YouTube视频提取)

### 系统依赖安装

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

## 🛠️ 安装配置

### 1. 克隆仓库

```bash
git clone https://github.com/Olemi-llm-apprentice/PinPoint-video.git
cd PinPoint-video
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置以下API密钥：

- `YOUTUBE_API_KEY`: 在 [Google Cloud Console](https://console.cloud.google.com/) 启用YouTube Data API v3后获取
- `GEMINI_API_KEY`: 从 [Google AI Studio](https://aistudio.google.com/) 获取

### 4. 运行应用

```bash
uv run streamlit run app/main.py
```

在浏览器中打开 http://localhost:8501。

## 📁 项目结构

```
pinpoint_video/
├── app/
│   └── main.py                    # Streamlit 入口
├── src/
│   ├── domain/
│   │   ├── entities.py            # Video, Subtitle, TimeRange, SearchResult
│   │   ├── exceptions.py          # 领域特定异常
│   │   └── time_utils.py          # 时间转换工具
│   ├── application/
│   │   ├── interfaces/            # Protocol定义
│   │   └── usecases/              # 用例实现
│   └── infrastructure/
│       ├── youtube_data_api.py    # YouTube Data API v3
│       ├── youtube_transcript.py  # youtube-transcript-api
│       ├── ytdlp_extractor.py     # yt-dlp + ffmpeg
│       ├── gemini_llm_client.py   # Gemini Flash (文本)
│       └── gemini_vlm_client.py   # Gemini Pro Vision (视频)
├── config/
│   └── settings.py                # 配置管理
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
├── .env.example
└── README.md
```

## 🔄 处理流程

1. **查询转换** (1-2秒): 优化用户查询以适应YouTube搜索
2. **YouTube搜索** (1-2秒): 搜索并筛选相关视频
3. **字幕分析** (2-3秒): AI从字幕中识别大致时间范围
4. **精确分析** (10-30秒/视频): 部分下载 + VLM精确定位时间戳
5. **显示结果**: 带时间戳的YouTube嵌入播放器

**总处理时间**: 30秒至1分钟

## 🧪 运行测试

```bash
uv run pytest tests/
```

## 📝 配置选项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DEFAULT_MODEL` | gemini-2.5-flash | 默认LLM模型 |
| `QUERY_CONVERT_MODEL` | (DEFAULT_MODEL) | 查询转换模型 |
| `SUBTITLE_ANALYSIS_MODEL` | (DEFAULT_MODEL) | 字幕分析模型 |
| `VIDEO_ANALYSIS_MODEL` | (DEFAULT_MODEL) | 视频分析模型（VLM） |
| `MAX_SEARCH_RESULTS` | 30 | YouTube搜索结果最大数量 |
| `MAX_FINAL_RESULTS` | 5 | 显示的片段数量 |
| `BUFFER_RATIO` | 0.2 | 片段提取缓冲比例 |
| `ENABLE_VLM_REFINEMENT` | true | 启用/禁用VLM精确分析 |
| `DURATION_MIN_SEC` | 60 | 最小视频长度（秒） |
| `DURATION_MAX_SEC` | 7200 | 最大视频长度（秒） |
| `PUBLISHED_AFTER` | - | 仅搜索此日期之后发布的视频（ISO 8601格式） |
| `PUBLISHED_BEFORE` | - | 仅搜索此日期之前发布的视频（ISO 8601格式） |

## ⚠️ 限制

- 无法处理没有字幕的视频（计划集成Whisper）
- 最大视频长度：1小时（gemini-2.5-flash）
- 语言：仅支持日语和英语
- YouTube Data API每日配额限制（10,000单位/天）

## 📄 许可证

MIT License
