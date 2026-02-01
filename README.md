# Xiaoyuzhou Podcast Transcript & Summary Tool

**小宇宙播客转录与摘要工具** - Automatically transcribe and summarize Chinese podcasts from Xiaoyuzhou FM.

---

## What It Does

Transform any Xiaoyuzhou podcast episode into:
- **Full transcript** with timestamps
- **AI-generated summary** with key insights
- **Topic highlights** and takeaways
- **Original quotes** for reference

Works locally or in the cloud with multi-user support.

---

## Quick Start

### Option A: Use the Cloud Version

1. Visit the deployed web service
2. Sign in with your account
3. Paste a Xiaoyuzhou episode URL
4. Click "Process" and wait for results
5. Read online or export to HTML

### Option B: Run Locally

#### 1. Setup (One-time)

```bash
# Clone and enter the project
cd xyz_transcript_download

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (required for audio processing)
brew install ffmpeg  # macOS
# or: sudo apt install ffmpeg  # Ubuntu
```

#### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```bash
# Required: LLM for summarization
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Optional: Whisper settings (defaults work fine)
WHISPER_MODE=local
WHISPER_LOCAL_MODEL=small
```

#### 3. Process Your First Episode

```bash
# Paste any episode URL from Xiaoyuzhou
python main.py process "https://www.xiaoyuzhoufm.com/episode/xxx"
```

This will:
1. Download the audio
2. Transcribe it using Whisper
3. Generate an AI summary
4. Auto-subscribe to the podcast

#### 4. View Results

**Option A: Command Line**
```bash
python main.py view --list              # List all summaries
python main.py view <episode_id>        # View in terminal
python main.py view <episode_id> -f html # Open in browser
```

**Option B: Web Interface**
```bash
cd web && npm install && cd ..  # First time only
python main.py serve
```

Open http://localhost:5173 in your browser.

---

## Features

| Feature | Description |
|---------|-------------|
| **Podcast Subscription** | Subscribe to podcasts, auto-detect new episodes |
| **Audio Transcription** | Whisper-powered (local or cloud API) |
| **AI Summarization** | Key points, topics, takeaways, quotes |
| **Web UI** | Modern React interface with dark theme |
| **Model Selection** | Choose Whisper and LLM models in settings |
| **Real-time Progress** | WebSocket-based live progress updates |
| **Cloud Deployment** | Deploy to Render.com with Supabase storage |
| **Multi-User** | Each user has isolated data (Supabase) |
| **Export** | HTML, Markdown, JSON formats |

---

## Web Interface

The web UI provides a visual way to manage podcasts and view summaries.

```bash
python main.py serve
```

### Pages

| Page | Features |
|------|----------|
| **Dashboard** | Stats, quick process form, recent summaries |
| **Podcasts** | Subscribe/unsubscribe, refresh episodes |
| **Episodes** | View all episodes, process individually |
| **Viewer** | Read summaries with topic grouping, export HTML |
| **Settings** | Configure models, data maintenance |

### Settings Page

The Settings page allows you to configure:

- **Whisper Model** - Choose transcription model:
  - `whisper-large-v3` - More accurate, slower
  - `whisper-large-v3-turbo` - Faster, slightly less accurate

- **LLM Model** - Choose from 20+ summarization models (see below)

- **Data Maintenance** - Check for and clean up incomplete transcripts

**URLs:**
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

---

## Supported Models

### Whisper Models (Transcription)

| Model | Description |
|-------|-------------|
| `whisper-large-v3` | Higher accuracy, recommended for important content |
| `whisper-large-v3-turbo` | Faster processing, good for daily use |

### LLM Models (Summarization)

Select any of these models in the Settings page:

#### OpenRouter
| Model | Description |
|-------|-------------|
| `openrouter/openai/gpt-4o` | GPT-4o |
| `openrouter/openai/gpt-5-chat` | GPT-5 |
| `openrouter/openai/gpt-5-mini` | GPT-5 Mini |
| `openrouter/openai/o3-mini` | O3 Mini |
| `openrouter/anthropic/claude-sonnet-4` | Claude Sonnet 4 |
| `openrouter/anthropic/claude-sonnet-4.5` | Claude Sonnet 4.5 |
| `openrouter/google/gemini-2.5-flash` | Gemini 2.5 Flash |
| `openrouter/google/gemini-2.5-pro` | Gemini 2.5 Pro |
| `openrouter/x-ai/grok-3-mini` | Grok 3 Mini |
| `openrouter/x-ai/grok-4` | Grok 4 |
| `openrouter/x-ai/grok-4-fast` | Grok 4 Fast |

#### Vertex AI
| Model | Description |
|-------|-------------|
| `vertex_ai/gemini-2.5-flash` | Gemini 2.5 Flash |
| `vertex_ai/gemini-2.5-flash-image` | Gemini 2.5 Flash Image |
| `vertex_ai/gemini-2.5-flash-lite` | Gemini 2.5 Flash Lite |
| `vertex_ai/gemini-2.5-flash-lite-preview-09-2025` | Flash Lite Preview |
| `vertex_ai/gemini-2.5-pro` | Gemini 2.5 Pro |
| `vertex_ai/gemini-3-pro-preview` | Gemini 3 Pro Preview |
| `vertex_ai/gemini-3-flash-preview` | Gemini 3 Flash Preview |

#### Firebase Direct
| Model | Description |
|-------|-------------|
| `gemini-2.5-flash-fb` | Gemini 2.5 Flash |
| `gemini-2.5-pro-fb` | Gemini 2.5 Pro |

---

## Command Reference

### Essential Commands

| Command | Description |
|---------|-------------|
| `process <url>` | Process an episode (download + transcribe + summarize) |
| `serve` | Start the web interface |
| `view --list` | List all available summaries |
| `view <id>` | View a summary |

### Podcast Management

| Command | Description |
|---------|-------------|
| `add <url>` | Subscribe to a podcast |
| `list` | Show subscribed podcasts |
| `remove <name>` | Unsubscribe |
| `episodes <name>` | List episodes of a podcast |

### Batch Processing

| Command | Description |
|---------|-------------|
| `batch <url>` | Process all episodes of a podcast |
| `batch <url> -n 5` | Process only the latest 5 |
| `batch <url> --skip-existing` | Skip already processed episodes |

### Background Daemon

| Command | Description |
|---------|-------------|
| `start` | Start auto-update daemon |
| `stop` | Stop daemon |
| `status` | Check daemon status |
| `check` | Manually check for new episodes |

---

## Configuration

### Whisper (Transcription)

| Setting | Options | Description |
|---------|---------|-------------|
| `WHISPER_MODE` | `local`, `api` | Use local Whisper or cloud API (Groq) |
| `WHISPER_BACKEND` | `auto`, `mlx-whisper`, `faster-whisper` | Transcription engine |
| `WHISPER_LOCAL_MODEL` | `tiny`, `small`, `medium`, `large-v3` | Model size (local mode) |

**Recommended for Apple Silicon (M1/M2/M3):**
```bash
WHISPER_BACKEND=mlx-whisper
WHISPER_LOCAL_MODEL=large-v3
```

**Recommended for Cloud (Render.com):**
```bash
WHISPER_MODE=api
GROQ_API_KEY=your-groq-key
```

### LLM (Summarization)

```bash
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

