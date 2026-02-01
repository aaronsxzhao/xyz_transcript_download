# 小宇宙播客转录与摘要工具

一款强大的播客转录和 AI 摘要工具，专为小宇宙 FM 播客设计。

---

## 功能亮点

### 核心功能
- **完整转录** - 将播客音频转换为带时间戳的文字稿
- **AI 智能摘要** - 自动提取关键观点、主题和金句
- **播客订阅** - 订阅喜欢的播客，自动检测新剧集
- **批量处理** - 一键处理整个播客的所有剧集
- **多格式导出** - 支持 HTML、Markdown、JSON 格式导出

### Web 界面
- **仪表盘** - 统计数据、最近摘要、处理队列一览
- **播客管理** - 订阅/取消订阅、刷新剧集列表
- **剧集浏览** - 查看处理状态、一键处理新剧集
- **摘要阅读器** - 分主题浏览、展开详情、导出分享
- **实时进度** - WebSocket 实时更新处理进度
- **深色主题** - 现代化界面设计，支持响应式布局

### 转录能力
- **云端 API** - 使用 Groq Whisper API，快速稳定
- **模型选择** - 支持 `whisper-large-v3` 和 `whisper-large-v3-turbo` 两种模型
  - `whisper-large-v3`: 更精准，速度较慢
  - `whisper-large-v3-turbo`: 更快速，精度略低
- **智能分段** - 自动识别对话段落，添加时间戳
- **长音频处理** - 自动分片处理超长播客

### 摘要能力
- **多模型支持** - 支持 20+ 种大语言模型
  - OpenRouter: GPT-4o, GPT-5, Claude Sonnet 4/4.5, Gemini 2.5, Grok 3/4 等
  - Vertex AI: Gemini 2.5/3.0 系列
  - 直连: Gemini Flash/Pro (Firebase)
- **深度分析** - 提取关键观点、主题分类、收听建议
- **原文引用** - 每个观点附带原文引用，有据可查
- **分段摘要** - 长播客自动分段摘要，完整覆盖

---

## 快速开始

### 在线使用

直接访问已部署的 Web 服务，无需安装：

1. 打开网站并登录
2. 粘贴小宇宙剧集链接
3. 点击"处理"按钮
4. 等待转录和摘要完成
5. 在线阅读或导出

### 本地部署

#### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd xyz_transcript_download

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装 FFmpeg（音频处理必需）
brew install ffmpeg  # macOS
# 或: sudo apt install ffmpeg  # Ubuntu
```

#### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# LLM 摘要服务（必需）
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Whisper 转录服务
WHISPER_MODE=api          # 使用云端 API
GROQ_API_KEY=your-groq-key  # Groq API 密钥（免费）
```

#### 3. 启动服务

```bash
python main.py serve
```

打开浏览器访问 http://localhost:5173

---

## 使用指南

### 处理单个剧集

1. 复制小宇宙剧集分享链接，例如：
   ```
   https://www.xiaoyuzhoufm.com/episode/xxxxx
   ```

2. 在 Web 界面粘贴链接，点击"处理"

3. 等待处理完成（根据时长，通常 5-15 分钟）

4. 查看转录文稿和 AI 摘要

### 订阅播客

1. 进入"播客"页面
2. 点击"添加播客"
3. 粘贴播客主页链接
4. 系统自动获取所有剧集列表
5. 选择要处理的剧集

### 批量处理

1. 订阅播客后，进入剧集列表
2. 选择多个剧集
3. 点击"批量处理"
4. 系统按队列依次处理

### 查看摘要

摘要包含以下内容：

- **概览** - 剧集主题和核心内容
- **关键观点** - 分主题整理的要点
- **原文引用** - 支持每个观点的原话
- **主题标签** - 便于分类和检索
- **收听建议** - 听众可能的收获

### 设置调整

在"设置"页面可以：

- **Whisper 模型** - 选择转录模型
  - `whisper-large-v3`: 更精准
  - `whisper-large-v3-turbo`: 更快速

- **LLM 模型** - 选择摘要模型
  - 可选 GPT、Claude、Gemini、Grok 等多种模型

- **数据维护** - 检查和清理不完整的转录

---

## 命令行工具

除了 Web 界面，还支持命令行操作：

### 基础命令

| 命令 | 说明 |
|------|------|
| `python main.py process <url>` | 处理单个剧集 |
| `python main.py serve` | 启动 Web 服务 |
| `python main.py view --list` | 列出所有摘要 |
| `python main.py view <id>` | 查看摘要 |

### 播客管理

| 命令 | 说明 |
|------|------|
| `python main.py add <url>` | 订阅播客 |
| `python main.py list` | 列出已订阅播客 |
| `python main.py remove <name>` | 取消订阅 |
| `python main.py episodes <name>` | 列出剧集 |

### 批量处理

| 命令 | 说明 |
|------|------|
| `python main.py batch <url>` | 批量处理所有剧集 |
| `python main.py batch <url> -n 5` | 只处理最新 5 集 |
| `python main.py batch <url> --skip-existing` | 跳过已处理剧集 |

### 后台服务

