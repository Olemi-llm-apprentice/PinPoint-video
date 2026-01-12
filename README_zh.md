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
- **综合摘要**: AI将所有相关片段整合成一份摘要
- **最终剪辑**: 自动将所有相关片段合并成一个视频文件
- **视觉内容**: 从搜索结果生成AI信息图和漫画

## 📋 系统要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python包管理器)
- ffmpeg (视频处理)

### 系统依赖安装

**Windows (winget):**
```powershell
winget install ffmpeg
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Linux (apt):**
```bash
sudo apt-get install ffmpeg
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

#### 必需的API密钥

| API密钥 | 获取方式 | 用途 |
|---------|----------|------|
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → 启用YouTube Data API v3 | YouTube视频搜索 |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) | AI分析（LLM + VLM） |

#### 可选的API密钥

| API密钥 | 获取方式 | 用途 |
|---------|----------|------|
| `LANGSMITH_API_KEY` | [LangSmith](https://smith.langchain.com/settings) | 可观测性和追踪 |

> ⚠️ **注意**: YouTube Data API有每日配额限制（10,000单位/天）。每次搜索约消耗100单位。

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

1. **查询转换** (1-2秒): 使用LLM优化用户查询以适应YouTube搜索
2. **多策略YouTube搜索** (2-3秒): 使用多个查询和策略（相关性、日期、最新）进行搜索
3. **标题过滤** (1-2秒): LLM按标题相关性过滤视频
4. **字幕分析** (2-5秒): AI从字幕中识别大致时间范围
5. **VLM精确分析** (10-30秒/视频): 最多3个并行处理
   - 仅下载相关部分
   - Gemini VLM分析实际视频内容
   - 失败时自动重试（最多3次）
6. **结果生成**:
   - 带时间戳的单独片段结果
   - **综合摘要**: AI将所有片段摘要整合为一份
   - **最终剪辑**: 所有片段合并成一个视频文件

**总处理时间**: 30秒至2分钟（取决于片段数量）

## 📂 输出结构

搜索结果保存到 `outputs/` 目录：

```
outputs/
└── 20260110_153324_search_query/
    ├── result.json          # 搜索结果（片段、时间戳、摘要）
    ├── result.md            # Markdown格式结果
    ├── metadata.json        # 会话元数据
    ├── queries.json         # 生成的搜索查询
    ├── integrated_summary.txt  # AI生成的综合摘要
    ├── log.txt              # 处理日志
    ├── final_clip.mp4       # 所有片段的合并视频
    ├── clips/               # 单独的视频片段
    │   ├── videoId_seg0.mp4
    │   └── videoId_seg1.mp4
    ├── subtitles/           # 下载的字幕
    │   └── videoId.json
    └── generated_images/    # AI生成的视觉内容
        ├── infographic.png
        └── manga.png
```

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
| `IMAGE_GENERATION_MODEL` | gemini-3-pro-image-preview | 图像生成模型 |
| `MAX_SEARCH_RESULTS` | 30 | YouTube搜索结果最大数量 |
| `MAX_FINAL_RESULTS` | 5 | 显示的片段数量 |
| `BUFFER_RATIO` | 0.2 | 片段提取缓冲比例 |
| `ENABLE_VLM_REFINEMENT` | true | 启用/禁用VLM精确分析 |
| `DURATION_MIN_SEC` | 60 | 最小视频长度（秒） |
| `DURATION_MAX_SEC` | 7200 | 最大视频长度（秒） |
| `PUBLISHED_AFTER` | - | 仅搜索此日期之后发布的视频（ISO 8601格式） |
| `PUBLISHED_BEFORE` | - | 仅搜索此日期之前发布的视频（ISO 8601格式） |

## ⚠️ 限制

- 无法处理没有字幕的视频
- 最大视频长度：2小时（源视频）。Gemini处理单独片段（有音频约45分钟 / 无音频约1小时）
- 语言：主要支持日语和英语
- YouTube Data API每日配额限制（10,000单位/天）
- 非常短的片段（<3秒）可能导致VLM分析失败

## 📄 许可证

MIT License
