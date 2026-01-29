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

### 1. Setup (One-time)

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

### 2. Configure

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

### 3. Process Your First Episode

```bash
# Paste any episode URL from Xiaoyuzhou
python main.py process "https://www.xiaoyuzhoufm.com/episode/xxx"
```

This will:
1. Download the audio
2. Transcribe it using Whisper
3. Generate an AI summary
4. Auto-subscribe to the podcast

### 4. View Results

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
| **Web UI** | Modern React interface for browsing |
| **Cloud Deployment** | Deploy to Render.com with Supabase storage |
| **Multi-User** | Each user has isolated data (Supabase) |
| **Export** | HTML, Markdown, JSON formats |

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

## Web Interface

The web UI provides a visual way to manage podcasts and view summaries.

```bash
python main.py serve
```

**Features:**
- Dashboard with stats and recent summaries
- Podcast subscription management
- Episode list with processing status
- Summary viewer with topic grouping
- Real-time processing progress
- HTML export for sharing

**URLs:**
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

---

## Configuration

### Whisper (Transcription)

| Setting | Options | Description |
|---------|---------|-------------|
| `WHISPER_MODE` | `local`, `api` | Use local Whisper or cloud API (Groq) |
| `WHISPER_BACKEND` | `auto`, `mlx-whisper`, `faster-whisper` | Transcription engine |
| `WHISPER_LOCAL_MODEL` | `tiny`, `small`, `medium`, `large-v3` | Model size |

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

Compatible with any OpenAI-compatible API (OpenAI, Azure, LiteLLM, etc.)

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
│          React Frontend (Vite)              │
├─────────────────────────────────────────────┤
│           FastAPI Backend                   │
├─────────────────────────────────────────────┤
│         Database Abstraction Layer          │
│              (api/db.py)                    │
├────────────────────┬────────────────────────┤
│  SQLite (Local)    │  Supabase (Cloud)      │
└────────────────────┴────────────────────────┘
```

**Key Components:**
- `main.py` - CLI entry point
- `transcriber.py` - Whisper integration
- `summarizer.py` - LLM summarization
- `api/db.py` - Unified database interface
- `web/` - React frontend

---

## License

MIT

---

## Contributing

Issues and PRs welcome! This tool is actively maintained.
