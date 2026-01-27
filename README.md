# 小宇宙播客转录与摘要工具

Xiaoyuzhou Podcast Transcript & Summary Tool

自动下载小宇宙播客、生成逐字稿、并使用 AI 生成摘要和关键点提取。

## 功能特点

- 🎙️ 订阅并自动监控小宇宙播客更新
- 📥 自动下载播客音频（支持断点续传）
- 📝 使用 Whisper 生成中文逐字稿（支持本地或 API）
- 🤖 使用 LLM 生成摘要、关键点和原文引用
- 🔄 后台守护进程自动处理新节目
- 🌐 **Web UI** - 现代化的 Web 界面管理播客和查看摘要

---

## 快速开始

### 1. 创建虚拟环境

```bash
# 进入项目目录
cd /Users/aaronz/Downloads/xyz_transcript_download

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境（每次使用都需要执行）
source venv/bin/activate
```

> 💡 **提示**: 激活成功后，终端提示符前会显示 `(venv)`

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 FFmpeg

FFmpeg 用于处理音频文件，是必须的依赖。

```bash
# macOS (使用 Homebrew)
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# 验证安装
ffmpeg -version
```

### 4. 配置环境变量

复制示例配置文件并编辑：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少配置 LLM API（用于生成摘要）：

```bash
# LLM API 配置（必填）
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Whisper 配置（默认即可）
WHISPER_MODE=local
WHISPER_LOCAL_MODEL=small
```

---

## 新手教程：从零开始处理一期播客

按照以下步骤，5分钟内完成你的第一次播客转录和摘要！

### 步骤 1: 激活环境

```bash
cd /Users/aaronz/Downloads/xyz_transcript_download
source venv/bin/activate
```

### 步骤 2: 处理一期节目

从小宇宙 App 或网站复制一期节目的链接，然后运行：

```bash
python main.py process "https://www.xiaoyuzhoufm.com/episode/xxx"
```

这个命令会自动：
1. ✅ 下载音频文件
2. ✅ 使用 Whisper 生成逐字稿
3. ✅ 使用 LLM 生成摘要和关键点
4. ✅ 自动订阅该节目所属的播客

### 步骤 3: 查看结果

```bash
# 列出所有已生成的摘要
python main.py view --list

# 查看摘要详情（使用上面列出的 episode_id）
python main.py view <episode_id>

# 或导出为 HTML 在浏览器中打开
python main.py view <episode_id> -f html
```

### 步骤 4: 启动 Web UI（可选）

如果你更喜欢图形界面：

```bash
# 首次运行需要安装前端依赖
cd web && npm install && cd ..

# 启动 Web 应用
python main.py serve
```

打开浏览器访问：
- **前端界面**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs

> ⚠️ **停止服务器**: 按 `Ctrl+C`（不是 `Ctrl+Z`！`Ctrl+Z` 只会暂停进程，不会释放端口）

---

## 常用命令详解

### 订阅播客

```bash
# 订阅一个播客
python main.py add "https://www.xiaoyuzhoufm.com/podcast/xxx"

# 查看已订阅的播客列表
python main.py list

# 取消订阅
python main.py remove "播客名称"
```

### 处理节目

```bash
# 处理单期节目（推荐方式）
python main.py process "https://www.xiaoyuzhoufm.com/episode/xxx"

# 批量处理整个播客
python main.py batch "https://www.xiaoyuzhoufm.com/podcast/xxx"

# 批量处理选项：
python main.py batch "URL" -n 5              # 只处理最新 5 集
python main.py batch "URL" --skip-existing   # 跳过已有摘要的节目
python main.py batch "URL" --transcribe-only # 只转录，不生成摘要
python main.py batch "URL" -y                # 跳过确认直接开始
```

### 查看摘要

```bash
# 列出所有可用的摘要
python main.py view --list

# 终端美观显示
python main.py view <episode_id>

# 紧凑模式
python main.py view <episode_id> --compact

# 导出为 Markdown
python main.py view <episode_id> -f markdown -o summary.md

# 导出为 HTML（自动在浏览器打开）
python main.py view <episode_id> -f html
```

