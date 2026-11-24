# -*- coding: utf-8 -*-
"""诊断：就绪/运行两态下参数区视口宽度是否一致、是否出现纵向滚动条。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea
app = QApplication([])
for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)
app.setFont(QFont("Microsoft YaHei UI", 9))
from app.main_window import MainWindow

w = MainWindow()
w.resize(1000, 740)
w._add_row(r"D:\投标\国网响应文件（技术）.pdf", 128, "20.4 MB")
w.show()

def report(tag):
    app.processEvents(); app.processEvents()
    sa = w.findChild(QScrollArea)
    vs = sa.verticalScrollBar()
    print(f"{tag}: viewport={sa.viewport().width()}px vscroll_visible={vs.isVisible()}")

w.state = w.STATE_READY
w._apply_state()
report("ready  ")
w.state = w.STATE_RUNNING
w._apply_state()
w._on_overall(46, "第 58/128 页 · 文件 1/2 · 剩约 1 分 20 秒")
report("running")
w.hide()
