import json
import uuid
from playwright.sync_api import sync_playwright
import random
import platform
import base64
import json
import re
import os
import time
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import List, Dict, Any
from urllib.parse import urlparse, parse_qs

# ========== Begin Sandbox ==========
# Global sandbox reference
_sandbox_instance = None

def connect_existing_sandbox(cdp_url, access_token):
    """Connect to existing sandbox, set global headers"""
    global _sandbox_instance, _cdp_headers
    _cdp_headers = {"X-Access-Token": access_token}
    print(f"✅ Connected to existing sandbox, CDP: {cdp_url[:60]}...")
    return cdp_url

# Internal headers cache
_cdp_headers = {}

def get_cdp_headers():
    """Get headers needed for CDP connection headers"""
    if _cdp_headers:
        return _cdp_headers
    if _sandbox_instance:
        return {"X-Access-Token": str(_sandbox_instance._envd_access_token)}
    return {}
# ========== End Sandbox ==========

browser_window_size_width = 1280
browser_window_size_height = 720

def extract_between_keywords(text, start_key, end_key):
    pattern = re.compile(f'{re.escape(start_key)}(.*?){re.escape(end_key)}', re.DOTALL)
    matches = pattern.findall(text)
    return [match.strip() for match in matches]

def extract_box_coordinate(response, box_name="start_box"):
    """Extract (x, y) coordinate from both formats:
    - New: start_box='<|box_start|>(x,y)<|box_end|>'
    - Old: start_box='(x,y)'
    """
    # New format with <|box_start|>...<|box_end|>
    m = re.search(rf"{box_name}='<\|box_start\|>\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*<\|box_end\|>'", response)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Old format
    m = re.search(rf"{box_name}='\(\s*(\d+)\s*,\s*(\d+)\s*\)'", response)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None

# Initialize Playwright
def init_playwright_context(url):
    p = sync_playwright().start()
    try:
        headers = get_cdp_headers()
        # Auto-detect sandbox: extract access_token from URL query param
        if not headers:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            token = qs.get('access_token', [None])[0]
            if token:
                connect_existing_sandbox(url, token)
                headers = get_cdp_headers()
                print(f"🔑 Auto-detected sandbox token from URL")
        browser = p.chromium.connect_over_cdp(url, **({"headers": headers} if headers else {}))
        # Get existing context or create new
        context = browser.contexts[0] if browser.contexts else browser.new_context()
    except Exception as e:
        print("init error", e)
        return None, None, None

    return p, browser, context