### 后台自动更新

```bash
# 启动后台守护进程（自动监控新节目）
python main.py start

# 前台运行（可以看到日志输出）
python main.py start -f

# 查看守护进程状态
python main.py status

# 停止守护进程
python main.py stop

# 手动检查所有订阅的播客是否有新节目
python main.py check
```

### 数据维护

```bash
# 检查数据一致性（推荐定期运行）
python main.py check-data

# 自动修复数据问题
python main.py check-data --fix

# 整理孤立的节目文件到正确的播客目录
python main.py organize
```

### Web 界面

```bash
# 启动完整 Web 应用（前端 + API）
python main.py serve

# 仅启动 API 服务器（不启动前端）
python main.py serve --api-only

# 指定端口
python main.py serve --port 9000
```

---

## 命令速查表

| 命令 | 说明 |
|------|------|
| `add <url>` | 订阅播客 |
| `remove <name>` | 取消订阅 |
| `list` | 列出已订阅播客 |
| `episodes <name>` | 列出播客节目 |
| `process <url>` | 处理单期节目（下载+转录+摘要） |
| `batch <url>` | 批量处理整个播客 |
| `view --list` | 列出所有摘要 |
| `view <id>` | 查看摘要详情 |
| `view <id> -f html` | 导出为 HTML |
| `serve` | 启动 Web UI |
| `start` | 启动后台守护进程 |
| `stop` | 停止后台守护进程 |
| `status` | 查看状态 |
| `check` | 手动检查新节目 |
| `check-data` | 检查数据一致性 |
| `check-data --fix` | 修复数据问题 |
| `organize` | 整理孤立文件 |

---

## 配置说明

### Whisper 转录配置

本工具支持两种高性能转录引擎：
- **[mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)**: 针对 Apple Silicon (M1/M2/M3) 优化，使用 GPU 加速
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**: 使用 CTranslate2，支持 CPU 和 NVIDIA GPU

#### 后端选择 (`WHISPER_BACKEND`)

| 值 | 说明 | 适用设备 |
|-----|------|---------|
| `auto` | 自动选择最佳后端 | 所有设备 |
| `mlx-whisper` | Apple Silicon GPU 加速 | M1/M2/M3 Mac |
| `faster-whisper` | CTranslate2 引擎 | CPU 或 NVIDIA GPU |

**Apple Silicon (M1/M2/M3) 用户推荐配置**：
```bash
pip install mlx-whisper
```

```bash
WHISPER_BACKEND=mlx-whisper
WHISPER_LOCAL_MODEL=large-v3  # MLX 足够快，可以用大模型
```

#### 模型选择 (`WHISPER_LOCAL_MODEL`)

| 模型 | 大小 | 速度 | 准确度 | 显存需求 |
|------|------|------|--------|----------|
| `tiny` | 39M | 最快 | 基础 | ~1GB |
| `base` | 74M | 快 | 良好 | ~1GB |
| `small` | 244M | 中等 | 较好 | ~2GB |
| `medium` | 769M | 较慢 | 优秀 | ~5GB |
| `large-v3` | 1.5G | 最慢 | 最佳 | ~10GB |
| `turbo` | 809M | 快 | 优秀 | ~6GB |

> 💡 推荐中文播客使用 `small`（速度优先）或 `medium`（准确度优先）

#### 设备选择 (`WHISPER_DEVICE`)

| 值 | 说明 |
|-----|------|
| `auto` | 自动检测（有 CUDA 用 GPU，否则用 CPU） |
| `cuda` | 强制使用 NVIDIA GPU（需要 CUDA 驱动） |
| `cpu` | 强制使用 CPU（通用但较慢） |

#### 计算精度 (`WHISPER_COMPUTE_TYPE`)

