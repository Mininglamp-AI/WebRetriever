import argparse
import platform
import re
import gc
import json
import logging
import logging.handlers
import math
import multiprocessing as mp
import os
import shutil
import tempfile
import time
import traceback
import fcntl
from datetime import datetime
from glob import glob
from typing import List

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import web_controller
from agent import UITARSAgent

def save_debug_image(image_path, bbox, point, markdown, action, save_dir):
    # 防御: action/markdown 可能是 list
    if isinstance(action, list): action = str(action)
    if isinstance(markdown, list): markdown = str(markdown)
    show_image = cv2.imread(image_path)
    if show_image is None:
        print(f"[save_debug_image] 读取图片失败: {image_path}")
        return

    if bbox is not None:
        try:
            left, top, right, bottom = bbox
            print(bbox)
            left, top, right, bottom = map(int, [left, top, right, bottom])
            # 注意：这里去掉最后那个 0，只保留前 5 个参数
            cv2.rectangle(show_image, (left, top), (right, bottom), (0, 0, 255), 4)
        except Exception as e:
            print(f"[save_debug_image] 无法绘制 bbox={bbox}, err={e}")

    if point is not None:
        try:
            cx, cy = point
            cx, cy = int(cx), int(cy)
            cv2.circle(show_image, (cx, cy), 4, (0, 0, 255), -1)
        except Exception as e:
            print(f"[save_debug_image] 无法绘制 point={point}, err={e}")
    pil_img = Image.fromarray(cv2.cvtColor(show_image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    microhei_path = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    zenhei_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    font_size = 24
    font = None
    system = platform.system()
    try:
        if system == "Windows":
            possible_fonts = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/msyhbd.ttc",
            ]
        else:
            possible_fonts = [
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
                "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc"
            ]
        for path in possible_fonts:
            if os.path.exists(path):
                font = ImageFont.truetype(path, font_size)
                break
    except Exception as e:
        pass
    if font is None:
        font = ImageFont.load_default()
    text_x = 10
    text_y = 10
    line_spacing = 35
    markdown_position = (text_x, text_y)
    markdown_bbox = draw.textbbox(markdown_position, markdown, font=font)
    padding = 5
    draw.rectangle(
        [markdown_bbox[0] - padding, markdown_bbox[1] - padding,
         markdown_bbox[2] + padding, markdown_bbox[3] + padding],
        fill=(255, 255, 255, 200)
    )

    draw.text(markdown_position, markdown, font=font, fill=(0, 128, 0))
    action_position = (text_x, text_y + line_spacing)
    action_bbox = draw.textbbox(action_position, action, font=font)
    draw.rectangle(
        [action_bbox[0] - padding, action_bbox[1] - padding,
         action_bbox[2] + padding, action_bbox[3] + padding],
        fill=(255, 255, 255, 200)
    )
    draw.text(action_position, action, font=font, fill=(0, 0, 255))
    result_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    imageName = image_path.split("/")[-1]
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    sava_path = os.path.join(save_dir, imageName)
    cv2.imwrite(sava_path, result_img)
     
def safe_create_directory(base_dir, result_file="result.json"):
    # .lock 文件统一放到 locks/ 子目录，避免和任务目录混在一起
    parent_dir = os.path.dirname(base_dir)
    lock_dir = os.path.join(parent_dir, "locks")
    os.makedirs(lock_dir, exist_ok=True)
    lock_name = os.path.basename(base_dir) + ".lock"
    lock_file = os.path.join(lock_dir, lock_name)
    try:
        with open(lock_file, 'w') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.path.exists(os.path.join(base_dir, result_file)):
                return False
            if os.path.exists(base_dir):
                shutil.rmtree(base_dir)
            os.makedirs(base_dir, exist_ok=True)
            os.makedirs(f"{base_dir}/trajectory", exist_ok=True)
            os.makedirs(f"{base_dir}/trajectory_visual", exist_ok=True)
            return True
    except BlockingIOError:
        return False
    finally:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except:
            pass

def safe_remove_task_dir(task_dir):
    parent_dir = os.path.dirname(task_dir)
    lock_dir = os.path.join(parent_dir, "locks")
    lock_name = os.path.basename(task_dir) + ".lock"
    lock_file = os.path.join(lock_dir, lock_name)
    if os.path.exists(task_dir):
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            print(f"Error removing task directory {task_dir}: {e}")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except Exception as e:
            print(f"Warning: Failed to remove lock file {lock_file}: {e}")

def safe_save_results(base_dir, result_data, max_retries=3):
    for attempt in range(max_retries):
        try:
            temp_result_path = f"{base_dir}/.result.json.tmp"
            with open(temp_result_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=4, ensure_ascii=False)
            with open(temp_result_path, 'r', encoding='utf-8') as f:
                json.load(f)
            os.replace(temp_result_path, f"{base_dir}/result.json")
            return True
        except Exception as e:
            for tmp_file in temp_result_path:
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except:
                    pass
            if attempt == max_retries - 1:
                print(f"Failed to save results after {max_retries} attempts: {e}")
                return False
            time.sleep(0.1 * (2 ** attempt))
    return False

def safe_write_json(filepath, data, max_retries=3):
    dir_path = os.path.dirname(filepath)
    os.makedirs(dir_path, exist_ok=True)
    
    # 记录临时文件名以便清理
    tmp_name = None
    
    for attempt in range(max_retries):
        try:
            # --- 方案 A: 原子写入 (标准做法) ---
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=dir_path,
                delete=False,
                suffix='.tmp',
                encoding='utf-8'
            ) as tmp_file:
                json.dump(data, tmp_file, indent=4, ensure_ascii=False)
                tmp_file.flush()
                os.fsync(tmp_file.fileno()) # 强制刷入磁盘
                tmp_name = tmp_file.name
            
            # 修正权限：tempfile 默认为 600，挂载盘可能需要 644/666
            try:
                os.chmod(tmp_name, 0o666) 
            except:
                pass

            os.replace(tmp_name, filepath)
            return True

        except Exception as e:
            # 清理 A 方案留下的临时文件
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except:
                    pass
            
            # 如果不是最后一次尝试，等待重试
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))
                continue
            
            # --- 方案 B: 降级为直接写入 (保底方案) ---
            # 如果原子替换一直失败（常见于网络文件系统），则直接写入
            try:
                print(f"Atomic write failed for {filepath}, using direct write. Error: {e}")
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except Exception as final_e:
                print(f"Failed to write {filepath} finally: {final_e}")
                return False
    return False

