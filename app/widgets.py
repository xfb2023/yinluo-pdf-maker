# -*- coding: utf-8 -*-
"""自定义组件：分段开关、拖放区、文件表、折叠区、确认对话框。"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)


# --------------------------------------------------------------------------- 分段开关
class SegmentedControl(QFrame):
    """胶囊形分段选择，用于主题切换。"""

    changed = Signal(str)

    def __init__(self, items, parent=None):
        """items: [(label, code), ...]"""
        super().__init__(parent)
        self.setObjectName("seg")
        self._buttons = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        for label, code in items:
            b = QPushButton(label)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.changed.emit(c))
            lay.addWidget(b)
            self._buttons[code] = b

    def set_code(self, code):
        b = self._buttons.get(code)
        if b is not None:
            b.setChecked(True)

    def code(self):
        for c, b in self._buttons.items():
            if b.isChecked():
                return c
        return None


# --------------------------------------------------------------------------- 拖放
def pdfs_from_mime(mime):
    out = []
    for url in mime.urls():
        p = url.toLocalFile()
        if os.path.isdir(p):
            out += [os.path.join(p, n) for n in sorted(os.listdir(p))
                    if n.lower().endswith(".pdf")]
        elif p.lower().endswith(".pdf"):
            out.append(p)
    return out


class DropZone(QFrame):
    """空态拖放区：虚线框 + 主按钮。"""

    files_dropped = Signal(list)
    pick_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 28, 24, 28)
        v.setSpacing(8)
        v.addStretch(1)
        title = QLabel("把 PDF 拖到这里")
        title.setObjectName("h2")
        title.setAlignment(Qt.AlignCenter)
        desc = QLabel("支持一次添加多个 PDF · 不修改、不删除原文件")
        desc.setObjectName("sub")
        desc.setAlignment(Qt.AlignCenter)
        btn = QPushButton("选择 PDF 文件…")
        btn.setObjectName("primary")
        btn.setMinimumSize(190, 42)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.pick_clicked)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(btn)
        wrap.addStretch(1)
        v.addWidget(title)
        v.addWidget(desc)
        v.addSpacing(10)
        v.addLayout(wrap)
        v.addStretch(1)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e):
        paths = pdfs_from_mime(e.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            e.acceptProposedAction()
        else:
            e.ignore()


# --------------------------------------------------------------------------- 文件表
class StatusCell(QWidget):
    """状态列：徽章 + 行内迷你进度条（仅处理中显示）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 8, 0)
        lay.setSpacing(8)
        self.badge = QLabel("等待")
        self.badge.setObjectName("badge")
        self.badge.setProperty("kind", "wait")
        self.bar = QProgressBar()
        self.bar.setObjectName("mini")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setMinimumWidth(0)
        self.bar.setVisible(False)
        lay.addWidget(self.badge)
        lay.addWidget(self.bar, 1)

    def set_state(self, kind, text, progress=-1):
        self.badge.setText(text)
        self.badge.setProperty("kind", kind)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        if 0 <= progress <= 100 and kind == "run":
            self.bar.setVisible(True)
            self.bar.setValue(progress)
        else:
            self.bar.setVisible(False)


_BADGE_TEXT = {"wait": "等待", "run": "处理中", "ok": "完成", "err": "失败", "stop": "已停止"}


class FileTree(QTreeWidget):
    """四列文件表：文件名 / 页数 / 大小 / 状态。支持拖入与多选。"""

    files_added = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(False)
        self.setSelectionBehavior(QTreeWidget.SelectRows)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setHeaderLabels(["文件名", "页数", "大小", "状态"])
        for col in (1, 2, 3):
            self.headerItem().setTextAlignment(col, Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hdr = self.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 56)
        self.setColumnWidth(2, 84)
        self.setColumnWidth(3, 150)

    # ---- 拖放
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        paths = pdfs_from_mime(e.mimeData())
        if paths:
            self.files_added.emit(paths)
            e.acceptProposedAction()
        else:
            e.ignore()

    # ---- 行操作
    def add_row(self, path, pages, size_text):
        item = QTreeWidgetItem([os.path.basename(path),
                                str(pages) if pages else "—",
                                size_text, ""])
        item.setData(0, Qt.UserRole, path)
        item.setToolTip(0, path)
        item.setTextAlignment(1, Qt.AlignCenter)
        item.setTextAlignment(2, Qt.AlignCenter)
        self.addTopLevelItem(item)
        cell = StatusCell()
        self.setItemWidget(item, 3, cell)
        return self.indexOfTopLevelItem(item)

    def set_status(self, row, kind, progress=-1, text=None):
        item = self.topLevelItem(row)
        if item is None:
            return
        cell = self.itemWidget(item, 3)
        if cell is not None:
            cell.set_state(kind, text or _BADGE_TEXT.get(kind, kind), progress)

    def path_at(self, row):
        item = self.topLevelItem(row)
        return item.data(0, Qt.UserRole) if item is not None else None

    def remove_rows(self, rows):
        for row in sorted(rows, reverse=True):
            self.takeTopLevelItem(row)

    def selected_rows(self):
        return sorted({i.row() for i in self.selectedIndexes()})

    def count(self):
        return self.topLevelItemCount()


