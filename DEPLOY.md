# Deploy to Cloud (Free Hosting)

This guide will help you deploy the app so you can access it from your iPhone anywhere.

## Choose a Platform

| Platform | Credit Card Required | Free Tier |
|----------|---------------------|-----------|
| **Render.com** | No | 750 hours/month |
| **Zeabur** | No | Limited |
| Fly.io | Yes | 3 VMs |

## Prerequisites

1. Groq API key (free): https://console.groq.com/keys
2. Your LLM API key (for summarization)
3. GitHub account (for Render)

---

# Option 1: Render.com (No Credit Card)

## Step 1: Prepare Your Code

```bash
# Build frontend first
cd web && npm install && npm run build && cd ..
```

## Step 2: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
# Create a repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/xyz-podcast.git
git push -u origin main
```

## Step 3: Deploy on Render

1. Go to https://dashboard.render.com
2. Click **New** → **Web Service**
3. Connect your GitHub repo
4. Settings:
   - **Name**: xyz-podcast
   - **Runtime**: Docker
   - **Plan**: Free
5. Add Environment Variables:
   - `GROQ_API_KEY` = your-groq-key
   - `LLM_API_KEY` = your-llm-key  
   - `LLM_BASE_URL` = https://duet-litellm-api.winktech.net/v1
   - `LLM_MODEL` = gemini-2.5-pro
6. Click **Create Web Service**

Your app will be at: `https://xyz-podcast.onrender.com`

---

# Option 2: Fly.io (Requires Credit Card)

## Step 1: Install Fly CLI

```bash
# macOS
brew install flyctl

# Or download from https://fly.io/docs/hands-on/install-flyctl/
```

## Step 2: Login to Fly.io

```bash
fly auth login
```

This will open a browser to sign up/login.

## Step 3: Get API Keys

### Groq API Key (Free - for transcription)
1. Go to https://console.groq.com/keys
2. Create a free account
3. Click "Create API Key"
4. Copy the key

### LLM API Key (for summarization)
Use your existing LiteLLM API key.

## Step 4: Build Frontend

```bash
cd web
npm install
npm run build
cd ..
```

## Step 5: Deploy

```bash
# First time: Create the app
fly launch --no-deploy

# Create persistent storage for your data
fly volumes create xyz_data --size 1

# Set your API keys as secrets
fly secrets set GROQ_API_KEY=your-groq-key-here
fly secrets set LLM_API_KEY=your-llm-api-key-here
fly secrets set LLM_BASE_URL=https://your-litellm-endpoint/v1
fly secrets set LLM_MODEL=your-model-name

# Deploy!
fly deploy
```

## Step 6: Access Your App

After deployment, Fly will give you a URL like:
```
https://xyz-podcast.fly.dev
```

Open this URL on your iPhone and bookmark it!

## Managing Your App

```bash
# Check status
fly status

# View logs
fly logs

# Open in browser
fly open

# SSH into the container
fly ssh console

# Scale up if needed (costs money beyond free tier)
fly scale memory 1024
```

## Costs

- **Fly.io Free Tier**: 3 shared VMs, enough for this app
- **Groq Whisper**: Free tier (limited requests, then ~$0.001/min)
- **Storage**: 1GB free, then $0.15/GB/month

## Troubleshooting

### App won't start
```bash
fly logs
```

### Out of memory
Increase memory (may exit free tier):
```bash
fly scale memory 1024
```

### Data not persisting
Check volume is mounted:
```bash
fly volumes list
```

## Updating

After making changes locally:
```bash
# Rebuild frontend
cd web && npm run build && cd ..

# Deploy update
fly deploy
```

## Alternative: Run Locally with Cloudflare Tunnel

If you want to keep everything on your laptop but access from phone:

```bash
# Install cloudflared
brew install cloudflared

# Start the app
python main.py serve --api-only --port 8000

# In another terminal, create tunnel
cloudflared tunnel --url http://localhost:8000
```

This gives you a temporary public URL. For permanent access, set up a Cloudflare Tunnel with a custom domain.