def setup_logger(log_dir, worker_id: int):
    current_date = datetime.now().strftime("%Y%m%d")
    log_filename = f"{log_dir}/worker_{worker_id}_{current_date}.log"
    logger_name = f"worker_{worker_id}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [Worker %(worker_id)s] [PID %(process)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    class WorkerFilter(logging.Filter):
        def __init__(self, worker_id):
            self.worker_id = worker_id
        def filter(self, record):
            record.worker_id = self.worker_id
            return True
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(WorkerFilter(worker_id))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(WorkerFilter(worker_id))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

def get_args():
    parser = argparse.ArgumentParser(description="Mano CUA 评测脚本")

    # 1. 输入输出
    parser.add_argument("--input", type=str, required=True,
                        help="任务 JSON 文件路径")
    parser.add_argument("--output", type=str, required=True,
                        help="结果输出目录（轨迹 + 日志）")

    # 2. 浏览器连接
    parser.add_argument("--cdp_url", type=str, nargs='+', required=True,
                        help="浏览器 CDP URL 列表（数量决定 worker 数）")

    # 3. 模型配置
    parser.add_argument("--model", type=str, default="uitars",
                        help="模型名称（本地 vLLM served-model-name 或闭源模型名）")

    # 4a. 本地模型：通过 vlm_ports 连接本地 vLLM 服务
    parser.add_argument("--vlm_ports", type=int, nargs='+', default=[],
                        help="本地 vLLM 服务端口列表（每个 worker 轮询分配）")

    # 4b. 闭源模型：通过 api_base + api_key 连接远程 API
    parser.add_argument("--api_base", type=str, default=None,
                        help="闭源模型 API base URL（设置后忽略 --vlm_ports）")
    parser.add_argument("--api_key", type=str, default=None,
                        help="闭源模型 API key")

    # 5. 推理参数

    args = parser.parse_args()

    # 校验：vlm_ports 和 api_base 至少要有一个
    if not args.vlm_ports and not args.api_base:
        parser.error("必须指定 --vlm_ports（本地模型）或 --api_base（闭源模型）")

    return args