Compatible with any OpenAI-compatible API (OpenAI, Azure, LiteLLM, OpenRouter, etc.)

---

## Cloud Deployment

### Deploy to Render.com

1. **Fork** this repo to your GitHub

2. **Create** a new Web Service on [Render.com](https://render.com)

3. **Set Environment Variables:**

```bash
# LLM
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Whisper (use Groq API for cloud - no local GPU)
WHISPER_MODE=api
GROQ_API_KEY=your-groq-key

# Supabase (for persistent storage)
USE_SUPABASE=true
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
```

4. **Deploy** - Render will auto-deploy on each git push

### Supabase Setup (Multi-User Storage)

1. Create a project at [supabase.com](https://supabase.com)
2. Run `supabase_schema.sql` in the SQL Editor
3. Set your Render URL in Authentication > URL Configuration
4. Copy API keys to Render environment variables

---

## Data Storage

### Local Mode (Default)

```
data/
├── audio/          # Downloaded audio files
├── transcripts/    # Transcript JSON files
├── summaries/      # Summary JSON files
├── logs/           # Application logs
└── xyz.db          # SQLite database
```

### Cloud Mode (Supabase)

- All data stored in PostgreSQL
- User isolation via Row Level Security
- Accessible from any device
- Persists across server restarts

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `command not found: python` | Use `python3` or activate venv |
| Port already in use | `lsof -i :8000` then `kill -9 <PID>` |
| FFmpeg not found | `brew install ffmpeg` (macOS) |
| Transcription fails | Check FFmpeg, try smaller model |
| Summary fails | Check LLM API key and network |
| Cloud data lost | Enable Supabase for persistence |
| Slow Render deploy | Use `WHISPER_MODE=api` to skip torch |
| Incomplete transcript | Use Settings > Data Maintenance to clean up |
| Summary quality poor | Try a different LLM model in Settings |

### Stopping the Server

Use `Ctrl+C`, not `Ctrl+Z`:
- `Ctrl+C` = Stop and release port
- `Ctrl+Z` = Suspend (port stays occupied)

If you used `Ctrl+Z`:
```bash
fg %1      # Bring back to foreground
# Then Ctrl+C
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│       React Frontend (Vite + Tailwind)      │
├─────────────────────────────────────────────┤
│            FastAPI Backend                  │
├─────────────────────────────────────────────┤
│         Database Abstraction Layer          │
│              (api/db.py)                    │
├────────────────────┬────────────────────────┤
│  SQLite (Local)    │  Supabase (Cloud)      │
└────────────────────┴────────────────────────┘
```

**Key Components:**
- `main.py` - CLI entry point
- `transcriber.py` - Whisper integration (local + API)
- `summarizer.py` - LLM summarization (20+ models)
- `api/db.py` - Unified database interface
- `web/` - React frontend with settings UI

---

## License

MIT

---

## Contributing

Issues and PRs welcome! This tool is actively maintained.

---

## 中文文档

查看 [README_CN.md](README_CN.md) 获取中文版说明文档。
