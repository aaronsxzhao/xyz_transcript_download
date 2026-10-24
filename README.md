# AI Podcast & Video Notes Tool

**播客与视频笔记工具** — Transcribe, summarize, and generate structured notes from podcasts and videos across multiple platforms.

---

## What It Does

Transform podcast episodes and videos into:
- **Full transcripts** with timestamps
- **AI-generated summaries** with key insights, topics, and takeaways
- **Video notes** with screenshots, table of contents, and markdown export
- **Export** to PDF, Markdown, Notion, and clipboard

Works locally or in the cloud with multi-user support.

---

## Supported Platforms

### Podcasts
| Platform | Features |
|----------|----------|
| **小宇宙 (Xiaoyuzhou)** | Subscribe, auto-discover episodes, process with transcript + summary |
| **Apple Podcasts** | Add via URL, fetch episodes from RSS feed, process with transcript + summary |

### Videos
| Platform | Features |
|----------|----------|
| **YouTube** | Channel subscription, auto-discover new videos, generate notes with screenshots |
| **Bilibili** | Channel subscription, auto-discover, generate notes |
| **Douyin / TikTok** | Process individual videos |
| **Kuaishou** | Process individual videos |

---

## Quick Start

### Option A: Cloud Version

1. Visit the deployed web app: https://aipodcastsummary.online/
2. Sign in with your account
3. Add podcasts or paste video URLs
4. Process and read summaries / notes online

### Option B: Run Locally

#### 1. Setup

```bash
cd xyz_transcript_download

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Install FFmpeg (required for audio/video processing)
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

# Optional: Whisper settings
WHISPER_MODE=local
WHISPER_LOCAL_MODEL=small
```

#### 3. Start the Web Interface

```bash
cd web && npm install && cd ..
python main.py serve
```

Open http://localhost:5173 in your browser.

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Platform Podcasts** | Xiaoyuzhou and Apple Podcasts with platform-specific icons |
| **Multi-Platform Videos** | YouTube, Bilibili, Douyin, Kuaishou |
| **Channel Subscriptions** | Subscribe to channels, auto-discover new episodes/videos |
| **Audio Transcription** | Whisper-powered (local or Groq cloud API) |
| **AI Summarization** | Key points, topics, takeaways, original quotes |
| **Video Notes** | Screenshots, TOC, summary, markdown — configurable styles |
| **Notion Integration** | Export notes directly to Notion |
| **Web UI** | Modern React interface with dark theme |
| **Real-time Progress** | WebSocket + polling fallback for live updates |
| **Processing Queue** | Dashboard shows active jobs for both podcasts and videos |
| **Model Selection** | Choose Whisper and LLM models in settings |
| **Default Settings** | Configure default video processing options (style, quality, formats) |
| **Cloud Deployment** | Deploy to Oracle Cloud / Render with Supabase storage |
| **Multi-User** | Each user has isolated data via Supabase RLS |
| **Export** | PDF, Markdown, copy-to-clipboard, Notion |

---

## Web Interface

Hosted app: https://aipodcastsummary.online/

```bash
python main.py serve
```

### Pages

| Page | Features |
|------|----------|
| **Dashboard** | Stats, quick process form (videos + podcasts), processing queue, recent summaries and video notes |
| **Podcasts** | Platform view, subscribe/unsubscribe, search, check for updates, process episodes |
| **Episodes** | View all episodes for a podcast, process individually, see transcript/summary status |
| **Videos** | Platform → Channel → Video hierarchy, search, check for updates, process/retry |
| **Video Note Viewer** | Read notes with screenshots, export to PDF/MD/Notion, copy to clipboard |
| **Summary Viewer** | Read podcast summaries with topic grouping, export to PDF/MD/Notion |
| **Settings** | Whisper/LLM model config, video processing defaults, account cookies, data maintenance |

**URLs:**
- Hosted Web App: https://aipodcastsummary.online/
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

---

## Configuration

### Whisper (Transcription)

| Setting | Options | Description |
|---------|---------|-------------|
| `WHISPER_MODE` | `local`, `api` | Use local Whisper or cloud API (Groq) |
| `WHISPER_BACKEND` | `auto`, `mlx-whisper`, `faster-whisper` | Transcription engine |
| `WHISPER_LOCAL_MODEL` | `tiny`, `small`, `medium`, `large-v3` | Model size (local mode) |

