#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 设置模型路径
export MODEL_PATH="/path/to/your/model"

echo "$MODEL_PATH"

# 定义 GPU 卡编号和对应的端口
gpu_ids=(0 1 2 3 4 5 6 7)
ports=(8001 8002 8003 8004 8005 8006 8007 8008)

# 先检查GPU状态
echo "检查GPU状态："
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv

# 创建日志目录（如果不存在）
mkdir -p logs

# 循环启动服务
for i in "${!gpu_ids[@]}"; do
    gpu=${gpu_ids[$i]}
    port=${ports[$i]}
    log_file="logs/service_${port}.log"
    
    echo "启动服务：GPU $gpu → 端口 $port，日志输出到 $log_file"
    
    # 方法1：使用 nohup 确保进程持续运行
    CUDA_VISIBLE_DEVICES=$gpu nohup python3 ../src/agent/app.py -p $port > $log_file 2>&1 &
    
    # 记录进程ID
    pid=$!
    echo "  进程ID: $pid"
    
    # 等待一下，让服务有时间启动
    sleep 2
    
    # 检查进程是否还在运行
    if ps -p $pid > /dev/null; then
        echo "  ✓ 服务在端口 $port 上成功启动"
    else
        echo "  ✗ 服务在端口 $port 上启动失败，请检查日志: $log_file"
    fi
done

echo "所有服务启动命令已执行！"
echo ""
echo "检查运行状态："
echo "1. 查看GPU使用情况: nvidia-smi"
echo "2. 查看进程: ps aux | grep 'python3 app.py'"
echo "3. 查看端口占用: netstat -tlnp | grep -E '(8001|8002|8003|8004|8005|8006)'"