# -*- coding: utf-8 -*-
"""配置读写与环境探测。配置固定写到用户目录，不污染项目文件夹。"""
import json
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))          # 新界面/app
ROOT_DIR = os.path.dirname(APP_DIR)                           # 新界面
SRC_DIR = os.path.dirname(ROOT_DIR)                           # _双层PDF（dl.py 所在）


def default_cache_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "双层PDF制作器", "cache")


def _config_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "双层PDF制作器")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "ui_config_v2.json")


CONFIG_PATH = _config_path()

DEFAULTS = {
    "dpi": 200, "quality": 90,
    "limit_on": False, "max_mb": 30,
    "native_mode": "reuse", "image_ocr": True,
    "bookmarks": True,
    "threads": 3, "gpu": False,
    "cache": True, "cache_dir": default_cache_dir(),
    "out_dir": "", "theme": "light",
    "advanced_open": False,
}


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                if k in cfg:
                    cfg[k] = v
    except Exception:
        pass
    # 旧版 bug 修正：max_mb 存了 0 之类的小于下限的值时，回到默认 30，
    # 避免勾选“限制体积”后按 1MB 猛压。
    try:
        if float(cfg["max_mb"]) < 1:
            cfg["max_mb"] = 30
    except Exception:
        cfg["max_mb"] = 30
    return cfg


def save_cfg(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def gpu_available():
    try:
        import onnxruntime as ort
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def system_is_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def page_count(path):
    try:
        import pymupdf
        doc = pymupdf.open(path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0


def human_size(nbytes):
    n = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def human_seconds(sec):
    sec = int(sec)
    if sec < 60:
        return f"{sec} 秒"
    if sec < 3600:
        return f"{sec // 60} 分 {sec % 60} 秒"
    return f"{sec // 3600} 小时 {sec % 3600 // 60} 分"
