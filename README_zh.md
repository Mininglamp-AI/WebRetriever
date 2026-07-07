<h1 align="center">🌐 WebRetriever：用于高效网络智能体评估的大规模综合基准</h1>
<p align="center">
<a href="https://github.com/Mininglamp-AI/WebRetriever">📃 论文</a>
•
<a href="https://mininglamp-ai.github.io/WebRetriever/">🏆 排行榜</a>
•
<a href="https://huggingface.co/datasets/Mininglamp-2718/WebRetriever">🤗 数据集</a>
•
🔤 <a href="https://github.com/Mininglamp-AI/WebRetriever/blob/main/README.md">English</a> | 中文
</p>


## 💡 动机
<p align="center">
  <img src="docs/static/images/motivation.png" alt="WebRetriever 基准测试的动机。" width="80%">
</p>
<p align="center"><em>图 1. WebRetriever 基准测试的动机。WebRetriever 从三个方面解决了先前工作的关键局限性：数据集规模和多样性、自动化评估的可靠性，以及面向部署的评估协议。</em>
</p>

---

## 🏗️ 项目结构

```
WebRetriever/
├── data/                           # 任务数据
│   └── example_tasks.json          # 示例任务（3 条）
├── scripts/                        # 启动脚本
│   ├── run_agent.sh                # 运行智能体评测
│   ├── run_online_service_multi.sh # 启动本地 VLM 推理服务
│   ├── create_sandbox.sh           # 创建云沙箱浏览器
│   └── run_naveval.sh              # 运行 NavEval 自动评估
├── src/
│   ├── agent/                      # 网络智能体（UI-TARS 1.5 示例）
│   │   ├── agent.py                # 智能体核心：VLM 交互、历史管理、动作解析
│   │   ├── main.py                 # 多进程任务调度器
│   │   ├── web_controller.py       # 基于 Playwright + CDP 的浏览器控制
│   │   ├── prompts.py              # Prompt 模板与动作空间定义
│   │   ├── app.py                  # 本地 VLM 推理服务（Qwen2.5-VL / Qwen3-VL）
│   │   ├── config.py               # 沙箱配置加载器
│   │   ├── create_sandbox.py       # 腾讯云 AGS 沙箱创建
│   │   └── .env.example            # 环境变量模板
│   └── eval/                       # NavEval 评估框架
│       ├── naveval.py              # 评估主脚本
│       ├── agents/                 # 评估智能体
│       ├── common/                 # 过滤器与格式化工具
│       └── util/                   # 工具函数
└── docs/                           # 文档与排行榜网站
```

## 🚀 快速开始

### 环境准备

```bash
pip install playwright openai numpy opencv-python Pillow
playwright install chromium
```

### 1. 数据准备

从 Hugging Face 下载任务数据集：

```bash
# 安装 git-lfs（如未安装）
git lfs install

# 克隆数据集
git clone https://huggingface.co/datasets/Mininglamp-2718/WebRetriever data/
```

数据集按评估协议组织。将下载的 JSON 文件放入 `data/` 目录，并在 `scripts/run_agent.sh` 中设置对应的 `INPUT` 路径。

