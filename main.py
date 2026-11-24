# -*- coding: utf-8 -*-
"""双层PDF制作器 · 新界面入口。

用法：
    python main.py                  打开图形界面
    python main.py --convert 输入.pdf [输出.pdf] [--dpi 300] [--quality 95]
                                   [--max-mb 30] [--native-mode reuse|ocr]
                                   [--threads 2] [--gpu]
                                  无窗口转换，日志写到输出文件同名 .log
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.settings import SRC_DIR, default_cache_dir  # noqa: E402

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _ensure_streams():
    """--noconsole 打包后 stdout/stderr 是 None，先兜住再导入重型依赖。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def run_convert_cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="main --convert")
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("--max-mb", type=float, default=0.0)
    ap.add_argument("--native-mode", choices=["reuse", "ocr"], default="reuse")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--gpu", action="store_true")
    a = ap.parse_args(argv)

    dst = a.dst or (os.path.splitext(a.src)[0] + "-双层.pdf")
    lines = []
    import dl
    dl.convert(a.src, dst, dpi_text=a.dpi, q_text=a.quality, max_mb=a.max_mb,
               native_mode=a.native_mode, threads=a.threads, gpu=a.gpu,
               cache_dir=default_cache_dir(), log=lambda m: lines.append(str(m)))
    out = getattr(dl.convert, "last_path", dst)
    with open(os.path.splitext(out)[0] + ".log", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return 0


def main():
    _ensure_streams()
    argv = sys.argv[1:]
    if argv and argv[0] == "--convert":
        sys.exit(run_convert_cli(argv[1:]))

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 打包成 exe 后图标在 _MEIPASS 的 assets 里，开发时在本目录 assets
    ico = os.path.join(getattr(sys, "_MEIPASS", HERE), "assets", "icon.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    try:  # 任务栏图标独立分组
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("yinluo.pdfmaker")
    except Exception:
        pass

    from app.main_window import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