# Open webpage
def open_page(p, browser, context, cdp_url, target_url, max_retries = 3):
    # --- Fix code ---
    # Strip whitespace
    if target_url:
        target_url = target_url.strip()
    # Auto-complete https
    if target_url and not target_url.startswith("http"):
        target_url = "https://" + target_url
    # ----------------

    # print(f"🌐 Opening page: {target_url}", context)
    print(f"🌐 Opening page: {target_url}")
    page = None
    
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Clean up extra pages
            if len(context.pages) >= 3:
                print(f"Too many pages ({len(context.pages)}个)，closing old pages...")
                pages_to_close = context.pages[:-1]
                for old_page in pages_to_close:
                    try:
                        # Force stop page activity first
                        try:
                            old_page.evaluate("() => { window.stop(); }")
                        except:
                            pass
                        
                        # 使用run_before_unload=Falseskip confirmation dialog
                        old_page.close(run_before_unload=False)

                    except Exception as e:
                        print(f"Failed to close: {e}")
                        # Continue closing other pages，不要exit()

        except Exception as e:
            print(f"Error cleaning up pages: {e}")

        try:
            # Try creating new page
            if context and len(context.pages) > 0:
                try:
                    page = context.new_page()
                    break
                except Exception as e:
                    print(f"Failed to create page: {e}")
                    context = None
            
            # 如果context不存在或Failed to create page，Reconnect
            if not context or not page:
                print(f"Reconnecting to browser... (attempt {retry_count + 1}/{max_retries})")
                
                # Try disconnecting existing connection first
                try:
                    if browser:
                        browser.close()
                except:
                    pass
                
                # Wait for connection to fully close
                import time
                time.sleep(2)
                
                # Reconnect
                try:
                    cdp_h = get_cdp_headers(); browser = p.chromium.connect_over_cdp(cdp_url, **({"headers": cdp_h} if cdp_h else {}))
                    # Wait for connection to stabilize
                    time.sleep(1)
                    
                    # Get or create context
                    if browser.contexts:
                        context = browser.contexts[0]
                    else:
                        context = browser.new_context()
                    
                    page = context.new_page()
                    break
                    
                except Exception as e:
                    print(f"Connection failed: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise Exception(f"Cannot connect to browser after {max_retries}  times")
                    continue
                    
        except Exception as e:
            print(f"Error creating page: {e}")
            retry_count += 1
            if retry_count >= max_retries:
                raise
    
    if not page:
        raise Exception("Cannot create page")
    
    # Set viewport size
    try:
        # Get browser window size
        browser_window_size = page.evaluate("""
            () => {
                return {
                    availWidth: window.screen.availWidth,
                    availHeight: window.screen.availHeight,
                    width: window.outerWidth || 1920,
                    height: window.outerHeight || 1080
                }
            }
        """)
        
        print(f"Available screen size: {browser_window_size['availWidth']}x{browser_window_size['availHeight']}")
        print(f"browserwindow size: {browser_window_size['width']}x{browser_window_size['height']}")
        
        global browser_window_size_width
        global browser_window_size_height
        
        browser_window_size_width = browser_window_size['width']
        browser_window_size_height = browser_window_size['height']
        
        page.set_viewport_size({"width": browser_window_size_width, "height": browser_window_size_height})
    except Exception as e:
        print(f"Set viewport sizefailed: {e}，使用default值")
        browser_window_size_width = 1920
        browser_window_size_height = 1080
        page.set_viewport_size({"width": 1920, "height": 1080})
    
    # 为所有page请求添加无缓存头
    def prevent_cache(route):
        try:
            headers = route.request.headers.copy()
            headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            headers['Pragma'] = 'no-cache'
            headers['Expires'] = '0'
            route.continue_(headers=headers)
        except:
            route.continue_()
    
    # 只对主文档应用此规则
    try:
        page.route('**/*', prevent_cache)
    except Exception as e:
        print(f"set路由规则failed: {e}")
    
    # 导航到目标URL
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=150000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"导航到pagefailed: {e}")
        # attempt使用更宽松的wait条件
        try:
            page.goto(target_url, wait_until="commit", timeout=60000)
        except:
            # 如果还是failed，至少确保page存在
            pass
    
    return page

# screenshotsave
def save_screenshot(page, savePath, timeout_ms=5000, max_retries=3):
    """
    savescreenshot，带retry机制
    """
    # 确保directory存在 (只需execute一 times)
    try:
        os.makedirs(os.path.dirname(savePath), exist_ok=True)
    except Exception as e:
        print(f"###创建directoryfailed: {str(e)}")
        return False

    for i in range(max_retries):
        try:
            # attemptscreenshot
            page.screenshot(path=savePath, full_page=False, timeout=timeout_ms)
            print(f"###screenshotsave至: {savePath}")
            return True
        except Exception as e:
            print(f"###screenshotsavefailed (attempt {i+1}/{max_retries}): {str(e)}")
            if i < max_retries - 1:
                time.sleep(1)  # failed后稍作wait再retry
    
    return False

# CDP移动
def cdp_mouse_move(client, end_x, end_y, steps=20):
    """
    使用CDP协议模拟Playwright的page.mouse.move多步移动功能
    
    params:
    client - CDP会话
    end_x, end_y - 目标坐标
    steps - 移动的步数
    """
    import time
    
    # 首先get鼠标current位置（如果无法get，可以假设一个起始位置）
    try:
        # 注意：CDP没有直接get鼠标位置的方法，这里通过JavaScriptget
        position = client.send("Runtime.evaluate", {
            "expression": "({x: window.mouseX || 0, y: window.mouseY || 0})",
            "returnByValue": True
        })
        start_x = position["result"]["value"]["x"]
        start_y = position["result"]["value"]["y"]
    except:
        # 如果无法get，假设起始位置为(0,0)
        start_x, start_y = 0, 0
    
    # 计算移动增量
    delta_x = (end_x - start_x) / steps
    delta_y = (end_y - start_y) / steps
    
    # execute多步移动
    for step in range(1, steps + 1):
        current_x = start_x + delta_x * step
        current_y = start_y + delta_y * step
        
        # 发送鼠标移动事件
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", 
            "x": current_x, 
            "y": current_y
        })
        
        # 可选：添加小延迟使移动更自然
        time.sleep(0.01)  # 10毫秒延迟
    
    # 更新全局鼠标位置（可选，方便下 times调用）
    client.send("Runtime.evaluate", {
        "expression": f"window.mouseX = {end_x}; window.mouseY = {end_y};"
    })

