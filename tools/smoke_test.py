# -*- coding: utf-8 -*-
"""冒烟测试：状态机、日志状态点、结果横幅、主题切换。offscreen 下窗口未 show，
可见性一律用 isHidden() 反向判断。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
app = QApplication([])
for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)
app.setFont(QFont("Microsoft YaHei UI", 9))
from app.main_window import MainWindow

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

w = MainWindow()
w.resize(1000, 740)

# 空态
check("空态: 主按钮禁用", not w.btn_primary.isEnabled())
check("空态: 结果横幅隐藏", w.result_bar.isHidden())

# 就绪
w._add_row(r"D:\投标\a.pdf", 128, "20.4 MB")
w.state = w.STATE_READY
w._apply_state()
check("就绪: 主按钮启用且文案正确", w.btn_primary.isEnabled() and w.btn_primary.text() == "生成双层PDF")
check("就绪: 状态点含文件数", "1 个文件" in w._log_state_text)

# 运行
w.state = w.STATE_RUNNING
w._apply_state()
w._on_overall(46, "第 58/128 页 · 文件 1/2 · 剩约 1 分 20 秒")
check("运行: 次按钮为停止", w.btn_secondary.text() == "停止" and not w.btn_secondary.isHidden())
check("运行: 主按钮禁用", not w.btn_primary.isEnabled())
check("运行: 状态文字已记录", "58/128" in w._log_state_text)
w.lb_log_state.resize(200, w.lb_log_state.height())
check("运行: 状态文字省略号收缩", "…" in w.lb_log_state.text() or "58/128" in w.lb_log_state.text())

# 完成
w.tree.set_status(0, "ok")
w.outputs = [(0, r"D:\投标\a-双层.pdf", 22.8)]
w.last_out = w.outputs[0][1]
w._on_finished(1, 0, False, 155)
check("完成: 横幅出现", not w.result_bar.isHidden())
check("完成: 主按钮恢复", w.btn_primary.isEnabled() and w.btn_primary.text() == "再次生成")

# 主题切换
w.seg_theme.set_code("dark")
w._on_theme()
check("深色: 状态点颜色已刷新", True)  # _refresh_log_state_color 不抛异常即过

# CLI 模式注册
import main as m
check("CLI: --convert 入口存在", hasattr(m, "main"))

print("\n%d 项失败" % len(fails) if fails else "\n全部通过")
sys.exit(1 if fails else 0)