# --------------------------------------------------------------------------- 折叠区
class CollapsibleSection(QWidget):
    """带箭头的折叠区，用于“高级设置”。"""

    toggled = Signal(bool)

    def __init__(self, title, content, expanded=False, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.btn = QToolButton()
        self.btn.setObjectName("fold")
        self.btn.setText(title)
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.btn.clicked.connect(self.toggle)
        self.content = content
        self.content.setVisible(expanded)
        v.addWidget(self.btn)
        v.addWidget(self.content)

    def is_expanded(self):
        return self.content.isVisible()

    def toggle(self):
        self.set_expanded(not self.is_expanded())
        self.toggled.emit(self.is_expanded())

    def set_expanded(self, on):
        self.content.setVisible(on)
        self.btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)


# --------------------------------------------------------------------------- 对话框
def make_btn(text, kind="secondary", primary=False):
    b = QPushButton(text)
    if kind != "secondary":
        b.setObjectName(kind)
    if primary:
        b.setObjectName("primary")
        b.setMinimumSize(150, 42)
        b.setDefault(True)
    elif kind in ("link", "quiet"):
        # 文字型按钮：不设最小宽度，避免撑宽所在行
        b.setMinimumSize(0, 0)
        b.setAutoDefault(False)
    else:
        b.setMinimumSize(108, 34)
        b.setAutoDefault(False)
    return b


class ConfirmStart(QDialog):
    """开始前的参数确认：摘要 + 碰撞/覆盖提示。"""

    def __init__(self, parent, file_count, total_pages, summary_rows, warnings=None):
        super().__init__(parent)
        self.setWindowTitle("开始生成双层PDF？")
        self.setModal(True)
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)

        head = QLabel("开始生成双层PDF？")
        head.setObjectName("h1")
        lay.addWidget(head)
        intro = QLabel(f"共 {file_count} 个文件"
                       + (f" · 约 {total_pages} 页" if total_pages else ""))
        intro.setObjectName("sub")
        lay.addWidget(intro)

        card = QFrame()
        card.setObjectName("summary")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)
        for k, v in summary_rows:
            r = QHBoxLayout()
            r.setSpacing(12)
            key = QLabel(k)
            key.setObjectName("hint")
            key.setFixedWidth(44)
            val = QLabel(str(v))
            val.setWordWrap(True)
            r.addWidget(key, 0, Qt.AlignTop)
            r.addWidget(val, 1)
            cl.addLayout(r)
        lay.addWidget(card)

        for w in warnings or []:
            lab = QLabel(w)
            lab.setObjectName("warn")
            lab.setWordWrap(True)
            lay.addWidget(lab)

        if total_pages >= 300:
            tip = QLabel("页数较多，预计需要数分钟；生成过程中可随时停止。")
            tip.setObjectName("hint")
            lay.addWidget(tip)

        bar = QHBoxLayout()
        bar.addStretch(1)
        back = make_btn("返回修改")
        back.clicked.connect(self.reject)
        go = make_btn("开始生成", primary=True)
        go.clicked.connect(self.accept)
        bar.addWidget(back)
        bar.addSpacing(10)
        bar.addWidget(go)
        lay.addLayout(bar)


class ConfirmAsk(QDialog):
    """通用二次确认：危险动作在左，安全动作在右且为默认。"""

    def __init__(self, parent, title, body, danger_text, safe_text):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        head = QLabel(title)
        head.setObjectName("h2")
        lay.addWidget(head)
        text = QLabel(body)
        text.setWordWrap(True)
        lay.addWidget(text)
        bar = QHBoxLayout()
        bar.addStretch(1)
        safe = make_btn(safe_text)
        safe.clicked.connect(self.reject)
        danger = make_btn(danger_text, kind="danger")
        danger.clicked.connect(self.accept)
        bar.addWidget(danger)
        bar.addSpacing(10)
        bar.addWidget(safe)
        lay.addLayout(bar)
        safe.setDefault(True)
