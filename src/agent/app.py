from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import uvicorn
import argparse
import time
import torch
import uuid
import os
import asyncio
from transformers import AutoTokenizer, AutoProcessor, AutoConfig
from qwen_vl_utils import process_vision_info
import base64



app = FastAPI(title="Qwen-VL-2.5 OpenAI Compatible API")

# 启用CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 加载模型和tokenizer
print("Loading model...")

# 配置环境变量
model_path = os.getenv("MODEL_PATH", "")
print(model_path)

# 自动判断模型类型
config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
model_type = getattr(config, "model_type", "")
print(f"Detected model_type: {model_type}")

if model_type == "qwen3_vl":
    from transformers import Qwen3VLForConditionalGeneration
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        # attn_implementation="flash_attention_2",
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
else:
    from transformers import Qwen2_5_VLForConditionalGeneration
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_path,
        # attn_implementation="flash_attention_2",
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
model.eval()

processor = AutoProcessor.from_pretrained(model_path)

#tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
print("Model loaded successfully")

# 模拟OpenAI的响应对象
class OpenAIResponse:
    def __init__(self, response_text, prompt_tokens, completion_tokens, model_name="qwen-vl-2"):
        self.id = f"chatcmpl-{uuid.uuid4()}"
        self.object = "chat.completion"
        self.created = int(time.time())
        self.model = model_name
        self.choices = [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }
        ]
        self.usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }

    def to_dict(self):
        return self.__dict__

# 全局变量跟踪当前进行中的请求
ongoing_requests = {}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    data = await request.json()
    
    # 获取请求参数
    messages = data.get("messages", [])
    temperature = data.get("temperature", 0.7)
    top_p = data.get("top_p", 0.9)
    max_tokens = data.get("max_tokens", 1024)
    stream = data.get("stream", False)
    model_name = data.get("model", "qwen-vl-2")
    
    try:
        # 处理消息，查找图像和文本
        image_base64 = None
        text_prompt = ""
        
        # 先转换 OpenAI 格式 (image_url) -> Qwen 格式 (image)
        for i, message in enumerate(messages):
            if not isinstance(message.get("content"), list):
                continue
            for index in range(len(message["content"])):
                if messages[i]["content"][index].get("type") == "image_url":
                    messages[i]["content"][index]["type"] = "image"
                    image_base64 = messages[i]["content"][index]["image_url"]["url"]
                    del messages[i]["content"][index]["image_url"]
                    messages[i]["content"][index]["image"] = image_base64

        # Preparation for inference
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device, torch.float16)

        # 生成回答
        gen_kwargs = dict(max_new_tokens=max_tokens)
        if temperature is not None and temperature > 0:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = top_p
            gen_kwargs["do_sample"] = True
        else:
            gen_kwargs["do_sample"] = False

        generated_ids = model.generate(**inputs, **gen_kwargs)

        
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        #if generated_ids_trimmed[0].shape[0] > 8192:
        #    continue
        
        response_text = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )

        print(response_text)

        # 估算token数量
        prompt_tokens = len(inputs)
        completion_tokens = len(generated_ids_trimmed)
        
        # 创建OpenAI格式响应
        openai_response = OpenAIResponse(
            response_text=response_text[0],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=model_name
        )
        
        return JSONResponse(content=openai_response.to_dict())
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e), "type": "server_error"}}
        )

@app.get("/health")
async def health_check():
    return {"status": "ok", "model": "qwen-vl-2"}


if __name__ == "__main__":
    # 创建参数解析器
    parser = argparse.ArgumentParser(description='Program description')

    # 添加端口号参数
    parser.add_argument('--port', '-p', 
                        type=int, 
                        default=8000, 
                        help='服务的端口号 (默认: 8000)')

    # 解析命令行参数
    args = parser.parse_args()

    uvicorn.run("app:app", host="0.0.0.0", port=args.port, workers=1)
