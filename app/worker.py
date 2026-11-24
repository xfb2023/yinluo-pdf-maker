# -*- coding: utf-8 -*-
"""后台转换线程：包装 dl.convert，汇报整体进度、单文件进度与预计剩余时间。

修正旧版问题：进度条按“全部文件的总页数”计算，多文件时不再从 100% 跳回 0%。
"""
import os
import sys
import time
import traceback

from PySide6.QtCore import QThread, Signal

from .settings import SRC_DIR, human_seconds

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


class Worker(QThread):
    log = Signal(str)
    overall = Signal(int, str)                 # 整体百分比, 状态文字
    row_state = Signal(int, str, int)          # 行号, 状态kind, 行内进度(-1 隐藏)
    file_done = Signal(int, str, float)        # 行号, 输出路径, 大小MB
    file_failed = Signal(int, str)             # 行号, 错误摘要
    finished_all = Signal(int, int, bool, float)  # 成功数, 失败数, 被停止, 总耗时

    def __init__(self, opts, jobs, parent=None):
        """jobs: [{"src":..., "dst":..., "pages":...}, ...]"""
        super().__init__(parent)
        self.opts = opts
        self.jobs = jobs
        self.cancelled = False

    def run(self):
        import dl

        total_pages = sum(j["pages"] for j in self.jobs) or 0
        pages_before = 0
        t_start = time.time()
        done = failed = 0
        outputs = []

        for i, job in enumerate(self.jobs):
            if self.cancelled:
                break
            src, dst, pages = job["src"], job["dst"], job["pages"]
            self.log.emit(f"\n===== [{i + 1}/{len(self.jobs)}] {os.path.basename(src)} =====")
            self.log.emit(f"      → {dst}")
            self.row_state.emit(i, "run", 0)
            t0 = time.time()

            def on_page(page, n_pages, row=i, before=pages_before):
                n = max(n_pages, 1)
                self.row_state.emit(row, "run", int(100 * page / n))
                if total_pages:
                    frac = min((before + page) / total_pages, 1.0)
                    elapsed = time.time() - t_start
                    eta = ""
                    if frac > 0.02 and elapsed > 4:
                        eta = f" · 剩约 {human_seconds(elapsed * (1 - frac) / frac)}"
                    self.overall.emit(
                        int(100 * frac),
                        f"第 {page}/{n_pages} 页 · 文件 {row + 1}/{len(self.jobs)}{eta}")

            o = self.opts
            try:
                dl.convert(
                    src, dst,
                    dpi_text=o["dpi"], q_text=o["quality"], max_mb=o["max_mb"],
                    native_mode=o["native_mode"], image_ocr=o["image_ocr"],
                    threads=o["threads"], gpu=o["gpu"],
                    bookmarks=o["bookmarks"], use_cache=o["cache"],
                    cache_dir=o["cache_dir"] if o["cache"] else None,
                    log=self.log.emit, on_page=on_page,
                    should_stop=lambda: self.cancelled,
                )
                out = getattr(dl.convert, "last_path", dst)
                size_mb = os.path.getsize(out) / 1e6 if os.path.exists(out) else 0.0
                self.log.emit(f"完成：{human_seconds(time.time() - t0)}，{size_mb:.1f}MB")
                self.row_state.emit(i, "ok", 100)
                self.file_done.emit(i, out, size_mb)
                outputs.append(out)
                done += 1
            except dl.Cancelled:
                self.row_state.emit(i, "stop", -1)
                self.log.emit("已停止（当前页处理完后中止）")
                break
            except Exception as e:
                self.row_state.emit(i, "err", -1)
                self.log.emit(f"!! 处理失败：{e}")
                self.log.emit(traceback.format_exc(limit=3))
                self.file_failed.emit(i, str(e))
                failed += 1
            pages_before += pages

        self.finished_all.emit(done, failed, self.cancelled, time.time() - t_start)
