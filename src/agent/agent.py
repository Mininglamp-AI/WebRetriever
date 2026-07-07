import ast
import base64
import io
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Dict, List

import numpy as np
from openai import OpenAI
from PIL import Image
from requests.exceptions import SSLError

import prompts
import io
import json
import logging
import logging.handlers
import math
import multiprocessing as mp
import os
import platform
import random
import re
import shutil
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from glob import glob
from io import BytesIO
from time import sleep
from typing import Dict, List

import numpy as np
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from requests.exceptions import SSLError

import web_controller
import prompts

RE_BOX_TOKEN = re.compile(
    r"<\|box_start\|>\s*"
    r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)"
    r"(?:\s*,\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\))?"
    r"\s*<\|box_end\|>",
    re.S,
)

RE_START_BOX_STR = re.compile(
    r"start_box\s*=\s*'?\s*"
    r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)"
    r"(?:\s*,\s*\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\))?"
    r"\s*'?",
    re.I,
)


FINISH_WORD = "Finish"
WAIT_WORD = "Wait"
CALL_USER = "CallUser"
IMAGE_FACTOR = 28
MIN_PIXELS = 100 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200

def extract_between_keywords(text, start_key, end_key):
    pattern = re.compile(f'{re.escape(start_key)}(.*?){re.escape(end_key)}', re.DOTALL)
    matches = pattern.findall(text)
    return [match.strip() for match in matches]

def parse_action(action_str):
    """Parse action string using ast (aligned with uitars15_v1)."""
    try:
        node = ast.parse(action_str, mode='eval')
        if not isinstance(node, ast.Expression):
            raise ValueError("Not an expression")
        call = node.body
        if not isinstance(call, ast.Call):
            raise ValueError("Not a function call")
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        else:
            func_name = None
        kwargs = {}
        for kw in call.keywords:
            key = kw.arg
            if isinstance(kw.value, ast.Constant):
                value = kw.value.value
            elif isinstance(kw.value, ast.Str):  # 兼容旧版本 Python
                value = kw.value.s
            else:
                value = None
            kwargs[key] = value
        return {'function': func_name, 'args': kwargs}
    except Exception as e:
        print(f"Failed to parse action '{action_str}': {e}")
        return None

def escape_single_quotes(text):
    pattern = r"(?<!\\)'"
    return re.sub(pattern, r"\\'", text)

def round_by_factor(number: int, factor: int) -> int:
    return round(number / factor) * factor

def ceil_by_factor(number: int, factor: int) -> int:
    return math.ceil(number / factor) * factor

def floor_by_factor(number: int, factor: int) -> int:
    return math.floor(number / factor) * factor

def add_box_token(input_string):
    if "Action: " in input_string and "start_box=" in input_string:
        suffix = input_string.split("Action: ")[0] + "Action: "
        actions = input_string.split("Action: ")[1:]
        processed_actions = []
        for action in actions:
            action = action.strip()
            coordinates = re.findall(r"(start_box|end_box)='\((\d+),\s*(\d+)\)'", action)
            updated_action = action
            for coord_type, x, y in coordinates:
                updated_action = updated_action.replace(f"{coord_type}='({x},{y})'", f"{coord_type}='<|box_start|>({x},{y})<|box_end|>'")
            processed_actions.append(updated_action)
        final_string = suffix + "\n\n".join(processed_actions)
    else:
        final_string = input_string
    return final_string