**Recommended for Apple Silicon (M1/M2/M3/M4):**
```bash
WHISPER_BACKEND=mlx-whisper
WHISPER_LOCAL_MODEL=large-v3
```

**Recommended for Cloud:**
```bash
WHISPER_MODE=api
GROQ_API_KEY=your-groq-key
```

### LLM (Summarization)

If `GROQ_API_KEY` is configured, the web app uses it for both transcription and
summaries by default (`openai/gpt-oss-120b`). No OpenAI API key is required.
In **Settings → General → LLM Configuration**, use **Test and save summaries**
to verify the connection. Choose **Server configured provider** to use the
`LLM_*` configuration below instead. These preferences are saved per account;
API keys stay on the server. ChatGPT subscriptions do not include OpenAI API credits.

To use your own provider, select **My OpenAI-compatible service** separately for
transcription and summaries. Enter the API root (for example,
`https://api.example.com/v1`), API key, and exact model ID. The model list is read
from that endpoint; providers without a `/models` API support manual model IDs.
Use **Test summary** or **Test transcription**, then **Save Settings**. Tests use
synthetic input and can incur a small provider charge. Summary models must support
JSON chat completions; transcription requires the audio transcription API with
verbose JSON and segment timestamps. A successful small test does not guarantee
that every model supports the context/output capacity of a long recording.

Keys are encrypted per account and never returned by Settings or stored in browser
preferences. Blank password fields keep a saved key; use the explicit removal
action and save to remove it. Changing the Base URL requires re-entering the key.
Cloud endpoints must use HTTPS and be publicly reachable. Existing saved outputs
are retained; configured services receive content when a new processing request
requires them (valid transcripts or source subtitles may be reused).

For deployment, credential encryption uses `MODEL_CREDENTIAL_KEY` when supplied,
otherwise a key derived from `SUPABASE_SERVICE_KEY`; local installations use a
private key file in the persistent data directory. Keep the encryption secret/data
directory stable and backed up. Rotating it requires users to re-enter model keys.

Markdown downloads preserve source formatting and use absolute screenshot links.
Signed media URLs retain their original expiry; the `.md` file does not embed images
or extend access indefinitely.

Summary delivery prioritizes an available result. Editorial coverage checks run
once per source chunk; a failed check returns the generated draft with a visible
notice. Failed chunks retain clearly labelled original transcript sections, and
an outline merge failure preserves the generated sections. Unmatched quotations
are left empty rather than presented as verified original speech. Cancellation
still stops processing, and a request that generated no usable content still
reports failure. Notices remain in saved/exported reading content.

Groq token and request limits depend on your plan. Long recordings are split to
fit the model's context window while preserving the full summary prompts.
Groq summary models use
transcripts; optional video frame analysis needs a vision-capable provider.

