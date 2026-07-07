<h1 align="center">🌐 WebRetriever: A Large-Scale Comprehensive Benchmark for Efficient Web Agent Evaluation</h1>
<p align="center">
<a href="https://github.com/Mininglamp-AI/WebRetriever">📃 Paper</a>
•
<a href="https://mininglamp-ai.github.io/WebRetriever/">🏆 Leaderboard</a>
•
<a href="https://huggingface.co/datasets/Mininglamp-2718/WebRetriever">🤗 Data</a>
•
🔤 English | <a href="https://github.com/Mininglamp-AI/WebRetriever/blob/main/README_zh.md">中文</a>
</p>


## 💡 Motivation
<p align="center">
  <img src="docs/static/images/motivation.png" alt="Motivation for the WebRetriever benchmark." width="80%">
</p>
<p align="center"><em>Figure 1. Motivation for the WebRetriever benchmark. WebRetriever addresses key limitations of prior work from three aspects: dataset scale and diversity, automated evaluation reliability, and deployment-oriented evaluation protocols.</em>
</p>

---

## 🏗️ Project Structure

```
WebRetriever/
├── data/                           # Task data
│   └── example_tasks.json          # Example tasks (3 samples)
├── scripts/                        # Launch scripts
│   ├── run_agent.sh                # Run agent evaluation
│   ├── run_online_service_multi.sh # Start local VLM inference services
│   ├── create_sandbox.sh           # Create cloud sandbox browsers
│   └── run_naveval.sh              # Run NavEval automated evaluation
├── src/
│   ├── agent/                      # Web agent (UI-TARS 1.5 example)
│   │   ├── agent.py                # Agent core: VLM interaction, history, action parsing
│   │   ├── main.py                 # Multi-process task runner
│   │   ├── web_controller.py       # Browser control via Playwright + CDP
│   │   ├── prompts.py              # Prompt templates and action space definitions
│   │   ├── app.py                  # Local VLM serving (Qwen2.5-VL / Qwen3-VL)
│   │   ├── config.py               # Sandbox configuration loader
│   │   ├── create_sandbox.py       # Tencent Cloud AGS sandbox creator
│   │   └── .env.example            # Environment variables template
│   └── eval/                       # NavEval evaluation framework
│       ├── naveval.py              # Main evaluation script
│       ├── agents/                 # Evaluation agents
│       ├── common/                 # Filters and formatters
│       └── util/                   # Utility functions
└── docs/                           # Documentation & leaderboard site
```

## 🚀 Quick Start

### Prerequisites

```bash
pip install playwright openai numpy opencv-python Pillow
playwright install chromium
```

### 1. Data Preparation

Download the task dataset from Hugging Face:

```bash
# Install git-lfs if not already installed
git lfs install

# Clone the dataset
git clone https://huggingface.co/datasets/Mininglamp-2718/WebRetriever data/
```

The dataset contains task files organized by evaluation protocol. Place the downloaded JSON files in the `data/` directory and set the `INPUT` path in `scripts/run_agent.sh` accordingly.

