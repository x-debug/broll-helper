# B-Roll Helper

读取 SRT 视频脚本，利用 AI 分析内容，自动从 **Pexels** 和 **Pixabay** 搜索并下载 B-Roll 素材，打包为 ZIP 文件。

支持两种使用方式：
- **🌐 Web 界面**：React SPA，可视化操作，自动下载 ZIP
- **⌨️ 命令行**：Django management command

---

## 功能特性

- 📄 读取 SRT 格式的视频脚本
- 🤖 AI（OpenRouter）分析脚本，切分分镜并生成英文搜索词，含视频时间戳
- 🔍 从 Pexels 和 Pixabay 搜索免费素材
- 🎬 支持视频和图片两种素材类型
- 📐 支持 16:9（横屏）和 9:16（竖屏）
- 🖥 支持多种清晰度：4K / 1080p / 720p / 480p / 360p
- 📦 自动打包为 ZIP，包含 manifest.txt 时间清单

---

## 安装与配置

### 环境要求

- Python 3.10+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) 包管理工具

### 1. 安装 Python 依赖

```bash
uv sync
```

### 2. 安装前端依赖

```bash
cd frontend && npm install && cd ..
```

### 3. 配置 API 密钥

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# OpenRouter API Key（必填，从 https://openrouter.ai/keys 获取）
OPENROUTER_API_KEY=sk-or-...

# 使用的模型（默认 openai/gpt-4o-mini，可替换为任意 OpenRouter 支持的模型）
OPENROUTER_MODEL=openai/gpt-4o-mini

# Pexels API Key（从 https://www.pexels.com/api/ 申请）
PEXELS_API_KEY=...

# Pixabay API Key（从 https://pixabay.com/api/docs/ 申请）
PIXABAY_API_KEY=...
```

### 4. 初始化数据库

```bash
uv run python manage.py migrate
```

---

## 使用方法

### 🌐 方式一：Web 界面（推荐）

**开发模式（两个终端）：**

```bash
# 终端 1：启动 Django 后端
uv run python manage.py runserver

# 终端 2：启动 React 前端（Vite 自动代理 /api/ 到 Django）
cd frontend && npm run dev
```

浏览器访问 http://localhost:5173 即可使用。

**生产模式（Django 直接托管）：**

```bash
# 构建前端
cd frontend && npm run build && cd ..

# 启动 Django（同时提供前端 + API）
uv run python manage.py runserver
```

浏览器访问 http://localhost:8000

---

### ⌨️ 方式二：命令行

```bash
uv run python manage.py fetch_broll <srt文件路径> [选项]
```

**示例：**

```bash
# 使用默认参数（medium 拆分，视频，16:9，1080p）
uv run python manage.py fetch_broll my_script.srt

# 高密度拆分，竖屏图片
uv run python manage.py fetch_broll my_script.srt --split high --type image --ratio 9:16

# 低密度拆分，4K 横屏视频
uv run python manage.py fetch_broll my_script.srt --split low --quality 4k

# 同时搜索 Pexels 和 Pixabay（优先 Pexels）
uv run python manage.py fetch_broll my_script.srt --sources pexels pixabay

# 指定输出路径
uv run python manage.py fetch_broll my_script.srt --output ./output/my_broll.zip
```

---

## 命令参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `srt_file` | 位置参数 | — | SRT 脚本文件路径（必填） |
| `--split` | `low` \| `medium` \| `high` | `medium` | B-Roll 拆分密度：low=5段，medium=10段，high=15段 |
| `--type` | `video` \| `image` | `video` | 素材类型：视频或图片 |
| `--ratio` | `16:9` \| `9:16` | `16:9` | 素材比例：横屏或竖屏 |
| `--quality` | `4k` \| `1080p` \| `720p` \| `480p` \| `360p` | `1080p` | 最低视频清晰度（图片类型忽略此参数） |
| `--output` | 文件路径 | `broll_<脚本名>.zip` | 输出 ZIP 文件路径 |
| `--results-per-segment` | 整数 | `2` | 每个分镜从每个来源获取的素材数量 |
| `--sources` | `pexels` `pixabay`（可多选） | `pexels pixabay` | 使用的素材来源 |

---

## SRT 文件格式示例

```srt
1
00:00:00,000 --> 00:00:03,500
欢迎来到我们的频道，今天我们将探讨人工智能的发展。

2
00:00:03,500 --> 00:00:07,000
AI 技术正在改变人类的生活方式，从医疗到教育无处不在。

3
00:00:07,000 --> 00:00:11,000
让我们一起看看未来十年 AI 将如何重塑我们的世界。
```

---

## 运行流程

```
SRT文件
  │
  ▼
解析脚本文本
  │
  ▼
OpenAI 分析 → 生成 N 个分镜 + 英文搜索词
  │
  ▼
用户预览 → 编辑 / 增删片段与搜索词 / 重新生成
  │
  ▼
用户确认
  │
  ▼
并发搜索 Pexels + Pixabay API
  │
  ▼
下载素材文件
  │
  ▼
打包为 ZIP（含 manifest.txt 清单）
```

ZIP 包内容示例：
```
broll_my_script.zip
├── manifest.txt          # 清单文件，记录每个素材的来源和对应分镜
├── seg01_pexels_12345.mp4
├── seg01_pixabay_67890.mp4
├── seg02_pexels_11111.mp4
└── ...
```

---

## 获取 API 密钥

| 服务 | 申请地址 | 说明 |
|------|----------|------|
| **OpenRouter** | https://openrouter.ai/keys | 支持数百个模型，按 token 付费，默认用 `openai/gpt-4o-mini` |
| **Pexels** | https://www.pexels.com/api/ | 每月 25,000 次免费请求 |
| **Pixabay** | https://pixabay.com/api/docs/ | 每小时 100 次，每天 5,000 次免费 |

### OpenRouter 推荐模型

```env
# 性价比高（默认）
OPENROUTER_MODEL=openai/gpt-4o-mini

# 更强的分析能力
OPENROUTER_MODEL=openai/gpt-4o
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# 更便宜的选项
OPENROUTER_MODEL=google/gemini-flash-1.5
OPENROUTER_MODEL=anthropic/claude-3.5-haiku
```

---

## 项目结构

```
broll-helper/
├── .env.example          # 环境变量模板
├── .env                  # 你的 API 密钥（不要提交到 git）
├── manage.py
├── pyproject.toml        # uv 项目配置
├── config/               # Django 项目配置
│   └── settings.py
└── broll/                # B-Roll 应用
    ├── ai_analyzer.py    # AI 分镜分析模块
    ├── api_clients.py    # Pexels + Pixabay API 客户端
    └── management/
        └── commands/
            └── fetch_broll.py  # 主命令
```
