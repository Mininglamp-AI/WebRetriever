#!/usr/bin/env python3
"""创建 AGS 浏览器沙箱，输出 CDP URL 列表"""
import sys, os, time, json, argparse

from config import cfg, setup_e2b_env
setup_e2b_env()
try:
    import e2b.api as _api; _api.validate_api_key = lambda k: None
except: pass
from e2b import Sandbox

def main():
    parser = argparse.ArgumentParser(description="创建 AGS 浏览器沙箱")
    parser.add_argument("--num", type=int, default=4, help="沙箱数量")
    parser.add_argument("--template", type=str, default="template")
    parser.add_argument("--timeout", type=int, default=36000)
    parser.add_argument("--region", type=str, default=None)
    parser.add_argument("--output", type=str, default="sandbox_list.json")
    args = parser.parse_args()

    # region 优先用命令行参数，其次用 config 里的
    region = args.region or cfg["region"]
    os.environ["E2B_DOMAIN"] = f"{region}.tencentags.com"
    os.environ["TC_REGION"] = region
    setup_e2b_env()

    sandboxes = []
    print(f"[Sandbox] 正在创建 {args.num} 个沙箱 (模板={args.template}, 区域={region})...")

    for i in range(args.num):
        print(f"[Sandbox] 创建第 {i+1}/{args.num} 个...", end=" ", flush=True)
        try:
            sb = Sandbox.create(template=args.template, timeout=args.timeout)
            host = sb.get_host(9000)
            token = sb._envd_access_token
            cdp = f"https://{host}/cdp?access_token={token}"
            vnc = f"https://{host}/novnc/vnc_lite.html?access_token={token}&path=websockify%3Faccess_token%3D{token}"
            sandboxes.append({"id": sb.sandbox_id, "cdp_url": cdp, "token": token, "live_url": vnc})
            print(f"OK {sb.sandbox_id}")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(1)

    if not sandboxes:
        print("[Sandbox] 没有创建成功任何沙箱！"); sys.exit(1)

    with open(args.output, "w") as f:
        json.dump(sandboxes, f, indent=2, ensure_ascii=False)

    print(f"\nOK: {len(sandboxes)}/{args.num} 个沙箱创建成功")
    print(f"列表: {args.output}")
    print(f"JSON: {json_out}")
    for i, s in enumerate(sandboxes):
        print(f"  [#{i}] {s['id']}: {s['cdp_url'][:80]}...")

if __name__ == "__main__":
    main()