| 值 | 说明 | 速度 | 显存 |
|-----|------|------|------|
| `auto` | 自动（GPU 用 float16，CPU 用 int8） | - | - |
| `float16` | 半精度浮点（仅 GPU） | 快 | 中等 |
| `int8` | 8位整数量化 | **最快** | **最低** |
| `int8_float16` | INT8 权重 + FP16 计算（仅 GPU） | 快 | 低 |
| `float32` | 全精度浮点 | 最慢 | 最高 |

#### 推荐配置组合

**Apple Silicon Mac (M1/M2/M3)**：
```bash
WHISPER_BACKEND=mlx-whisper
WHISPER_LOCAL_MODEL=large-v3
```

**NVIDIA GPU**：
```bash
WHISPER_BACKEND=faster-whisper
WHISPER_LOCAL_MODEL=small
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=int8
WHISPER_BATCH_SIZE=16
```

**CPU（通用）**：
```bash
WHISPER_BACKEND=faster-whisper
WHISPER_LOCAL_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_BATCH_SIZE=8
```

#### 性能参考

13 分钟音频转录时间（[benchmark 来源](https://github.com/SYSTRAN/faster-whisper)）：

| 配置 | 时间 | 显存 |
|------|------|------|
| large-v2, fp16, batch=8 | **17秒** | 6GB |
| large-v2, int8, batch=8 | **16秒** | 4.5GB |
| small, int8, batch=8 (CPU) | 51秒 | 3.6GB RAM |

### 检查间隔

默认每小时检查一次新节目，可在 `.env` 中修改：

```bash
XYZ_CHECK_INTERVAL=3600  # 秒
```

---

## 数据存储

所有数据存储在 `data/` 目录下：

```
data/
├── audio/          # 下载的音频文件（按播客 ID 分目录）
├── transcripts/    # 逐字稿 JSON 文件
├── summaries/      # 摘要 JSON 文件
├── logs/           # 日志文件
├── xyz.db          # SQLite 数据库
└── tokens.json     # 登录令牌（自动刷新）
```

---

## 输出格式

### 逐字稿 (transcripts/*.json)

```json
{
  "episode_id": "xxx",
  "language": "zh",
  "duration": 3600.0,
  "text": "完整文本...",
  "segments": [
    {"start": 0.0, "end": 5.0, "text": "段落文本..."}
  ]
}
```

### 摘要 (summaries/*.json)

```json
{
  "episode_id": "xxx",
  "title": "节目标题",
  "overview": "2-3段概述...",
  "key_points": [
    {
      "topic": "话题",
      "summary": "要点总结",
      "original_quote": "原文引用",
      "timestamp": "00:15:30"
    }
  ],
  "topics": ["话题1", "话题2"],
  "takeaways": ["收获1", "收获2"]
}
```

---

## 故障排除

### 常见问题

#### 1. "command not found: python"
使用 `python3` 代替 `python`，或确保虚拟环境已激活。

#### 2. 端口被占用
```bash
# 查看占用端口的进程
lsof -i :8000

# 杀掉进程
kill -9 <PID>

# 或使用其他端口
python main.py serve --port 9000
```

#### 3. Ctrl+Z 后端口不释放
`Ctrl+Z` 只暂停进程，不会释放端口。正确做法：
```bash
# 杀掉暂停的任务
kill %1

# 或者恢复到前台再 Ctrl+C
fg %1
# 然后按 Ctrl+C
```

#### 4. FFmpeg 未找到
```bash
# 检查是否安装
ffmpeg -version

# 如果未安装
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu
```

#### 5. 转录失败
1. 确保已安装 FFmpeg
2. 检查音频文件是否完整下载
3. 尝试使用更小的 Whisper 模型（`WHISPER_LOCAL_MODEL=small`）

#### 6. 摘要失败或超时
1. 检查 LLM API 配置是否正确
2. 确认 API 密钥有效
3. 检查网络连接
4. 长音频可能需要更长时间，耐心等待

#### 7. 私有播客需要登录
公开播客无需登录。如果遇到私有/付费内容，工具会自动弹出浏览器让你登录小宇宙账号。

---

## License

MIT