# CDP点击
def mouse_up_and_down(page, client, x, y, time_wait=500):
    # client.send("Input.dispatchMouseEvent", {
    #     "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
    # })
    # page.wait_for_timeout(time_wait)  # 保持按下
    # client.send("Input.dispatchMouseEvent", {
    #     "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
    # })
    page.mouse.click(x, y)

# 点击
def click(page, client, x, y, time_wait=500):
    cdp_mouse_move(client, x, y, steps=20)
    #page.wait_for_timeout(500)

    # executeCDP点击操作
    mouse_up_and_down(page, client, x, y, time_wait)
    page.wait_for_timeout(3000)

    return page, client

# 双击
def doubleclick(page, client, x, y, time_wait=500):
    # execute点击操作
    cdp_mouse_move(client, x, y, steps=20)
 
    time_wait = random.randint(time_wait // 2, time_wait)
    mouse_up_and_down(page, client, x, y, time_wait)
    
    time_wait = random.randint(time_wait // 2, time_wait)
    mouse_up_and_down(page, client, x, y, time_wait)

    page.wait_for_timeout(3000)
    
    return page, client

# 按压快捷键
def hotkey(page, client, hot_key_value, time_wait=500):
    # 映射常见键名到 Playwright 格式
    key_map = {
        "ctrl": "Control", "control": "Control",
        "alt": "Alt", "shift": "Shift",
        "meta": "Meta", "cmd": "Meta", "command": "Meta",
        "enter": "Enter", "return": "Enter",
        "tab": "Tab", "escape": "Escape", "esc": "Escape",
        "backspace": "Backspace", "delete": "Delete",
        "space": " ", "arrowup": "ArrowUp", "arrowdown": "ArrowDown",
        "arrowleft": "ArrowLeft", "arrowright": "ArrowRight",
        "home": "Home", "end": "End",
        "pageup": "PageUp", "pagedown": "PageDown",
    }

    # CDP keyCode 映射（用于 CDP Input.dispatchKeyEvent）
    cdp_key_codes = {
        "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46,
        " ": 32, "ArrowUp": 38, "ArrowDown": 40, "ArrowLeft": 37, "ArrowRight": 39,
        "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
    }

    # 支持 "ctrl+a", "ctrl+shift+t", "enter" 等格式
    keys = [k.strip() for k in hot_key_value.split("+")]
    mapped = [key_map.get(k.lower(), k) for k in keys]

    # 单键且有 CDP keyCode → 用 CDP 直接发送（更可靠）
    if len(mapped) == 1 and mapped[0] in cdp_key_codes:
        key_name = mapped[0]
        key_code = cdp_key_codes[key_name]
        client.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "windowsVirtualKeyCode": key_code,
            "code": key_name,
            "key": key_name,
        })
        client.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "windowsVirtualKeyCode": key_code,
            "code": key_name,
            "key": key_name,
        })
    else:
        # 组合键用 Playwright keyboard.press
        combo = "+".join(mapped)
        page.keyboard.press(combo)

    page.wait_for_timeout(time_wait)
    return page, client

# 键入
def click_type(page, client, x, y, content, time_wait=500):
    # 1. 使用CDPexecute点击
    if x != -1 and y != -1:
        page, client = click(page, client, x, y, time_wait) 
        page.wait_for_timeout(random.randint(100, 200))
    
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # 在 macOS 上使用 Command+A (Meta+A)
        page.keyboard.press("Meta+a")
    else:  # Windows 和 Linux/Ubuntu
        # 在 Windows 和 Linux 上使用 Control+A
        page.keyboard.press("Control+a")
    page.keyboard.press('Backspace')
    page.wait_for_timeout(2500)

    for char in content:
        page.keyboard.type(char, delay=random.randint(10, 50))

    # execute完后暂停2秒
    page.wait_for_timeout(2000)

    return page, client