def pil_to_base64(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def linearize_accessibility_tree(accessibility_tree, platform="ubuntu"):
    if platform == "ubuntu":
        _attributes_ns = attributes_ns_ubuntu
        _state_ns = state_ns_ubuntu
        _component_ns = component_ns_ubuntu
        _value_ns = value_ns_ubuntu
    elif platform == "windows":
        _attributes_ns = attributes_ns_windows
        _state_ns = state_ns_windows
        _component_ns = component_ns_windows
        _value_ns = value_ns_windows
    else:
        raise ValueError("Invalid platform, must be 'ubuntu' or 'windows'")
    filtered_nodes = filter_nodes(ET.fromstring(accessibility_tree), platform)
    linearized_accessibility_tree = [
        "tag\tname\ttext\tclass\tdescription\tposition (top-left x&y)\tsize (w&h)"
    ]
    for node in filtered_nodes:
        if node.text:
            text = (
                node.text
                if '"' not in node.text
                else '"{:}"'.format(node.text.replace('"', '""'))
            )
        elif node.get("{{{:}}}class".format(class_ns_windows), "").endswith(
            "EditWrapper"
        ) and node.get("{{{:}}}value".format(_value_ns)):
            node_text = node.get("{{{:}}}value".format(_value_ns), "")
            text = (
                node_text
                if '"' not in node_text
                else '"{:}"'.format(node_text.replace('"', '""'))
            )
        else:
            text = '""'
        linearized_accessibility_tree.append(
            "{:}\t{:}\t{:}\t{:}\t{:}\t{:}\t{:}".format(
                node.tag,
                node.get("name", ""),
                text,
                (
                    node.get("{{{:}}}class".format(_attributes_ns), "")
                    if platform == "ubuntu"
                    else node.get("{{{:}}}class".format(class_ns_windows), "")
                ),
                node.get("{{{:}}}description".format(_attributes_ns), ""),
                node.get("{{{:}}}screencoord".format(_component_ns), ""),
                node.get("{{{:}}}size".format(_component_ns), ""),
            )
        )
    return "\n".join(linearized_accessibility_tree)

def trim_accessibility_tree(linearized_accessibility_tree, max_tokens):
    return linearized_accessibility_tree

def get_start_index(base_directory):
    if not os.path.exists(base_directory):
        os.makedirs(base_directory, exist_ok=True)
        return 0
    folders = [d for d in os.listdir(base_directory)
               if os.path.isdir(os.path.join(base_directory, d))]
    index_folders = []
    for folder in folders:
        match = re.match(r'^(\d+)_', folder)
        if match:
            index = int(match.group(1))
            index_folders.append((index, folder))
    if not index_folders:
        return 0
    max_index, max_folder = max(index_folders, key=lambda x: x[0])
    folder_path = os.path.join(base_directory, max_folder)
    result_path = os.path.join(folder_path, 'result.json')
    if not os.path.exists(result_path):
        try:
            shutil.rmtree(folder_path)
            print(f"已删除无result.json的文件夹: {folder_path}")
        except OSError as e:
            print(f"删除文件夹失败: {e}")
        return max_index
    return max_index + 1

def smart_resize(
    height: int, width: int, factor: int = IMAGE_FACTOR, min_pixels: int = MIN_PIXELS, max_pixels: int = MAX_PIXELS
) -> tuple[int, int]:
    """
    Rescales the image so that the following conditions are met:

    1. Both dimensions (height and width) are divisible by 'factor'.

    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].

    3. The aspect ratio of the image is maintained as closely as possible.
    """
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def parse_action_to_structure_output(text, factor, origin_resized_height, origin_resized_width, model_type, max_pixels=16384*28*28, min_pixels=100*28*28):
    """Parse model output: extract thought, split actions, remap coordinates.

    Returns list of dicts:
        - text: full model output
        - thought: extracted thought string
        - raw_action: original action string as model output
        - action: action string with coordinates remapped to screen pixels
        - action_type: ast function name for terminal detection (finished/wait/call_user)
    """
    text = text.strip()

    # Calculate smart_resize dimensions (what model actually sees)
    if model_type == "qwen25vl":
        smart_resize_height, smart_resize_width = smart_resize(
            origin_resized_height, origin_resized_width,
            factor=IMAGE_FACTOR, min_pixels=min_pixels, max_pixels=max_pixels)

    # Screen dimensions = origin_resized dimensions
    screen_width = origin_resized_width
    screen_height = origin_resized_height

    # Coordinate remapping helper
    def remap_xy(x, y):
        """Convert model coordinates to screen pixels."""
        if model_type == "qwen25vl":
            rx = round(float(x) / smart_resize_width * screen_width)
            ry = round(float(y) / smart_resize_height * screen_height)
        else:
            rx = round(float(x) / factor * screen_width)
            ry = round(float(y) / factor * screen_height)
        return rx, ry

    def remap_action_str(raw_str):
        """Replace coordinates in action string with remapped screen pixel values."""
        def replace_box_token(match):
            coord_type = match.group(1)
            x, y = match.group(2), match.group(3)
            rx, ry = remap_xy(x, y)
            return f"{coord_type}='<|box_start|>({rx},{ry})<|box_end|>'"

        def replace_simple(match):
            coord_type = match.group(1)
            x, y = match.group(2), match.group(3)
            rx, ry = remap_xy(x, y)
            return f"{coord_type}='({rx},{ry})'"

        # Handle <|box_start|>(x,y)<|box_end|> format first
        result = re.sub(
            r"(start_box|end_box)='<\|box_start\|>\((\d+),\s*(\d+)\)<\|box_end\|>'",
            replace_box_token, raw_str)
        # Then handle simple (x,y) format
        result = re.sub(
            r"(start_box|end_box)='\((\d+),\s*(\d+)\)'",
            replace_simple, result)
        return result

    # 1. Extract thought
    if text.startswith("Thought:"):
        thought_pattern = r"Thought: (.+?)(?=\s*Action:|$)"
    elif text.startswith("Reflection:"):
        thought_pattern = r"Reflection: (.+?)Action_Summary: (.+?)(?=\s*Action:|$)"
    elif text.startswith("Action_Summary:"):
        thought_pattern = r"Action_Summary: (.+?)(?=\s*Action:|$)"
    else:
        thought_pattern = r"Thought: (.+?)(?=\s*Action:|$)"

    thought = None
    thought_match = re.search(thought_pattern, text, re.DOTALL)
    if thought_match:
        if len(thought_match.groups()) == 1:
            thought = thought_match.group(1).strip()
        elif len(thought_match.groups()) == 2:
            thought = thought_match.group(2).strip()

    assert "Action:" in text
    raw_action_str = text.split("Action:")[-1].strip()

    if "type(content" in raw_action_str:
        def escape_quotes(match):
            return match.group(1)
        pattern = r"type\(content='(.*?)'\)"
        content = re.sub(pattern, escape_quotes, raw_action_str)
        type_str = escape_single_quotes(content)
        raw_action_str = "type(content='" + type_str + "')"

    raw_action_str = raw_action_str.strip()
    remapped_action_str = remap_action_str(raw_action_str)

    result = {
        "text": text,
        "thought": thought,
        "raw_action": raw_action_str,       # 模型输出的原始动作字符串
        "action": remapped_action_str,       # 坐标重映射后的动作字符串
    }

    return result


class UITARSAgent:
    """UI-TARS 1.5 Agent - VLM-based GUI agent (aligned with uitars15_v1, no runtime_conf)."""

    def __init__(
        self,
        model: str = "uitars",
        api_url: str = "http://localhost:8001/v1",
        api_key: str = None,
        model_type: str = "qwen25vl",
        platform: str = "ubuntu",
        action_space: str = "pyautogui",
        observation_type: str = "screenshot",
        max_trajectory_length: int = 50,
        a11y_tree_max_tokens: int = 10000,
        temperature: float = 0.7,
        top_k: int = -1,
        top_p: float = 1.0,
        max_tokens: int = 8192,
        history_n: int = 5,
        max_pixels: int = 16384 * 28 * 28,
        min_pixels: int = 100 * 28 * 28,
        language: str = "Chinese",
        infer_mode: str = "qwen2vl_user",
        prompt_style: str = "qwen2vl_user",
        input_swap: bool = True,
        callusr_tolerance: int = 0,
    ):
        if api_key is None:
            api_key = os.getenv("VLM_API_KEY", "EMPTY")
        self.vlm = OpenAI(base_url=api_url, api_key=api_key)
        self.model = model
        self.model_type = model_type
        self.platform = platform
        self.action_space = action_space
        self.observation_type = observation_type
        self.max_trajectory_length = max_trajectory_length
        self.a11y_tree_max_tokens = a11y_tree_max_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.history_n = history_n
        self.max_pixels = max_pixels
        self.min_pixels = min_pixels
        self.language = language
        self.infer_mode = infer_mode
        self.prompt_style = prompt_style
        self.input_swap = input_swap
        self.callusr_tolerance = callusr_tolerance
        self.action_parse_res_factor = 1000

        # Select action space based on infer_mode (from prompts module)
        self.prompt_action_space = prompts.UITARS_ACTION_SPACE
        if self.infer_mode == "qwen2vl_user":
            self.prompt_action_space = prompts.UITARS_CALL_USR_ACTION_SPACE
        elif self.infer_mode == "qwen25vl_normal":
            self.prompt_action_space = prompts.UITARS_NORMAL_ACTION_SPACE

        # Select prompt template based on prompt_style (from prompts module)
        self.prompt_template = prompts.UITARS_USR_PROMPT_THOUGHT
        if self.prompt_style in ("qwen2vl_user", "qwen25vl_normal"):
            self.prompt_template = prompts.UITARS_USR_PROMPT_THOUGHT
        elif self.prompt_style == "qwen2vl_no_thought":
            self.prompt_template = prompts.UITARS_USR_PROMPT_NOTHOUGHT

        self.thoughts = []
        self.actions = []
        self.observations = []
        self.history_images = []
        self.history_responses = []
        self.urls = []
        self.logger = logging.getLogger(__name__)
        self.cur_callusr_count = 0

    def reset(self):
        self.thoughts = []
        self.actions = []
        self.observations = []
        self.history_images = []
        self.history_responses = []
        self.urls = []
        self.cur_callusr_count = 0

    def predict(
        self, instruction: str, obs: Dict, last_action_after_obs: Dict = None
    ) -> List:
        """
        Predict the next action(s) based on the current observation.
        """

        # Append trajectory
        assert len(self.observations) == len(self.actions) and len(self.actions) == len(
            self.thoughts
        ), "The number of observations and actions should be the same."

        if len(self.observations) > self.max_trajectory_length:
            if self.max_trajectory_length == 0:
                _observations = []
                _actions = []
                _thoughts = []
            else:
                _observations = self.observations[-self.max_trajectory_length :]
                _actions = self.actions[-self.max_trajectory_length :]
                _thoughts = self.thoughts[-self.max_trajectory_length :]
        else:
            _observations = self.observations
            _actions = self.actions
            _thoughts = self.thoughts


        self.history_images.append(obs["screenshot"])

        if self.observation_type in ["screenshot", "screenshot_a11y_tree"]:
            base64_image = obs["screenshot"]
            try:
                linearized_accessibility_tree = (
                    linearize_accessibility_tree(
                        accessibility_tree=obs["accessibility_tree"],
                        platform=self.platform,
                    )
                    if self.observation_type == "screenshot_a11y_tree"
                    else None
                )
            except:
                linearized_accessibility_tree = None

            if linearized_accessibility_tree:
                linearized_accessibility_tree = trim_accessibility_tree(
                    linearized_accessibility_tree, self.a11y_tree_max_tokens
                )

            if self.observation_type == "screenshot_a11y_tree":
                self.observations.append(
                    {
                        "screenshot": base64_image,
                        "accessibility_tree": linearized_accessibility_tree,
                    }
                )
            else:
                self.observations.append(
                    {"screenshot": base64_image, "accessibility_tree": None}
                )

        else:
            raise ValueError(
                "Invalid observation_type type: " + self.observation_type
            )
        
        if self.infer_mode == "qwen2vl_user" or self.infer_mode == "qwen25vl_normal":
            user_prompt = self.prompt_template.format(
                instruction=instruction,
                action_space=self.prompt_action_space,
                language=self.language
            )
        elif self.infer_mode == "qwen2vl_no_thought":
            user_prompt = self.prompt_template.format(
                instruction=instruction
            )

        if len(self.history_images) > self.history_n:
            self.history_images = self.history_images[-self.history_n:]

        messages, images = [], []
        if isinstance(self.history_images, bytes):
            self.history_images = [self.history_images]
        elif isinstance(self.history_images, np.ndarray):
            self.history_images = list(self.history_images)
        elif isinstance(self.history_images, list):
            pass
        else:
            raise TypeError(f"Unidentified images type: {type(self.history_images)}")

        for turn, image in enumerate(self.history_images):
            if len(images) >= self.history_n:
                break
            try:
                image = Image.open(BytesIO(image))
            except Exception as e:
                raise RuntimeError(f"Error opening image: {e}")

            if image.width * image.height > self.max_pixels:
                resize_factor = math.sqrt(self.max_pixels / (image.width * image.height))
                width, height = int(image.width * resize_factor), int(image.height * resize_factor)
                image = image.resize((width, height))
            if image.width * image.height < self.min_pixels:
                resize_factor = math.sqrt(self.min_pixels / (image.width * image.height))
                width, height = math.ceil(image.width * resize_factor), math.ceil(image.height * resize_factor)
                image = image.resize((width, height))

            if image.mode != "RGB":
                image = image.convert("RGB")

            images.append(image)

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant."}]
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": user_prompt}]
            }
        ]
        
        image_num = 0
        if len(self.history_responses) > 0:
            for history_idx, history_response in enumerate(self.history_responses):
                # send at most history_n images to the model
                if history_idx + self.history_n > len(self.history_responses):

                    cur_image = images[image_num]
                    encoded_string = pil_to_base64(cur_image)
                    messages.append({
                        "role": "user",
                        "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_string}"}}]
                    })
                    image_num += 1
                    
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": add_box_token(history_response)}]
                })

            cur_image = images[image_num]
            encoded_string = pil_to_base64(cur_image)
            messages.append({
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_string}"}}]
            })
            image_num += 1
        
        else:
            cur_image = images[image_num]
            encoded_string = pil_to_base64(cur_image)
            messages.append({
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_string}"}}]
            })
            image_num += 1

        try_times = 3
        origin_resized_height = images[-1].height
        origin_resized_width = images[-1].width
        temperature = self.temperature
        top_k = self.top_k
        while True:
            if try_times <= 0:
                print(f"Reach max retry times to fetch response from client, as error flag.")
                return "client error", ["DONE"]
            try:
                response = self.vlm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    frequency_penalty=1,
                    max_tokens=self.max_tokens,
                    temperature=temperature,
                    top_p=self.top_p
                )
                print("*" * 20)
                print("Response:")
                print(response.choices[0].message.content)
                print("*" * 20)
                prediction = response.choices[0].message.content.strip()
                break

            except Exception as e:
                self.logger.exception(f"Error when fetching response from client: {e}")
                prediction = None
                try_times -= 1
                continue
                
        if prediction is None:
            return "client error", ["DONE"]

        # Parse model output → browser-ready action dicts (one step)
        try:
            parsed_response = parse_action_to_structure_output(
                prediction,
                self.action_parse_res_factor,
                origin_resized_height,
                origin_resized_width,
                self.model_type,
                self.max_pixels,
                self.min_pixels
            )
        except Exception as e:
            print(f"Parsing action error: {prediction}, with error:\n{e}")
            return f"Parsing action error: {prediction}, with error:\n{e}", ["DONE"]

        # Record history
        thought_str = parsed_response["thought"]
        action_str = parsed_response["action"]
        self.thoughts.append(thought_str)
        self.actions.append(action_str)
        self.history_responses.append(prediction)

        # Collect browser actions, check for terminal conditions
        action_type = web_controller.parse_action_type(action_str)
        if action_type == FINISH_WORD:
            return prediction, "DONE"
        elif action_type == WAIT_WORD:
            return prediction, "WAIT"
        elif action_type == CALL_USER:
            if self.callusr_tolerance > self.cur_callusr_count:
                self.cur_callusr_count += 1
                return prediction, "WAIT"
            else:
                return prediction, "FAIL"

        if len(self.history_responses) >= self.max_trajectory_length:
            return prediction, "FAIL"

        return prediction, "CONTINUE"

    def get_thoughts(self):
        return self.thoughts

    def get_actions(self):
        return self.actions

    def get_history_responses(self):
        return self.history_responses

    def get_history_images(self):
        return self.history_images

    def get_urls(self):
        return self.urls
