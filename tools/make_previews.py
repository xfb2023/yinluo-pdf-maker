# -*- coding: utf-8 -*-
"""离屏渲染各状态预览图到 previews/，供界面验收。不启动真实转换。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication([])

# 离屏模式下 Qt 找不到系统中文字体，显式加载微软雅黑
for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
          r"C:\Windows\Fonts\simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)
app.setFont(QFont("Microsoft YaHei UI", 9))

from app.main_window import MainWindow  # noqa: E402
from app.widgets import ConfirmStart  # noqa: E402

OUT = os.path.join(ROOT, "previews")
os.makedirs(OUT, exist_ok=True)


def shot(w, name):
    w.show()
    app.processEvents()
    app.processEvents()
    w.grab().save(os.path.join(OUT, name))
    w.hide()
    print("saved", name)


def new_window():
    w = MainWindow()
    w.resize(1000, 740)
    w.seg_theme.set_code("light")
    w._on_theme()
    return w


def add_demo_files(w):
    w._add_row(r"D:\投标\国网响应文件（技术）.pdf", 128, "20.4 MB")
    w._add_row(r"D:\投标\商务文件.pdf", 56, "8.2 MB")
    w.state = w.STATE_READY
    w._apply_state()


# 1 空态 · 浅色
w = new_window()
shot(w, "01-空态-浅色.png")
w.close()

# 2 就绪 · 浅色
w = new_window()
add_demo_files(w)
shot(w, "02-就绪-浅色.png")

# 3 运行中
w.state = w.STATE_RUNNING
w._apply_state()
w._on_overall(46, "第 58/128 页 · 文件 1/2 · 剩约 1 分 20 秒")
w.tree.set_status(0, "run", 46)
w.tree.set_status(1, "wait")
w.log.setPlainText(
    "===== [1/2] 国网响应文件（技术）.pdf =====\n"
    "      → D:\\投标\\国网响应文件（技术）-双层.pdf\n"
    "  p 1 native     dpi=200 px=1654x2339 img= 132.6KB chars=  53 skew=  0.0 rot=  0.0\n"
    "  p 2 ocr(img)   dpi=220 px=1820x2569 img= 401.2KB chars= 312 skew=  0.4 rot=  0.0\n"
    "  p 3 native     dpi=200 px=1654x2339 img= 128.1KB chars=  61 skew=  0.0 rot=  0.0")
shot(w, "03-运行中-浅色.png")

# 4 完成态
w.tree.set_status(0, "ok")
w.tree.set_status(1, "ok")
w.outputs = [(0, r"D:\投标\国网响应文件（技术）-双层.pdf", 22.8),
             (1, r"D:\投标\商务文件-双层.pdf", 9.1)]
w.last_out = w.outputs[0][1]
w._on_finished(2, 0, False, 155)
shot(w, "04-完成-浅色.png")
w.close()

# 5 深色 · 就绪
w = new_window()
add_demo_files(w)
w.seg_theme.set_code("dark")
w._on_theme()
shot(w, "05-就绪-深色.png")

# 6 深色 · 确认框
o = {"out_dir": "", "native_mode": "reuse", "dpi": 200, "image_ocr": True,
     "quality": 88, "bookmarks": True, "max_mb": 0.0,
     "threads": 0, "gpu": False, "cache": True}
summary = [
    ("输出", "源文件所在目录（原名-双层.pdf）"),
    ("识别", "复用现成文字 · 200 dpi · 图片识别：开"),
    ("质量", "JPEG 90 · 书签：开 · 体积限制：关"),
    ("性能", "3 线程 · 缓存：开"),
]
dlg = ConfirmStart(w, 2, 184, summary,
                   ["注意：1 个输出文件已存在，将被覆盖（若正被阅读器打开会自动改存带时间戳的名字）。"])
shot(dlg, "06-确认框-深色.png")
w.close()

# 7 高级设置展开 · 浅色
w = new_window()
add_demo_files(w)
w.sec_advanced.set_expanded(True)
shot(w, "07-高级设置展开-浅色.png")
w.close()

# 8 使用说明 · 浅色
from app.help import HelpDialog  # noqa: E402
w = new_window()
add_demo_files(w)
h = HelpDialog(w)
shot(h, "08-使用说明-浅色.png")
w.close()

print("all done ->", OUT)