> See the [🤗 Hugging Face dataset page](https://huggingface.co/datasets/Mininglamp-2718/WebRetriever) for detailed protocol descriptions and data format documentation.

### 2. Browser Connection (3 Modes)

WebRetriever uses [Playwright](https://playwright.dev/python/) for all browser interactions via [CDP (Chrome DevTools Protocol)](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp). For detailed Playwright API usage, see the [Playwright Python documentation](https://playwright.dev/python/docs/intro).

#### Mode A: Local Browser

Launch Chrome with a remote debugging port:

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

Verify the connection:
```bash
curl http://localhost:9222/json/version
```

Then configure in `scripts/run_agent.sh`:
```bash
CDP_URLS=(
    "http://localhost:9222"
)
```

#### Mode B: Remote Browser

Same as Mode A, but launch Chrome on a remote server with `--remote-allow-origins=*` and set `CDP_URLS` to the remote IP (e.g., `http://YOUR_REMOTE_IP:9222`).

#### Mode C: Tencent Cloud AGS Sandbox

Cloud-hosted browser sandboxes with built-in isolation:

1. Copy and fill in your credentials:
   ```bash
   cp src/agent/.env.example src/agent/.env
   # Edit .env with your Tencent Cloud AGS credentials
   ```

2. Create sandboxes:
   ```bash
   bash scripts/create_sandbox.sh 4    # Create 4 sandbox instances
   ```

3. The script generates `sandbox_list.json` with CDP URLs. Copy the URLs into `scripts/run_agent.sh`:
   ```bash
   CDP_URLS=(
       "https://9000-xxx.tencentags.com/cdp?access_token=sit_xxx"
       "https://9000-yyy.tencentags.com/cdp?access_token=sit_yyy"
       # ... paste from sandbox_list.json
   )
   ```

> **Note:** Sandbox authentication is handled automatically — `web_controller.py` detects the `access_token` parameter from the URL and sets the required CDP headers.

### 3. Model Setup

The agent supports both **open-source (local)** and **proprietary (API)** models.

#### Open-Source Models (Local Deployment)

The included `app.py` provides a lightweight OpenAI-compatible inference server that supports **Qwen2.5-VL** and **Qwen3-VL** models. Launch one service per GPU:

```bash
# 1. Edit MODEL_PATH in the script to point to your model weights
# 2. Start services (8 GPUs → 8 services on ports 8001-8008)
bash scripts/run_online_service_multi.sh
```

You can also use [vLLM](https://docs.vllm.ai/) or any other OpenAI-compatible serving framework as an alternative.

Then in `scripts/run_agent.sh`:
```bash
MODEL="uitars"                                     # --served-model-name
VLM_PORTS="8001 8002 8003 8004 8005 8006 8007 8008" # Local service ports
```

Each worker is assigned a VLM port via round-robin (`worker_id % num_ports`).

#### Proprietary Models (API)

For proprietary models (e.g., GPT-4o, Claude), configure the API endpoint directly in `scripts/run_agent.sh`:

```bash
API_BASE="https://api.openai.com/v1"
API_KEY="your-api-key"
MODEL="gpt-4o"
VLM_PORTS=""                                        # Leave empty for API mode
```

All workers share the same API endpoint.

### 4. Agent Evaluation

The `src/agent/` directory provides a **complete working example** built on [UI-TARS 1.5](https://github.com/bytedance/UI-TARS).

#### Run

```bash
bash scripts/run_agent.sh
```

**Configuration options in `run_agent.sh`:**

| Parameter | Description |
|-----------|-------------|
| `INPUT` | Task JSON file path (e.g., `data/example_tasks.json`) |
| `OUTPUT` | Output directory for trajectories and results |
| `CDP_URLS` | Browser CDP URL array (number of URLs = number of parallel workers) |
| `MODEL` | Model name |
| `VLM_PORTS` | Local VLM service ports (for open-source models) |
| `API_BASE` / `API_KEY` | API endpoint and key (for proprietary models) |

**Parallelism:** The number of `CDP_URLS` determines the number of parallel workers. Each worker connects to one browser instance.

**Resume:** The runner automatically skips completed tasks (those with `result.json` containing `"status": "SUCCESS"`), enabling safe restart after interruptions.

#### Task Format

See the downloaded dataset in `data/` for the input format and examples.

#### Output Structure

```
output/
├── locks/                          # Multi-process coordination locks
├── 0_f0fe04a2.../
│   ├── trajectory/                 # Raw screenshots at each step (0.png, 1.png, ...)
│   ├── trajectory_visual/          # Annotated screenshots with action overlays
│   ├── result.json                 # Task result: status, actions, thoughts, URLs
│   └── capture.json                # Captured XHR/Fetch network requests
└── logs/
    └── worker_0_YYYYMMDD.log       # Per-worker log files
```

### 5. NavEval Evaluation

NavEval provides automated evaluation of agent trajectories with approximately 90% human agreement.

#### Run

```bash
# Edit API credentials in run_naveval.sh first
bash scripts/run_naveval.sh
```

#### How It Works

NavEval operates in two stages:
- **Filter stage:** Extracts and filters relevant XHR/Fetch requests from captured network traffic, removing noise (static assets, analytics, etc.)
- **Eval stage:** Uses an LLM judge to evaluate task completion based on rich interaction context including network requests, action sequences, and page URLs

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `--mode` | `filter`, `eval`, or `both` |
| `--test-dir` | Directory containing agent output (with `result.json` and `capture.json`) |
| `--save-dir` | Directory to save evaluation results |
| `--max-workers` | Number of parallel evaluation workers |
| `--api-key` / `--api-base` | LLM API credentials for the judge model |
| `--model` | Judge model name (e.g., `claude-sonnet-4-5`) |

### 6. Building Your Own Agent

The provided `src/agent/` is a reference implementation based on UI-TARS 1.5. To integrate your own model:

**Customize `agent.py`** — Modify the VLM interaction logic to work with your model.

**Customize `web_controller.py`** — Extend browser control if your model uses a different action space.

The `main.py` task runner generally does not need modification — it handles multi-process scheduling, browser lifecycle, screenshot capture, and result saving.

## 📜 License

This project is released under the [MIT License](LICENSE).