if __name__ == "__main__":

    args = get_args()

    # === 输入输出路径 ===
    BASE_DIR = args.output
    LOG_DIR = os.path.join(args.output, "logs")
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    # === Worker 数量（由 cdp_url 数量决定）===
    CDP_URLS = args.cdp_url
    WORKERS = len(CDP_URLS)

    # === VLM 端口列表（本地模型）===
    VLM_PORT_LIST = args.vlm_ports  # 闭源模型时为空

    # === 加载任务 ===
    print(f"加载任务: {args.input}")
    with open(args.input, 'r', encoding='utf-8') as f:
        scribe_json_items = json.load(f)
    print(f"共 {len(scribe_json_items)} 条任务")

    # === 构建已成功任务映射（断点续跑）===
    success_task_map = {}
    if os.path.isdir(BASE_DIR):
        for fname in os.listdir(BASE_DIR):
            rp = os.path.join(BASE_DIR, fname, "result.json")
            if os.path.exists(rp):
                try:
                    with open(rp) as rf:
                        rj = json.load(rf)
                    if rj.get("status") == "SUCCESS":
                        tidx = fname.split("_")[0]
                        success_task_map[tidx] = True
                except Exception:
                    pass
        if success_task_map:
            print(f"已成功任务数: {len(success_task_map)}")

    # === 任务过滤（跳过已完成的）===
    N = len(scribe_json_items)
    indices = []
    skip_cnt = 0
    for i in range(N):
        json_item = scribe_json_items[i]
        task_id = json_item.get("task_id", str(json_item.get("task_index", json_item.get("task_idx"))))
        task_idx = json_item.get("task_index", json_item.get("task_idx"))

        if task_idx in success_task_map:
            skip_cnt += 1
            continue
        website = json_item.get("website", "").strip()
        if not website.startswith("http"):
            website = "https://" + website
        idx_task_id = f"{task_idx}_{task_id}"

        task_dir = f"{BASE_DIR}/{idx_task_id}"
        result_json_path = f"{task_dir}/result.json"
        if os.path.exists(result_json_path):
            with open(result_json_path, 'r', encoding='utf-8') as f:
                result_json_item = json.load(f)
            actions = result_json_item["actions"]
            if len(actions) > 0 and result_json_item["status"] in ["SUCCESS"]:
                skip_cnt += 1
                continue
            else:
                safe_remove_task_dir(task_dir)
        else:
            safe_remove_task_dir(task_dir)
        indices.append(i)

    print(f"总任务数: {N}, 跳过: {skip_cnt}, 待处理: {len(indices)}")
    if not indices:
        print("所有任务已完成！")
        exit(0)
    print(f"从任务索引 {indices[0]} 开始测试")

    # === 多进程调度 ===
    shards = np.array_split(indices, WORKERS)
    shards = [shard.tolist() for shard in shards]
    manager = mp.Manager()
    processing_tasks = manager.dict()
    completed_tasks = manager.dict()

    def run_worker(worker_id: int, worker_indices: List[int]):
        logger = setup_logger(LOG_DIR, worker_id)
        logger.info("进程启动，开始初始化浏览器和任务配置")

        # === 浏览器连接 ===
        url = CDP_URLS[worker_id]
        print(f"[W{worker_id}] 连接浏览器: {url[:80]}...")

        # === 构建 Agent ===
        if args.api_base:
            # 闭源模型：所有 worker 用同一个 api_base
            api_url = args.api_base
            api_key = args.api_key or os.getenv("VLM_API_KEY", "EMPTY")
        else:
            # 本地模型：固定分配 vlm_port（worker_id % len）
            vlm_port = VLM_PORT_LIST[worker_id % len(VLM_PORT_LIST)]
            api_url = f"http://127.0.0.1:{vlm_port}/v1"
            api_key = os.getenv("VLM_API_KEY", "EMPTY")
            logger.info(f"分配 VLM 端口: {vlm_port}")

        agent = UITARSAgent(
            model=args.model,
            api_url=api_url,
            api_key=api_key,
        )
        agent.logger = logger

        request_collector = web_controller.RequestCollector()
        # === 初始化浏览器 ===
        try:
            p, browser, context = web_controller.init_playwright_context(url)
            if browser is None:
                print(f"[W{worker_id}] 浏览器初始化失败，退出。")
                return
        except Exception:
            traceback.print_exc()
            print(f"[W{worker_id}] init_playwright_context 异常，退出。")
            return

        for json_item_i in worker_indices:
            try:
                json_item = scribe_json_items[json_item_i]
                task_id = json_item.get("task_id", str(json_item.get("task_index", json_item.get("task_idx"))))
                task = json_item["task"]
                task_idx = json_item.get("task_index", json_item.get("task_idx"))
                website = str(json_item.get("website", "")).lower()
                if task_id in completed_tasks or task_id in processing_tasks:
                    logger.info(f"跳过任务 {json_item_i}/{task_id}（已被其他进程处理）")
                    continue

                key_points = json_item.get("keytra", "")
                processing_tasks[task_id] = worker_id
                logger.info(f"开始处理任务 {json_item_i}/{task_id}：{task[:50]}...")

                base_dir = f"{BASE_DIR}/{task_idx}_{task_id}"

                save_traj_dir = f"{base_dir}/trajectory"
                save_vis_dir = f"{base_dir}/trajectory_visual"
                if not safe_create_directory(base_dir, result_file="result.json"):
                    logger.info(f"跳过任务 {json_item_i}/{task_id}（已存在结果或被其他进程占用）")
                    processing_tasks.pop(task_id, None)
                    continue
                try:
                    page = web_controller.open_page(p, browser, context, url, website)
                    client = page.context.new_cdp_session(page)
                except Exception as e:
                    logger.error(f"任务 {task_id} 页面初始化失败: {e}")
                    processing_tasks.pop(task_id, None)
                    continue

                request_collector.clear()
                page.on("request", request_collector.handle_request)
                logger.info(f"页面打开成功: {page.url}")
                status = ""
                curr_step = 0
                effect_step = 0
                continue_scroll_cnt = 0
                reference_length = json_item.get("reference_length", 15)
                total_steps = math.ceil(reference_length * 2)
                agent.reset()
                agent.max_trajectory_length = total_steps
                while effect_step < total_steps:
                    image_path = f"{save_traj_dir}/{int(curr_step)}.png"
                    agent.urls.append(page.url)
                    screenshot_success = web_controller.save_screenshot(page, savePath=image_path, timeout_ms=50000)
                    if not screenshot_success:
                        status = "FAIL_SAVE_SCREENSHOT_ERROR"
                        logger.error(f"步骤{curr_step}：截图保存失败")
                        break
                    screenshot = open(image_path, "rb").read()
                    logger.info(f"###总任务数/当前任务：{len(scribe_json_items)}/{json_item_i + 1}")
                    logger.info(f"###总步数/当前步数/有效步数：{total_steps}/{curr_step + 1}/{effect_step + 1}")
                    logger.info(f"###任务：{json_item.get('task', '')}")

                    prediction, condition = agent.predict(task, {"screenshot": screenshot})
                    action_str = agent.get_actions()[-1]
                    action = web_controller.parse_action(action_str)
                    draw_point = action.get("coordinate", None)
                    save_debug_image(image_path, bbox=None, point=draw_point, markdown="", action=action_str, save_dir=save_vis_dir)
                    if condition in ["FAIL"]:
                        status = "FAIL"
                        break
                    elif condition in ["DONE"]:
                        status = "SUCCESS"
                        break
                    new_page, new_client = web_controller.excute_action(page, client, action)
                    if new_page != page:
                        logger.info(f"页面已切换: {page.url} -> {new_page.url}")
                        page = new_page
                        client = page.context.new_cdp_session(page)
                        page.on("request", request_collector.handle_request)

                    if "scroll" not in action_str:
                        continue_scroll_cnt = 0
                        effect_step += 1
                    else:
                        continue_scroll_cnt += 1
                        if continue_scroll_cnt >= 10:
                            logger.info("连续滚动10次，跳出循环")
                            status = "FAIL_SCROLLDOWN"
                            break
                    curr_step += 1

                if status == "FAIL_SAVE_SCREENSHOT_ERROR":
                    logger.info("图片保存失败导致任务结束，跳过该任务！")
                    processing_tasks.pop(task_id, None)
                    agent.reset()
                    continue

                responses = agent.get_history_responses()
                thoughts = agent.get_thoughts()
                actions = agent.get_actions()
                final_result_response = thoughts[-1] if thoughts else ""
                urls = agent.get_urls()
                result_item = {
                    "task_idx": json_item.get("task_idx", ""),
                    "task_id": task_id,
                    "task": task,
                    "key_points": key_points,
                    "website": website,
                    "status": status,
                    "reference_length": reference_length,
                    "predict_length": len(actions),
                    "final_result_response": final_result_response,
                    "actions": actions,
                    "thoughts": thoughts,
                    "history_resps": responses,
                    "urls": urls
                }
                if not safe_save_results(base_dir, result_item):
                    logger.error(f"保存结果文件失败: {base_dir}")

                save_result_path = f"{base_dir}/capture.json"
                request_count = request_collector.save_results(save_result_path)
                logger.info(f"保存了 {request_count} 个请求到 {save_result_path}")

                completed_tasks[task_id] = worker_id
                processing_tasks.pop(task_id, None)
                agent.reset()
                logger.info(f"###总任务数/当前任务：{len(scribe_json_items)}/{json_item_i + 1} 已完成!!!")
            except Exception as e:
                logger.error(f"处理任务 {json_item_i} 时发生异常: {str(e)}", exc_info=True)
                if 'task_id' in locals():
                    processing_tasks.pop(task_id, None)
                continue

        try:
            context.close()
            p.stop()
            logger.info(f"Worker {worker_id} 资源清理完成")
        except Exception as e:
            logger.error(f"Worker {worker_id} 资源清理失败: {str(e)}")

    # === 启动 Workers ===
    print(f"启动 {WORKERS} 个进程")
    for wid in range(WORKERS):
        print(f"  Worker {wid}: {len(shards[wid])} 个任务")
    procs = []
    for wid in range(WORKERS):
        if not shards[wid]:
            continue
        proc = mp.Process(target=run_worker, args=(wid, shards[wid]))
        proc.start()
        procs.append(proc)
        print(f"Worker {wid} 已启动")
        time.sleep(3)

    print("\n开始监控进程状态...")
    try:
        while any(p.is_alive() for p in procs):
            time.sleep(5)
            alive_count = sum(1 for p in procs if p.is_alive())
            print(f"[状态] 活跃: {alive_count}, 完成: {len(completed_tasks)}, 处理中: {len(processing_tasks)}")
    except KeyboardInterrupt:
        print("\n中断，终止所有进程...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
    for proc in procs:
        proc.join()

    print(f"\n完成。总计: {len(completed_tasks)}/{len(indices)}")
    summary_file = os.path.join(LOG_DIR, "summary.json")
    summary = {
        "total_tasks": len(indices),
        "completed_tasks": len(completed_tasks),
        "completion_rate": f"{len(completed_tasks)/len(indices)*100:.2f}%",
        "completed_task_ids": list(completed_tasks.keys()),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    safe_write_json(summary_file, summary)
    print(f"汇总报告: {summary_file}")
