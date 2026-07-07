"""AGS 沙箱配置：从 ~/.ags/config.toml / .env / 环境变量 读取"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── 读取 ~/.ags/config.toml ──
_ags_cfg = {}
_ags_toml = Path.home() / ".ags" / "config.toml"
if _ags_toml.exists():
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None
    if tomllib:
        with open(_ags_toml, "rb") as f:
            _ags_toml_data = tomllib.load(f)
        _toml_region = _ags_toml_data.get("region", "ap-singapore")
        _toml_domain = _ags_toml_data.get("domain", "tencentags.com")
        if not _toml_domain.startswith(("ap-", "na-", "eu-")):
            _toml_domain = f"{_toml_region}.{_toml_domain}"
        _ags_cfg = {
            "e2b_api_key": _ags_toml_data.get("e2b", {}).get("api_key", ""),
            "secret_id": _ags_toml_data.get("cloud", {}).get("secret_id", ""),
            "secret_key": _ags_toml_data.get("cloud", {}).get("secret_key", ""),
            "region": _toml_region,
            "e2b_domain": _toml_domain,
        }

# ── 合并配置：环境变量 > toml > 默认值 ──
cfg = {
    "e2b_domain": os.getenv("E2B_DOMAIN", _ags_cfg.get("e2b_domain", "ap-guangzhou.tencentags.com")),
    "e2b_api_key": os.getenv("E2B_API_KEY", _ags_cfg.get("e2b_api_key", "")),
    "secret_id": os.getenv("TC_SECRET_ID", _ags_cfg.get("secret_id", "")),
    "secret_key": os.getenv("TC_SECRET_KEY", _ags_cfg.get("secret_key", "")),
    "region": os.getenv("TC_REGION", _ags_cfg.get("region", "ap-guangzhou")),
    "role_arn": os.getenv("TENCENT_ROLE_ARN", _ags_cfg.get("role_arn", "")),
}


def setup_e2b_env():
    """设置 e2b SDK 需要的环境变量，并清理代理"""
    os.environ["E2B_DOMAIN"] = cfg["e2b_domain"]
    os.environ["E2B_API_KEY"] = cfg["e2b_api_key"]
    for key in ("http_proxy", "https_proxy", "all_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.pop(key, None)