| 命令 | 说明 |
|------|------|
| `python main.py start` | 启动后台守护进程 |
| `python main.py stop` | 停止守护进程 |
| `python main.py status` | 查看运行状态 |
| `python main.py check` | 手动检查新剧集 |

---

## 支持的模型

### Whisper 转录模型

| 模型 | 说明 |
|------|------|
| `whisper-large-v3` | 更精准，适合重要内容 |
| `whisper-large-v3-turbo` | 更快速，日常使用推荐 |

### LLM 摘要模型

#### OpenRouter 系列
- `openrouter/openai/gpt-4o` - GPT-4o
- `openrouter/openai/gpt-5-chat` - GPT-5
- `openrouter/openai/gpt-5-mini` - GPT-5 Mini
- `openrouter/openai/o3-mini` - O3 Mini
- `openrouter/anthropic/claude-sonnet-4` - Claude Sonnet 4
- `openrouter/anthropic/claude-sonnet-4.5` - Claude Sonnet 4.5
- `openrouter/google/gemini-2.5-flash` - Gemini 2.5 Flash
- `openrouter/google/gemini-2.5-pro` - Gemini 2.5 Pro
- `openrouter/x-ai/grok-3-mini` - Grok 3 Mini
- `openrouter/x-ai/grok-4` - Grok 4
- `openrouter/x-ai/grok-4-fast` - Grok 4 Fast

#### Vertex AI 系列
- `vertex_ai/gemini-2.5-flash` - Gemini 2.5 Flash
- `vertex_ai/gemini-2.5-flash-image` - Gemini 2.5 Flash Image
- `vertex_ai/gemini-2.5-flash-lite` - Gemini 2.5 Flash Lite
- `vertex_ai/gemini-2.5-pro` - Gemini 2.5 Pro
- `vertex_ai/gemini-3-pro-preview` - Gemini 3 Pro Preview
- `vertex_ai/gemini-3-flash-preview` - Gemini 3 Flash Preview

#### Firebase 直连
- `gemini-2.5-flash-fb` - Gemini 2.5 Flash
- `gemini-2.5-pro-fb` - Gemini 2.5 Pro

---

## 云端部署

### Render.com 部署

1. Fork 本仓库到你的 GitHub

2. 在 [Render.com](https://render.com) 创建新的 Web Service

3. 设置环境变量：
   ```bash
   # LLM 配置
   LLM_API_KEY=your-key
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4o

   # Whisper 配置（云端使用 API 模式）
   WHISPER_MODE=api
   GROQ_API_KEY=your-groq-key

   # Supabase 配置（数据持久化）
   USE_SUPABASE=true
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_KEY=your-anon-key
   SUPABASE_SERVICE_KEY=your-service-key
   ```

4. 部署完成后即可使用

### Supabase 配置（多用户支持）

1. 在 [supabase.com](https://supabase.com) 创建项目

2. 在 SQL Editor 运行 `supabase_schema.sql`

3. 配置 Authentication URL

4. 将 API 密钥添加到环境变量

---

## 数据存储

### 本地模式

```
data/
├── audio/          # 下载的音频文件
├── transcripts/    # 转录 JSON 文件
├── summaries/      # 摘要 JSON 文件
├── logs/           # 应用日志
└── xyz.db          # SQLite 数据库
```

### 云端模式

- 所有数据存储在 Supabase PostgreSQL
- 通过 Row Level Security 实现用户数据隔离
- 支持多设备访问
- 服务重启后数据不丢失

---

## 常见问题

### 处理失败怎么办？

1. 检查网络连接
2. 确认 API 密钥有效
3. 查看错误信息，对症处理
4. 点击"重试"按钮

### 转录不完整？

- 在设置页面使用"数据维护"功能
- 检查并清理不完整的转录
- 重新处理该剧集

### 摘要质量不满意？

- 尝试更换 LLM 模型
- 使用"重新摘要"功能
- GPT-4o 和 Claude Sonnet 4.5 通常效果最好

### 处理很慢？

- 使用 `whisper-large-v3-turbo` 模型加速转录
- 选择更快的 LLM 模型（如 Gemini Flash）
- 长播客需要更多时间，请耐心等待

### 如何导出摘要？

- 在摘要页面点击"导出 HTML"
- 生成的 HTML 文件可在浏览器打开
- 也可复制文本到其他应用

---

## 技术架构

```
┌─────────────────────────────────────────────┐
│          React 前端 (Vite + Tailwind)        │
├─────────────────────────────────────────────┤
│            FastAPI 后端                      │
├─────────────────────────────────────────────┤
│           数据库抽象层 (api/db.py)           │
├────────────────────┬────────────────────────┤
│  SQLite (本地)      │  Supabase (云端)        │
└────────────────────┴────────────────────────┘
```

**核心组件：**
- `main.py` - CLI 入口
- `transcriber.py` - Whisper 转录服务
- `summarizer.py` - LLM 摘要服务
- `api/` - FastAPI 后端
- `web/` - React 前端

---

## 反馈与支持

如有问题或建议，欢迎提交 Issue 或 Pull Request。

---

## 许可证

MIT License