# 滑动
def scroll(page, client, delta_x, delta_y):
    viewport_size = page.viewport_size
    center_x = viewport_size["width"] / 2
    center_y = viewport_size["height"] / 2
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": center_x,
        "y": center_y,
        "deltaX": delta_x, # 正值scroll down，负值scroll up
        "deltaY": delta_y  # 正值scroll down，负值scroll up
    })
    return page, client

# 滑动(固定区域)
def scroll_menu(page, client, x, y, delta_x, delta_y):
    print("x,y,delta_y:", x, y, delta_y)
    cdp_mouse_move(client, x, y, steps=20)
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": x,
        "y": y,
        "deltaX": delta_x,
        "deltaY": delta_y  # 正值scroll down，负值scroll up
    })
    return page, client

# 拉拽
def drag(page, client, x1, y1, x2, y2, steps=20):
    """
    page - Playwrightpage对象
    client - CDP会话
    x1, y1 - 起始坐标
    x2, y2 - 目标坐标
    steps - drag过程的步数
    """
    import time
    
    # 1. move mouse到起始位置
    cdp_mouse_move(client, x1, y1, steps=steps)
    page.wait_for_timeout(100)
    
    # 2. press mouse左键
    client.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x1,
        "y": y1,
        "button": "left",
        "clickCount": 1
    })
    page.wait_for_timeout(100)
    
    # 3. 分步移动到目标位置
    delta_x = (x2 - x1) / steps
    delta_y = (y2 - y1) / steps
    
    for step in range(1, steps + 1):
        current_x = x1 + delta_x * step
        current_y = y1 + delta_y * step
        
        client.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": current_x,
            "y": current_y,
            "button": "left",  # drag时保持按下status
            "buttons": 1       # 表示左键被按下
        })
        
        # 添加小延迟使drag更自然
        time.sleep(0.01)  # 10毫秒延迟
    
    # 4. 在目标位置释放鼠标
    client.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x2,
        "y": y2,
        "button": "left",
        "clickCount": 1
    })
    
    page.wait_for_timeout(2000)  # waitdrag效果complete
    return page, client

# wait
def wait(page, client, time):
    page.wait_for_timeout(time)  # waitdrag效果complete
    return page, client

# parse动作类型
def parse_action_type(action_str):
    action_str = action_str.strip()
    if action_str.startswith('click('):
        return 'LeftClick'
    elif action_str.startswith('doubleclick(') or action_str.startswith('left_double('):
        return 'DoubleClick'
    elif action_str.startswith('right_single('):
        return 'RightClick'
    elif action_str.startswith('hover('):
        return 'Hover'
    elif action_str.startswith('select('):
        return 'Select'
    elif action_str.startswith('drag('):
        return 'Drag'
    elif action_str.startswith('hotkey(') or action_str.startswith('hotkey '):
        return 'Hotkey'
    elif action_str.startswith('type('):
        return 'Type'
    elif action_str.startswith('stop('):
        return 'Stop'
    elif action_str.startswith('scroll'):
        # 新的动作空间
        if "scroll(" in action_str: 
            if "up" in action_str:
                return 'ScrollUp'
            elif "down" in action_str:
                return 'ScrollDown'
            elif "left" in action_str:
                return 'ScrollLeft'
            elif "right" in action_str:
                return 'ScrollRight'
            else:
                print("scroll parse error !")
                exit()
        else:
            print("scroll parse error !")
            exit()
    elif action_str == 'finish()' or action_str == 'finished()':
        return 'Finish'
    elif action_str == 'wait()':
        return 'Wait'
    elif action_str == 'call_user()':
        return 'CallUser'
    else:
        return 'Unknown'
           
