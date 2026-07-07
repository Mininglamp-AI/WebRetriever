#!/bin/bash
# Mano CUA 评测启动脚本
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ====== 任务配置 ======
INPUT="$PROJECT_DIR/data/example_tasks.json"       # 任务 JSON 文件
OUTPUT="$PROJECT_DIR/test_results/uitars"  # 输出目录

# ====== 构建 CDP_URLS ======
CDP_URLS=(
    "http://YOUR_BROWSER_HOST:9223"
)

echo "🔗 CDP URLs (${#CDP_URLS[@]}):"
for u in "${CDP_URLS[@]}"; do
    echo "  ${u:0:80}..."
done

# ====== 模型配置 ======
# --- 本地模型（vLLM 服务）---
MODEL="uitars"
VLM_PORTS="8001 8002 8003 8004 8005 8006 8007 8008"

# --- 闭源模型（取消注释下面三行，注释掉 VLM_PORTS）---
# API_BASE="https://api.openai.com/v1"
# API_KEY="sk-xxx"
# MODEL="gpt-4o"
# VLM_PORTS=""

# ====== 启动 ======
cd "$PROJECT_DIR/src/agent"
python main.py \
    --input "$INPUT" \
    --output "$OUTPUT" \
    --cdp_url "${CDP_URLS[@]}" \
    --model "$MODEL" \
    ${VLM_PORTS:+--vlm_ports $VLM_PORTS} \
    ${API_BASE:+--api_base "$API_BASE"} \
    ${API_KEY:+--api_key "$API_KEY"}
