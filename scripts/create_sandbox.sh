#!/bin/bash
# 创建 AGS 沙箱，输出 CDP URL
# 用法: bash scripts/create_sandbox.sh [沙箱数量] [模板] [区域]
NUM=${1:-4}
TEMPLATE=${2:-"template"}
REGION=${3:-"ap-shanghai"}
export E2B_DOMAIN="${REGION}.tencentags.com"
export TC_REGION="${REGION}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR/src/agent"
python3 create_sandbox.py --num "${NUM}" --template "${TEMPLATE}" --region "${REGION}" --output "$SCRIPT_DIR/sandbox_list.json"