# parse动作
def parse_action(action_str):
    response = action_str
    # print(response)
    try:
        if "type(content" in response:
            type_value = extract_between_keywords(response,"content='", "')")
            if len(type_value) == 0:
                type_value = extract_between_keywords(response, 'content="', '")')
            if len(type_value) == 0:
                print("type parse不出内容！")
                exit()

            action = {"name": "Type", "value": type_value[0]}

        elif "click(start_box=" in response:
            coord = extract_box_coordinate(response, "start_box")
            if coord:
                cx, cy = coord
                action = {"name": "LeftClick", "coordinate": [cx, cy]}
            else:
                action = {"name": "Unknown"}

        elif "left_double(start_box=" in response or "doubleclick(start_box=" in response:
            coord = extract_box_coordinate(response, "start_box")
            if coord:
                cx, cy = coord
                action = {"name": "DoubleClick", "coordinate": [cx, cy]}
            else:
                action = {"name": "Unknown"}

        elif "right_single(start_box=" in response:
            coord = extract_box_coordinate(response, "start_box")
            if coord:
                cx, cy = coord
                action = {"name": "RightClick", "coordinate": [cx, cy]}
            else:
                action = {"name": "Unknown"}

        elif "hover(start_box=" in response:
            coord = extract_box_coordinate(response, "start_box")
            if coord:
                cx, cy = coord
                action = {"name": "Hover", "coordinate": [cx, cy]}
            else:
                action = {"name": "Unknown"}

        elif "scroll(" in response:
            # 提取 direction
            dir_match = re.search(r"direction='(\w+)'", response)
            direction = dir_match.group(1) if dir_match else None

            # 提取坐标（兼容 <|box_start|> 和 (x,y) 两种格式）
            coord = extract_box_coordinate(response, "start_box")

            if direction:
                direction_map = {"up": "ScrollUp", "down": "ScrollDown", "left": "ScrollLeft", "right": "ScrollRight"}
                action = {"name": direction_map.get(direction, "ScrollDown")}
            elif "up" in response:
                action = {"name": "ScrollUp"}
            elif "down" in response:
                action = {"name": "ScrollDown"}
            elif "left" in response:
                action = {"name": "ScrollLeft"}
            elif "right" in response:
                action = {"name": "ScrollRight"}
            else:
                print("scroll parse error !")
                exit()

            if coord:
                action["coordinate"] = [coord[0], coord[1]]

        elif "hotkey" in response:
            # Support both key='...' and key="..."
            hotkey_value = extract_between_keywords(response, "key='", "')")
            if not hotkey_value:
                hotkey_value = extract_between_keywords(response, "key=\"", "\")")
            if not hotkey_value:
                hotkey_value = extract_between_keywords(response, "\"", "\"")
            if hotkey_value:
                hotkey_value = hotkey_value[0].replace(".", "")
            else:
                hotkey_value = ""
            print(f"hotkey_value:{hotkey_value}")
            action = {"name": "HotKey", "value": hotkey_value}

        elif "drag" in response:
            start = extract_box_coordinate(response, "start_box")
            end = extract_box_coordinate(response, "end_box")
            if start and end:
                x1, y1 = start
                x2, y2 = end
                action = {"name": "Drag", "bbox": [x1, y1, x2, y2]}
            else:
                # Fall back to old format
                try:
                    click_point = extract_between_keywords(response, "start_box='(", ")'")[0]
                    c1, c2 = click_point[0].split("),(")
                    x1, y1 = c1.split(",")
                    x2, y2 = c2.split(",")
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    action = {"name": "Drag", "bbox": [x1, y1, x2, y2]}
                except:
                    action = {"name": "Unknown"}

        elif "finished()" in response or "finish()" in response:
            action = {"name": "Finish"}

        elif "call_user()" in response:
            action = {"name": "CallUser"}

        elif "wait()" in response:
            action = {"name": "Wait"}

        else:
            action = {"name": "Unknown"}

    except:
        print("parse error")
        action = {"name": "Unknown"}

    return action