```bash
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

Compatible with any OpenAI-compatible API (OpenAI, Azure, LiteLLM, OpenRouter, Vertex AI, etc.)

### Video Platform Cookies

For YouTube, Bilibili, and Douyin, you can set login cookies in the Settings page to access member-only or restricted content. Cookies are stored per-platform and used automatically during video processing.

---

## Cloud Deployment

### Oracle Cloud (ARM Container Instance)

The project includes a GitHub Actions workflow (`.github/workflows/deploy-oracle.yml`) that:
1. Builds an ARM64 Docker image
2. Pushes to Oracle Container Registry (OCIR)
3. Restarts the container instance
4. Verifies health

Deploys are triggered automatically on push to `main` when build-relevant files change (Python, frontend, Dockerfile, dependencies). Use `workflow_dispatch` for manual deploys.

Deployment succeeds only when the public health endpoint reports the exact
commit built into the image. A failed restart, unhealthy API, or old image causes
the workflow to fail. Merge release pull requests after both backend and frontend
checks pass.

### Supabase Setup (Multi-User Storage)

1. Create a project at [supabase.com](https://supabase.com)
2. Run `supabase_schema.sql` in the SQL Editor
3. Configure authentication settings
4. Set environment variables:

```bash
USE_SUPABASE=true
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
# Optional: stop uploading screenshots/thumbnails to Supabase Storage
# and keep using Supabase only for auth/database.
# SUPABASE_STORAGE_ENABLED=false
```

If your Supabase free plan is running out of Storage, the biggest contributors are usually video screenshots and generated thumbnails. You can inspect buckets with:

```bash
./venv/bin/python scripts/manage_supabase_storage.py
```

And if you want to reclaim space immediately:

```bash
./venv/bin/python scripts/manage_supabase_storage.py --empty screenshots --empty thumbnails --yes
```

Or delete orphaned screenshots/thumbnails older than 21 days:

```bash
./venv/bin/python scripts/manage_supabase_storage.py --cleanup-expired 21 --yes
```

The API server also runs this cleanup automatically every 6 hours. Images belonging to saved video notes and their versions are retained. Only orphaned screenshots/thumbnails older than 21 days are removed. Cleanup skips deletion if it cannot check the saved task inventory. You can tune the orphan retention with `GENERATED_MEDIA_RETENTION_DAYS` and `GENERATED_MEDIA_CLEANUP_INTERVAL_HOURS`.

Supabase usage on the billing page is averaged across the billing period and refreshes hourly, so the chart may not drop immediately after cleanup.

---

## Data Storage

### Upgrading an existing cloud deployment

Before deploying the account-isolation fixes, run
`supabase/migrations/20261018114840_account_isolation.sql` in the Supabase SQL Editor.
It adds account-owned cookies and model preferences, makes summary replacement
transactional, and closes access to legacy shared cookies. This step is compatible
with the previous API. Deploy the updated backend and frontend next, then make
generated image buckets private:

```sql
UPDATE storage.buckets SET public = FALSE WHERE id IN ('screenshots', 'thumbnails');
```

Run that final step only after the new API is live, so existing image previews
continue working during deployment. New installations can use the updated
`supabase_schema.sql`, which configures private buckets immediately.

Users must reconnect their platform accounts after this upgrade. Shared cookies
are retained for administrative recovery but are never reused for another account.
Cloud Notion exports require each user's integration token in Settings.

Generated images use file-specific links for previews and exports, valid for the
configured media-retention period. The signing key is derived from the configured
Supabase service key, so links work across replicas and restarts. An optional
`MEDIA_SIGNING_KEY` can provide a separate stable secret; use the same value on
every replica. Rotating either signing secret invalidates existing image links;
reopen the note to get fresh links.

### Local Mode (Default)

```
data/
├── audio/          # Downloaded audio files
├── video/          # Downloaded video files
├── transcripts/    # Transcript JSON files
├── summaries/      # Summary JSON files
├── screenshots/    # Video screenshots
├── logs/           # Application logs
└── xyz.db          # SQLite database
```

### Cloud Mode (Supabase)

- All data stored in PostgreSQL
- User isolation via Row Level Security
- Accessible from any device
- Persists across server restarts

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│       React Frontend (Vite + Tailwind CSS)       │
├─────────────────────────────────────────────────┤
│  FastAPI Backend (WebSocket + REST API)          │
├──────────────────┬──────────────────────────────┤
│  Podcast Engine  │  Video Engine                │
│  - xyz_client    │  - video_downloader (yt-dlp) │
│  - apple_client  │  - note_summarizer           │
│  - downloader    │  - screenshot_extractor      │
│  - transcriber   │  - cookie_manager            │
│  - summarizer    │                              │
├──────────────────┴──────────────────────────────┤
│         Database Abstraction Layer (api/db.py)   │
├──────────────────┬──────────────────────────────┤
│  SQLite (Local)  │  Supabase (Cloud/PostgreSQL) │
└──────────────────┴──────────────────────────────┘
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port already in use | `lsof -i :8000` then `kill -9 <PID>` |
| FFmpeg not found | `brew install ffmpeg` (macOS) |
| Transcription fails | Check FFmpeg installation, try a smaller Whisper model |
| Summary quality poor | Try a different LLM model in Settings |
| Video download fails | Set platform cookies in Settings |
| Apple Podcast won't add | Some Apple-exclusive shows have no public RSS feed |
| Cloud data lost | Enable Supabase for persistent storage |
| Processing stuck | Check server logs; stuck jobs auto-recover on restart |

---

## License

MIT

---

## Contributing

Run the backend and frontend regression suites before submitting changes:

```bash
python -m pytest
cd web
npm ci
npm test
npm run build
```

Tests use temporary data and mocked provider responses. Live platform downloads,
AI providers, Notion, and native desktop packaging need their own configured
integration checks.

Issues and PRs welcome! This tool is actively maintained.