> 详细的协议说明和数据格式文档请参阅 [🤗 Hugging Face 数据集页面](https://huggingface.co/datasets/Mininglamp-2718/WebRetriever)。

### 2. 浏览器连接（3 种模式）

WebRetriever 通过 [CDP（Chrome DevTools Protocol）](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)使用 [Playwright](https://playwright.dev/python/) 进行所有浏览器交互。Playwright API 详细用法请参阅 [Playwright Python 文档](https://playwright.dev/python/docs/intro)。

#### 模式 A：本地浏览器

启动带有远程调试端口的 Chrome：

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --user-data-dir="/tmp/chrome-debug-profile"

# Linux
google-chrome --remote-debugging-port=9222 \
    --user-data-dir="/tmp/chrome-debug-profile" \
    --no-first-run --no-sandbox
```

验证连接：
```bash
curl http://localhost:9222/json/version
```

然后在 `scripts/run_agent.sh` 中配置：
```bash
CDP_URLS=(
    "http://localhost:9222"
)
```

#### 模式 B：远程浏览器

与模式 A 相同，但在远程服务器上启动 Chrome 时需添加 `--remote-allow-origins=*`，并将 `CDP_URLS` 设置为远程 IP（如 `http://YOUR_REMOTE_IP:9222`）。

#### 模式 C：腾讯云 AGS 沙箱

云端浏览器沙箱，内置环境隔离：

1. 复制并填写凭证：
   ```bash
   cp src/agent/.env.example src/agent/.env
   # 编辑 .env，填入腾讯云 AGS 凭证
   ```

2. 创建沙箱：
   ```bash
   bash scripts/create_sandbox.sh 4    # 创建 4 个沙箱实例
   ```

3. 脚本会生成包含 CDP URL 的 `sandbox_list.json`，将 URL 复制到 `scripts/run_agent.sh` 中：
   ```bash
   CDP_URLS=(
       "https://9000-xxx.tencentags.com/cdp?access_token=sit_xxx"
       "https://9000-yyy.tencentags.com/cdp?access_token=sit_yyy"
       # ... 从 sandbox_list.json 中粘贴
   )
   ```

> **注意：** 沙箱认证会自动处理 —— `web_controller.py` 会从 URL 中检测 `access_token` 参数并设置所需的 CDP 请求头。

### 3. 模型配置

智能体同时支持**开源模型（本地部署）**和**闭源模型（API 调用）**。

#### 开源模型（本地部署）

项目内置的 `app.py` 提供了一个轻量级的 OpenAI 兼容推理服务，支持 **Qwen2.5-VL** 和 **Qwen3-VL** 模型。每张 GPU 启动一个服务：

```bash
# 1. 在脚本中修改 MODEL_PATH，指向你的模型权重路径
# 2. 启动服务（8 张 GPU → 8 个服务，端口 8001-8008）
bash scripts/run_online_service_multi.sh
```

也可以使用 [vLLM](https://docs.vllm.ai/) 或其他 OpenAI 兼容的推理框架作为替代。

然后在 `scripts/run_agent.sh` 中配置：
```bash
MODEL="uitars"                                     # --served-model-name
VLM_PORTS="8001 8002 8003 8004 8005 8006 8007 8008" # 本地服务端口
```

每个 worker 通过轮询分配 VLM 端口（`worker_id % num_ports`）。

#### 闭源模型（API 调用）

使用闭源模型（如 GPT-4o、Claude）时，直接在 `scripts/run_agent.sh` 中配置 API：

```bash
API_BASE="https://api.openai.com/v1"
API_KEY="your-api-key"
MODEL="gpt-4o"
VLM_PORTS=""                                        # API 模式下留空
```

所有 worker 共享同一个 API 端点。

### 4. 智能体评测

`src/agent/` 目录提供了基于 [UI-TARS 1.5](https://github.com/bytedance/UI-TARS) 的**完整运行示例**。

#### 运行

```bash
bash scripts/run_agent.sh
```

**`run_agent.sh` 配置项：**

| 参数 | 说明 |
|------|------|
| `INPUT` | 任务 JSON 文件路径（如 `data/example_tasks.json`） |
| `OUTPUT` | 输出目录（轨迹与结果） |
| `CDP_URLS` | 浏览器 CDP URL 数组（数量决定并行 worker 数） |
| `MODEL` | 模型名称 |
| `VLM_PORTS` | 本地 VLM 服务端口（开源模型） |
| `API_BASE` / `API_KEY` | API 端点与密钥（闭源模型） |

**并行机制：** `CDP_URLS` 的数量决定并行 worker 数，每个 worker 连接一个浏览器实例。

**断点续跑：** 运行器会自动跳过已完成的任务（`result.json` 中 `"status": "SUCCESS"` 的任务），支持中断后安全重启。

#### 任务格式

请查看 `data/` 目录中下载的数据集了解输入格式和示例。

#### 输出结构

```
output/
├── locks/                          # 多进程协调锁
├── 0_f0fe04a2.../
│   ├── trajectory/                 # 每步截图（0.png, 1.png, ...）
│   ├── trajectory_visual/          # 标注截图（带动作叠加层）
│   ├── result.json                 # 任务结果：状态、动作序列、思维链、URL
│   └── capture.json                # 捕获的 XHR/Fetch 网络请求
└── logs/
    └── worker_0_YYYYMMDD.log       # 各 worker 日志文件
```

### 5. NavEval 评估

NavEval 提供智能体轨迹的自动化评估，与人工判断的一致性为 91.2%。

#### 运行

```bash
# 先在 run_naveval.sh 中配置 API 凭证
bash scripts/run_naveval.sh
```

#### 工作原理

NavEval 分为两个阶段：
- **过滤阶段：** 从捕获的网络流量中提取和过滤相关的 XHR/Fetch 请求，去除噪声（静态资源、统计分析等）
- **评估阶段：** 使用 LLM 裁判基于丰富的交互上下文（包括网络请求、动作序列和页面 URL）评估任务完成情况

#### 配置

| 参数 | 说明 |
|------|------|
| `--mode` | `filter`、`eval` 或 `both` |
| `--test-dir` | 智能体输出目录（包含 `result.json` 和 `capture.json`） |
| `--save-dir` | 评估结果保存目录 |
| `--max-workers` | 并行评估 worker 数 |
| `--api-key` / `--api-base` | LLM 裁判模型的 API 凭证 |
| `--model` | 裁判模型名称（如 `claude-sonnet-4-5`） |

### 6. 构建自定义智能体

`src/agent/` 提供的是基于 UI-TARS 1.5 的参考实现。如需接入自己的模型：

**自定义 `agent.py`** —— 修改 VLM 交互逻辑以适配你的模型。

**自定义 `web_controller.py`** —— 如果你的模型使用不同的动作空间，可扩展浏览器控制逻辑。

`main.py` 任务调度器通常不需要修改 —— 它负责多进程调度、浏览器生命周期管理、截图采集和结果保存。

## 📜 许可证

本项目基于 [MIT 许可证](LICENSE) 发布。