# execute动作
def excute_action(page, client, action):
    name = action["name"]

    # 记录动作execute前的所有page
    old_pages = set(page.context.pages)

    viewport_size = page.viewport_size
    page_height = viewport_size["height"]
    page_width = viewport_size["width"]

    if name == "Type":
        content = action["value"]
        cx,cy = -1,-1
        page, client = click_type(page, client, cx, cy, content, time_wait=1000)

    elif name == "LeftClick":
        cx,cy = action["coordinate"]
        page, client = click(page, client, cx, cy, time_wait=1000)

    elif name == "DoubleClick":
        cx,cy = action["coordinate"]
        page, client = doubleclick(page, client, cx, cy, time_wait=1000)

    elif name == "Hover":
        cx,cy = action["coordinate"]
        cdp_mouse_move(client, cx, cy, steps=20)

    elif name == "RightClick":
        cx, cy = action["coordinate"]
        cdp_mouse_move(client, cx, cy, steps=20)
        page.mouse.click(cx, cy, button="right")
        page.wait_for_timeout(3000)

    elif name == "HotKey":
        hot_key_value = action["value"]
        page, client = hotkey(page, client, hot_key_value)

    elif "Scroll" in name:
        if name in ["ScrollUp", "ScrollDown", "ScrollLeft", "ScrollRight"]:
            if name == "ScrollUp":
                delta_x = 0
                delta_y = -(page_height - 100)
            elif name == "ScrollDown":
                delta_x = 0
                delta_y = page_height - 100
            elif name == "ScrollLeft":
                delta_x = -(page_width - 100)
                delta_y = 0
            elif name == "ScrollRight":
                delta_x = page_width - 100
                delta_y = 0
            
            if "coordinate" in action:
                x, y = action["coordinate"]
                page, client = scroll_menu(page, client, x, y, delta_x, delta_y)
            else:
                page, client = scroll(page, client, delta_x, delta_y)

        else:
            print(f"parse error: {name}")
            exit()

    elif name == "Drag":
        x1, y1, x2, y2 = action["bbox"]
        page, client = drag(page, client, x1, y1, x2, y2, steps=20)

    elif name == "Wait":
        page, client = wait(page, client, time=3000)
   
    # 统一检测page跳转并清理旧page
    # 计算新增的page
    current_pages = set(page.context.pages)
    new_pages = current_pages - old_pages
    print("len new pages:", len(list(new_pages)))

    final_page = page
    final_client = client

    # 如果有new page，返回它；否则返回原page
    if new_pages:
        new_page = list(new_pages)[0]
        new_page.set_viewport_size({"width": browser_window_size_width, "height": browser_window_size_height})
        new_client = page.context.new_cdp_session(new_page)
        print(f"检测到new page，currentlyclose {len(old_pages)} 个旧page...")
        
        # closed_pages = old_pages
        # 最后一页保留，防止new page打不开导致browserclose
        closed_pages = list(old_pages)[:-1]
        
        for p in closed_pages: 
            try:
                # run_before_unload=False 强制close，忽略"是否离开"弹窗
                p.close(run_before_unload=False)
            except Exception as e:
                print(f"closing old pagesfailed: {e}")

        final_page = new_page
        final_client = new_client

    wait_for_rendering_complete(final_page)

    return final_page, final_client

# waitpage渲染
def wait_for_rendering_complete(page):
    try:
        # waitpage load和网络空闲
        page.wait_for_load_state("load", timeout=30000)
        #page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)

        # 简单checkpagestatus，如果这个调用success，page很可能是稳定的
        is_ready = page.evaluate("() => document.readyState")
        if is_ready != "complete":
            print(f"Warning: document.readyState is {is_ready}, not 'complete'")

        # 然后再attemptexecute更复杂的评估
        page.evaluate("""() => {
            return new Promise(resolve => {
                let lastHeight = document.body.scrollHeight;
                let checkCount = 0;
                const interval = setInterval(() => {
                    const currentHeight = document.body.scrollHeight;
                    if (currentHeight === lastHeight || checkCount > 10) {
                        clearInterval(interval);
                        resolve();
                    } else {
                        lastHeight = currentHeight;
                        checkCount++;
                    }
                }, 100);
            });
        }""")

        # 确保有实际内容
        page.wait_for_function("""() => {
            const content = document.body.innerText.trim();
            return content.length > 0;
        }""", timeout=5000)

    except Exception as e:
        print(f"Warning: wait_for_rendering_complete encountered an error: {e}")
        # 如果发生error，再 timesattemptwaitpage load
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass  # 忽略二 timeswait的error

# getvimcparse元素info
def get_vimc_elements(page):
    # ② 提取 highlight 元素
    print("🛠️ execute highlight_dom_sync 方法...")
    # page.wait_for_timeout(1000)
    # result_handle = page.evaluate_handle("""() => window.__highlight_dom_sync__?.()""")
    # page.wait_for_timeout(10000)
    page.evaluate("""() => {
    window.__highlight_completed__ = false;
    Promise.resolve(window.__highlight_dom_sync__?.())
      .then(result => {
        window.__highlight_result__ = result;
        window.__highlight_completed__ = true;
      });
    }""")
    page.wait_for_timeout(2000)
    try:
        page.wait_for_function("""() => window.__highlight_completed__ === true""", timeout=30000)
        result_handle = page.evaluate_handle("""() => window.__highlight_result__""")
        element_handles = result_handle.get_properties()
        print(f"✨ Highlight 元素数量: {len(element_handles)}")

        highlighted_elements = []
        for idx, handle in element_handles.items():
            try:
                obj = handle.json_value()
                if "attributes" in obj:
                    if "id" in obj["attributes"]:
                        obj["attributes"]["attributes_id"] = obj["attributes"]["id"]
                        del obj["attributes"]["id"]
                highlighted_elements.append(obj)
            except Exception as e:
                print(f"⚠️ 提取第 {idx} 个元素failed：{e}")

        page.evaluate("""() => window.__clear_highlight_dom_sync__?.()""")
        page.wait_for_timeout(1000)
    except Exception as e:
        return []
    return highlighted_elements

def get_url(scribe_path):
    #scribe_path_raw = scribe_path.replace("document_details_parse_", "document_details_").replace("_addthink_fix_aug", "").replace("_addthink_aug", "").replace("_aug_list.json",".json")
    scribe_path_raw = scribe_path.replace("document_details_parse_", "document_details_").replace("_addthink_fix", "").replace("_addthink", "")
    print(scribe_path_raw)
    scribe_items = json.load(open(scribe_path_raw))
    title = scribe_items["title"]
    action_list = scribe_items["actions"]
    #print(action_list[0]["description"])
    if "Navigate to" not in action_list[0]["description"]:
        return None, title
    matchs = extract_between_keywords(action_list[0]["description"], "(", ")")
    if len(matchs) == 0:
        matchs = extract_between_keywords(action_list[0]["description"], "<", ">")
    url = matchs[0].split("?")[0]
    print(url, title)    
    return url, title

def check_url_accessible(cdp_url, url, timeout=5000):
    """check URL 是否可访问（sandbox版）"""
    with sync_playwright() as p:
        headers = get_cdp_headers()
        browser = p.chromium.connect_over_cdp(cdp_url, **({"headers": headers} if headers else {}))
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        
        try:
            # response = page.goto(url, timeout=timeout, wait_until='domcontentloaded')
            response = page.goto(url, timeout=timeout, wait_until='commit')
            # check响应status码
            if response and response.status < 400:
                browser.close()
                return True, response.status
            else:
                browser.close()
                return False, response.status if response else None

        except Exception as e:
            browser.close()
            return False, str(e)

# 监听请求类
class RequestCollector:
    """每个进程独立的请求收集器"""
    def __init__(self):
        self.requests = []
    
    def clear(self):
        """清空请求列表"""
        self.requests = []
    
    def handle_request(self, request):
        """process每个请求"""
        req_data = {
            "timestamp": time.time(),
            "url": request.url,
            "method": request.method,
            "headers": dict(request.headers),
            "resource_type": request.resource_type,
            "post_data": None,
            "post_text": None,
            "json_data": None
        }
        
        if request.resource_type not in ["xhr", "fetch"]:
            return
        
        raw = request.post_data_buffer
        if raw:
            req_data["raw_post_data"] = raw.hex()
            try:
                text = raw.decode("utf-8")
                req_data["post_data"] = text
                try:
                    req_data["json_data"] = json.loads(text)
                except:
                    pass
                if req_data["post_data"] is None:
                    return
            except UnicodeDecodeError:
                pass
        
        self.requests.append(req_data)
    
    def save_results(self, save_result_path="capture.json"):
        """save捕获的result"""
        output = {
            "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": len(self.requests),
            "all_requests": self.requests
        }
        
        with open(save_result_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        
        print("result已save到 capture.json")
        return len(self.requests)
