# -*- coding: utf-8 -*-
"""主窗口：文件 → 参数 → 生成 的单主线布局。

布局约定：
  · 顶栏：产品名「隐络」+ 使用说明 + 主题分段开关
  · 左列：源文件（矮）/ 运行日志（高，不可折叠）；主操作按钮在日志区标题栏
  · 右列：参数（识别与质量 + 输出位置 + 高级设置折叠）
  · 无底栏：运行进度与状态由日志区标题栏的状态点承担
  · 完成/失败摘要以彩色横幅出现在日志区底部，与日志文本视觉区分
"""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QScrollArea,
    QSpinBox, QStackedWidget, QStyle, QToolButton, QVBoxLayout, QWidget,
)

from .theme import TOKENS, qss
from .settings import (
    default_cache_dir, human_seconds, human_size, load_cfg, page_count,
    save_cfg, system_is_dark,
)
from .widgets import (
    CollapsibleSection, ConfirmAsk, ConfirmStart, DropZone, FileTree,
    SegmentedControl, make_btn,
)
from .worker import Worker

MODES = [("复用现成文字（快）", "reuse"), ("整页 OCR（慢）", "ocr")]


class MainWindow(QMainWindow):
    STATE_EMPTY = "empty"
    STATE_READY = "ready"
    STATE_RUNNING = "running"
    STATE_STOPPING = "stopping"
    STATE_STOPPED = "stopped"
    STATE_DONE = "done"
    STATE_FAILED = "failed"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("隐络双层PDF制作器")
        self.resize(980, 700)
        self.setMinimumSize(880, 600)

        self.worker = None
        self.outputs = []            # [(row, out_path, size_mb)]
        self.last_out = None
        self.state = self.STATE_EMPTY
        self.cfg = load_cfg()
        self._imgocr_saved = bool(self.cfg["image_ocr"])

        self._loading = True
        self._build()
        self._load_into_widgets()
        self._apply_theme()
        self._sync_image_ocr()
        self._sync_cache_row()
        self._apply_state()
        self._loading = False
        self._watch_system_theme()

    # ---------------------------------------------------------------- 构建
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(24, 18, 24, 18)
        v.setSpacing(14)
        v.addLayout(self._header())
        v.addLayout(self._body(), 1)

    def _card(self, title, extra=None):
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        lab = QLabel(title)
        lab.setObjectName("section")
        head.addWidget(lab)
        head.addStretch(1)
        if extra is not None:
            head.addWidget(extra)
        lay.addLayout(head)
        return frame, lay

    def _header(self):
        row = QHBoxLayout()
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        app = QLabel("隐络双层PDF制作器")
        app.setObjectName("h1")
        sub = QLabel("彩色图像层 + 可复制文字层 · 全部在本机处理，不联网")
        sub.setObjectName("sub")
        col.addWidget(app)
        col.addWidget(sub)
        row.addLayout(col)
        row.addStretch(1)
        self.btn_help = make_btn("使用说明", kind="link")
        self.btn_help.clicked.connect(self._show_help)
        row.addWidget(self.btn_help, 0, Qt.AlignVCenter)
        row.addSpacing(4)
        self.seg_theme = SegmentedControl(
            [("跟随系统", "auto"), ("浅色", "light"), ("深色", "dark")])
        self.seg_theme.changed.connect(self._on_theme)
        row.addWidget(self.seg_theme, 0, Qt.AlignVCenter)
        return row

    def _body(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(self._files_card(), 2)   # 源文件区矮
        left.addWidget(self._log_card(), 3)     # 运行日志区高

        right = QVBoxLayout()
        right.setSpacing(0)
        pc = self._params_card()
        pc.setMinimumWidth(380)
        pc.setMaximumWidth(440)
        right.addWidget(pc, 1)

        row.addLayout(left, 6)
        row.addLayout(right, 0)
        return row

    # ---- 源文件
    def _files_card(self):
        head_extra = QWidget()
        hl = QHBoxLayout(head_extra)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self.btn_clear = make_btn("清空列表…", kind="quiet")
        self.btn_clear.clicked.connect(self._clear_files)
        self.btn_add_head = make_btn("＋ 添加 PDF…")
        self.btn_add_head.clicked.connect(self._pick_files)
        hl.addWidget(self.btn_clear)
        hl.addWidget(self.btn_add_head)
        card, lay = self._card("源文件", extra=head_extra)

        self.stack = QStackedWidget()
        self.dropzone = DropZone()
        self.dropzone.pick_clicked.connect(self._pick_files)
        self.dropzone.files_dropped.connect(self._add_paths)
        self.tree = FileTree()
        self.tree.files_added.connect(self._add_paths)
        self.tree.selectionModel().selectionChanged.connect(lambda *_: self._apply_state())
        self.stack.addWidget(self.dropzone)
        self.stack.addWidget(self.tree)
        lay.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.btn_remove = make_btn("移除选中", kind="link")
        self.btn_remove.clicked.connect(self._remove_selected)
        foot.addWidget(self.btn_remove)
        foot.addStretch(1)
        lay.addLayout(foot)
        return card

    # ---- 日志（不可折叠；主操作按钮与状态点在本卡标题栏）
    def _log_card(self):
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        lab = QLabel("运行日志")
        lab.setObjectName("section")
        head.addWidget(lab)
        self.lb_log_state = QLabel("● 等待开始")
        self.lb_log_state.setObjectName("stat")
        # 占满剩余空间（拉伸因子 1），长文本只裁剪不撑宽左列；不再用 addStretch 否则会把它压成 0
        from PySide6.QtWidgets import QSizePolicy as _SP
        self.lb_log_state.setSizePolicy(_SP.Ignored, _SP.Preferred)
        head.addWidget(self.lb_log_state, 1)
        self.lb_log_state.installEventFilter(self)
        self.btn_secondary = make_btn("停止", kind="danger")
        self.btn_secondary.setMinimumSize(90, 34)
        self.btn_secondary.clicked.connect(self._on_secondary)
        self.btn_primary = make_btn("生成双层PDF", primary=True)
        self.btn_primary.setMinimumSize(150, 36)
        self.btn_primary.clicked.connect(self._on_primary)
        head.addWidget(self.btn_secondary)
        head.addWidget(self.btn_primary)
        lay.addLayout(head)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setPlaceholderText("生成信息会显示在这里")
        self.log.setMinimumHeight(140)
        lay.addWidget(self.log, 1)

        # 结果摘要横幅（默认隐藏）：与日志文本不同的背景色
        self.result_bar = QFrame()
        self.result_bar.setObjectName("result")
        rl = QHBoxLayout(self.result_bar)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(10)
        self.lb_result = QLabel()
        self.lb_result.setWordWrap(True)
        self.btn_result_open = make_btn("打开输出文件夹", kind="link")
        self.btn_result_open.clicked.connect(self._open_outdir)
        rl.addWidget(self.lb_result, 1)
        rl.addWidget(self.btn_result_open)
        self.result_bar.setVisible(False)
        lay.addWidget(self.result_bar)
        return card

    # ---- 参数
    def _params_card(self):
        card, lay = self._card("参数")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        v.addWidget(self._group_common())
        line = QFrame()
        line.setObjectName("hrule")
        v.addWidget(line)
        self.sec_advanced = CollapsibleSection("高级设置", self._group_advanced())
        self.sec_advanced.toggled.connect(self._on_advanced_toggled)
        v.addWidget(self.sec_advanced)
        v.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        return card

    def _form(self):
        f = QFormLayout()
        f.setHorizontalSpacing(12)
        f.setVerticalSpacing(8)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        f.setRowWrapPolicy(QFormLayout.DontWrapRows)
        return f

    def _wrap(self, layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)   # 去掉默认内边距，行内控件与字段列左缘对齐
        w.setLayout(layout)
        return w

    def _wrap_left(self, widget):
        """单个控件左对齐、不拉伸填满整行。"""
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(widget)
        h.addStretch(1)
        return self._wrap(h)

    def _group_common(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        f = self._form()
        self.cb_mode = QComboBox()
        for label, _ in MODES:
            self.cb_mode.addItem(label)
        self.cb_mode.setMaximumWidth(190)
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        f.addRow("文字页 OCR", self._wrap_left(self.cb_mode))

        self.cb_imgocr = QCheckBox("识别文字页中插图上的文字")
        self.cb_imgocr.setToolTip("开启后文字页中的插图会被裁出单独识别，原生文字层完整保留；整页扫描件始终会识别，不受此开关影响。关掉后插图不做识别，图中的字搜不到")
        self.cb_imgocr.toggled.connect(self._on_params_changed)
        f.addRow("", self.cb_imgocr)

        # 分辨率 + JPEG 质量 同一行
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(100, 600)
        self.sp_dpi.setSingleStep(50)
        self.sp_dpi.setSuffix(" dpi")
        self.sp_dpi.setMaximumWidth(96)
        self.sp_dpi.setToolTip("150 偏小 · 200 均衡 · 300 最清晰")
        self.sp_dpi.valueChanged.connect(self._on_params_changed)

        self.sp_quality = QSpinBox()
        self.sp_quality.setRange(60, 98)
        self.sp_quality.setMaximumWidth(76)
        self.sp_quality.setToolTip("JPEG 压缩质量，70~95，默认 90")
        self.sp_quality.valueChanged.connect(self._on_params_changed)

        dq = QHBoxLayout()
        dq.setSpacing(10)
        dq.addWidget(self.sp_dpi)
        lab_q = QLabel("JPEG 质量")
        dq.addWidget(lab_q)
        dq.addWidget(self.sp_quality)
        dq.addStretch(1)
        f.addRow("分辨率", self._wrap(dq))

        # 体积限制独立一行，紧跟分辨率
        self.cb_limit = QCheckBox("限制单文件体积")
        self.cb_limit.toggled.connect(self._toggle_limit)
        self.sp_maxmb = QDoubleSpinBox()
        self.sp_maxmb.setRange(1, 2000)
        self.sp_maxmb.setDecimals(0)
        self.sp_maxmb.setSuffix(" MB")
        self.sp_maxmb.setMaximumWidth(90)
        self.sp_maxmb.setToolTip("超限时自动先降 JPEG 质量、再降分辨率")
        self.sp_maxmb.valueChanged.connect(self._on_params_changed)
        lim = QHBoxLayout()
        lim.setSpacing(12)
        lim.addWidget(self.cb_limit)
        lim.addWidget(self.sp_maxmb)
        lim.addStretch(1)
        f.addRow("", self._wrap(lim))

        # 生成书签独立一行
        self.cb_bm = QCheckBox("生成书签")
        self.cb_bm.setToolTip("沿用原大纲；没有的从目录页解析生成")
        self.cb_bm.toggled.connect(self._on_params_changed)
        f.addRow("", self.cb_bm)

        # 输出位置（设置区内）
        self.ed_out = QLineEdit()
        self.ed_out.setMinimumWidth(60)
        self.ed_out.setPlaceholderText("留空 = 源文件所在目录")
        self.ed_out.setToolTip("留空 = 源文件所在目录（原名-双层.pdf）")
        self.ed_out.textChanged.connect(self._on_params_changed)
        self.ed_out.textChanged.connect(
            lambda t: self.ed_out.setToolTip(t or "留空 = 源文件所在目录（原名-双层.pdf）"))
        self.ed_out.editingFinished.connect(lambda: self.ed_out.setCursorPosition(0))
        btn_out_pick = make_btn("更改目录…", kind="link")
        btn_out_pick.clicked.connect(self._pick_out)
        orow = QHBoxLayout()
        orow.setSpacing(4)
        orow.addWidget(self.ed_out, 1)
        f.addRow("输出位置", self._wrap(orow))
        # 更改…：单独放在输出位置的下一行
        f.addRow("", btn_out_pick)
        v.addLayout(f)
        return box

    def _group_advanced(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        f = self._form()
        self.sp_threads = QSpinBox()
        self.sp_threads.setRange(0, 32)
        self.sp_threads.setMaximumWidth(72)
        self.sp_threads.setSpecialValueText("自动")
        self.sp_threads.setToolTip("默认 3，处理时整机不卡；自动 = 用满所有核心")
        self.sp_threads.valueChanged.connect(self._on_params_changed)
        th_row = QHBoxLayout()
        th_row.setSpacing(10)
        th_row.addWidget(self.sp_threads)
        th_hint = QLabel("默认 3 · 自动 = 用满核心")
        th_hint.setObjectName("hint")
        th_row.addWidget(th_hint, 1)
        f.addRow("线程数", self._wrap(th_row))

        self.cb_cache = QCheckBox("使用缓存（同样内容不重复识别）")
        self.cb_cache.toggled.connect(self._sync_cache_row)
        f.addRow("", self.cb_cache)

        lab_cache = QLabel("缓存位置")
        self.ed_cache = QLineEdit()
        self.ed_cache.setMinimumWidth(60)
        btn_cache_pick = make_btn("更改目录…", kind="link")
        btn_cache_pick.clicked.connect(self._pick_cache)
        btn_cache_reset = make_btn("恢复默认", kind="link")
        btn_cache_reset.setToolTip("恢复为系统默认缓存位置")
        btn_cache_reset.clicked.connect(self._reset_cache)

        # 打开缓存文件夹：与更改/恢复默认同行，贴近缓存位置行
        self.btn_cache_open = make_btn("打开缓存文件夹", kind="link")
        self.btn_cache_open.clicked.connect(
            lambda: self._open_path(self.ed_cache.text().strip()))
        acts = QHBoxLayout()
        acts.setSpacing(12)
        acts.addWidget(btn_cache_pick)
        acts.addWidget(btn_cache_reset)
        acts.addWidget(self.btn_cache_open)
        acts.addStretch(1)
        cbox = QVBoxLayout()
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.setSpacing(2)
        cbox.addWidget(self.ed_cache)
        cbox.addLayout(acts)
        self.w_cache_row = self._wrap(cbox)
        self.lb_cache = lab_cache
        f.addRow(lab_cache, self.w_cache_row)
        v.addLayout(f)
        return box

    # ---------------------------------------------------------------- 配置
    def _load_into_widgets(self):
        c = self.cfg
        self.sp_dpi.setValue(int(c["dpi"]))
        self.sp_quality.setValue(int(c["quality"]))
        self.cb_limit.setChecked(bool(c["limit_on"]))
        self.sp_maxmb.setValue(float(c["max_mb"]))
        self.sp_maxmb.setEnabled(bool(c["limit_on"]))
        self.cb_mode.setCurrentIndex(0 if c["native_mode"] == "reuse" else 1)
        self._imgocr_saved = bool(c["image_ocr"])
        self.cb_imgocr.setChecked(self._imgocr_saved)
        self.cb_bm.setChecked(bool(c["bookmarks"]))
        self.sp_threads.setValue(int(c["threads"]))
        self.cb_cache.setChecked(bool(c["cache"]))
        self.ed_cache.setText(c["cache_dir"])
        self.ed_out.setText(c["out_dir"])
        for e in (self.ed_cache, self.ed_out):
            e.setToolTip(e.text())
            e.setCursorPosition(0)
        self.seg_theme.set_code(c["theme"] if c["theme"] in ("auto", "light", "dark") else "auto")
        self.sec_advanced.set_expanded(bool(c.get("advanced_open")))

    def _opts(self):
        mode = MODES[self.cb_mode.currentIndex()][1]
        return {
            "dpi": self.sp_dpi.value(),
            "quality": self.sp_quality.value(),
            "max_mb": float(self.sp_maxmb.value()) if self.cb_limit.isChecked() else 0.0,
            "native_mode": mode,
            "image_ocr": True if mode == "ocr" else self.cb_imgocr.isChecked(),
            "threads": self.sp_threads.value(),
            "gpu": False,   # CUDA 实测不可用（缺 cuBLAS/cuDNN），界面不提供开关
            "bookmarks": self.cb_bm.isChecked(),
            "cache": self.cb_cache.isChecked(),
            "cache_dir": self.ed_cache.text().strip() or default_cache_dir(),
            "out_dir": self.ed_out.text().strip(),
        }

    def _cfg_now(self):
        o = self._opts()
        o["limit_on"] = self.cb_limit.isChecked()
        o["theme"] = self.seg_theme.code() or "auto"
        o["advanced_open"] = self.sec_advanced.is_expanded()
        return o

    # ---------------------------------------------------------------- 主题
    def _effective_theme(self):
        code = self.seg_theme.code() or "auto"
        return ("dark" if system_is_dark() else "light") if code == "auto" else code

    def _apply_theme(self):
        app = QApplication.instance()
        sheet = qss(self._effective_theme())
        if app is not None:
            app.setStyleSheet(sheet)
        else:
            self.setStyleSheet(sheet)
        self._refresh_log_state_color()

    def _on_theme(self, *_):
        self._apply_theme()
        if getattr(self, "_loading", False):
            return
        self.cfg = self._cfg_now()
        save_cfg(self.cfg)

    def _watch_system_theme(self):
        """跟随系统：Qt ≥ 6.5 可监听系统深浅色切换；老环境退化为 3 秒轮询。"""
        try:
            hints = QGuiApplication.styleHints()
            hints.colorSchemeChanged.connect(self._on_system_scheme)
            self._scheme_watch = hints
        except Exception:
            from PySide6.QtCore import QTimer
            self._last_dark = system_is_dark()
            self._theme_timer = QTimer(self)
            self._theme_timer.timeout.connect(self._poll_system_scheme)
            self._theme_timer.start(3000)

    def _on_system_scheme(self, *_):
        if (self.seg_theme.code() or "auto") == "auto":
            self._apply_theme()

    def _poll_system_scheme(self):
        dark = system_is_dark()
        if dark != self._last_dark:
            self._last_dark = dark
            self._on_system_scheme()

    # ---------------------------------------------------------------- 联动
    def _on_mode_changed(self, *_):
        self._sync_image_ocr()
        self._on_params_changed()

    def _sync_image_ocr(self):
        if self.cb_mode.currentIndex() == 0:
            self.cb_imgocr.setEnabled(True)
            self.cb_imgocr.setChecked(self._imgocr_saved)
        else:
            self._imgocr_saved = self.cb_imgocr.isChecked()
            self.cb_imgocr.setChecked(False)
            self.cb_imgocr.setEnabled(False)

    def _sync_cache_row(self, *_):
        on = self.cb_cache.isChecked()
        self.lb_cache.setVisible(on)
        self.w_cache_row.setVisible(on)   # 操作按钮在 w_cache_row 内部，随它一起显隐
        self._on_params_changed()

    def _toggle_limit(self, on):
        self.sp_maxmb.setEnabled(on)
        self._on_params_changed()

    def _on_advanced_toggled(self, _on):
        if getattr(self, "_loading", False):
            return
        self.cfg = self._cfg_now()
        save_cfg(self.cfg)

    def _on_params_changed(self, *_):
        """完成/失败/停止态下改任何参数 → 回到就绪态，文件状态复位为等待。"""
        if getattr(self, "_loading", False):
            return
        if self.state in (self.STATE_DONE, self.STATE_FAILED, self.STATE_STOPPED):
            self.state = self.STATE_READY if self.tree.count() else self.STATE_EMPTY
            for row in range(self.tree.count()):
                self.tree.set_status(row, "wait")
            self.result_bar.setVisible(False)
            self._apply_state()

    # ---------------------------------------------------------------- 文件
    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF", "", "PDF 文件 (*.pdf);;所有文件 (*.*)")
        self._add_paths(paths)

    def _add_paths(self, paths):
        added = 0
        existing = {self.tree.path_at(r) for r in range(self.tree.count())}
        for p in paths:
            p = os.path.normpath(p)
            if p in existing or not os.path.isfile(p):
                continue
            pages = page_count(p)
            try:
                size_text = human_size(os.path.getsize(p))
            except OSError:
                size_text = "—"
            self._add_row(p, pages, size_text)
            existing.add(p)
            added += 1
        if added:
            if self.state in (self.STATE_EMPTY, self.STATE_DONE,
                              self.STATE_STOPPED, self.STATE_FAILED):
                self.state = self.STATE_READY
            self._apply_state()

    def _add_row(self, path, pages, size_text):
        """添加一行（预览/测试可直接调用）。"""
        return self.tree.add_row(path, pages, size_text)

    def _remove_selected(self):
        rows = self.tree.selected_rows()
        if not rows:
            return
        self.tree.remove_rows(rows)
        self.state = self.STATE_READY if self.tree.count() else self.STATE_EMPTY
        self._apply_state()

    def _clear_files(self):
        if not self.tree.count():
            return
        dlg = ConfirmAsk(self, "清空列表？",
                         "只会把文件从列表里移除，不会删除磁盘上的原文件。",
                         "清空列表", "取消")
        if dlg.exec() == QDialog.Accepted:
            self.tree.clear()
            self.state = self.STATE_EMPTY
            self._apply_state()

    # ---------------------------------------------------------------- 目录
    def _pick_cache(self):
        d = QFileDialog.getExistingDirectory(self, "选择缓存文件夹", self.ed_cache.text())
        if d:
            self.ed_cache.setText(os.path.normpath(d))
            self._on_params_changed()

    def _reset_cache(self):
        self.ed_cache.setText(default_cache_dir())
        self._on_params_changed()
        self.log.appendPlainText("已恢复默认缓存位置")

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.ed_out.text())
        if d:
            self.ed_out.setText(os.path.normpath(d))

    def _open_path(self, path):
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass

    def _open_outdir(self):
        od = self.ed_out.text().strip()
        if od and os.path.isdir(od):
            self._open_path(od)
        elif self.last_out and os.path.exists(self.last_out):
            self._open_path(os.path.dirname(self.last_out))
        elif self.tree.count():
            self._open_path(os.path.dirname(self.tree.path_at(0)))

    def out_path_for(self, src):
        name = os.path.splitext(os.path.basename(src))[0] + "-双层.pdf"
        od = self.ed_out.text().strip()
        return os.path.join(od, name) if od else os.path.splitext(src)[0] + "-双层.pdf"

    # ---------------------------------------------------------------- 帮助
    def _show_help(self):
        from .help import HelpDialog
        HelpDialog(self).exec()

    # ---------------------------------------------------------------- 日志状态
    def _log_state(self, text, color_key="muted"):
        self._log_state_text, self._log_state_color = text, color_key
        c = TOKENS[self._effective_theme()][color_key]
        self.lb_log_state.setStyleSheet(f"color: {c};")
        self._elide_log_state()

    def _elide_log_state(self):
        """按标题栏剩余宽度对状态文字做省略号收缩，避免生硬截断。"""
        full = f"● {self._log_state_text}"
        fm = self.lb_log_state.fontMetrics()
        w = self.lb_log_state.width()
        self.lb_log_state.setText(
            fm.elidedText(full, Qt.ElideRight, w) if w > 0 else full)
        self.lb_log_state.setToolTip(full)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.lb_log_state and event.type() == QEvent.Resize:
            if hasattr(self, "_log_state_text"):
                self._elide_log_state()
        return super().eventFilter(obj, event)

    def _refresh_log_state_color(self):
        if hasattr(self, "_log_state_text"):
            self._log_state(self._log_state_text, self._log_state_color)

    # ---------------------------------------------------------------- 状态
    @staticmethod
    def _restyle(w):
        w.style().unpolish(w)
        w.style().polish(w)

    def _apply_state(self):
        s = self.state
        has_files = bool(self.tree.count())
        sel = bool(self.tree.selected_rows()) if has_files else False
        busy = s in (self.STATE_RUNNING, self.STATE_STOPPING)

        self.stack.setCurrentIndex(1 if has_files else 0)
        self.btn_add_head.setVisible(has_files and not busy)
        self.btn_clear.setVisible(has_files and not busy)
        self.btn_remove.setVisible(has_files and sel and not busy)

        for w in (self.tree, self.cb_mode, self.sp_dpi, self.sp_quality,
                  self.cb_bm, self.cb_limit, self.sp_maxmb, self.sp_threads,
                  self.cb_cache, self.ed_cache, self.ed_out,
                  self.btn_add_head, self.btn_cache_open, self.seg_theme):
            w.setEnabled(not busy)
        self.cb_imgocr.setEnabled((not busy) and self.cb_mode.currentIndex() == 0)

        self.btn_primary.setObjectName("primary")
        self.btn_primary.setEnabled(True)
        if s == self.STATE_EMPTY:
            self.btn_primary.setText("生成双层PDF")
            self.btn_primary.setEnabled(False)
            self.btn_primary.setToolTip("请先添加 PDF 文件")
        elif s == self.STATE_READY:
            self.btn_primary.setText("生成双层PDF")
            self.btn_primary.setToolTip("")
        elif s in (self.STATE_RUNNING, self.STATE_STOPPING):
            self.btn_primary.setText("正在生成…")
            self.btn_primary.setEnabled(False)
        elif s == self.STATE_STOPPED:
            self.btn_primary.setText("重新生成")
        elif s == self.STATE_DONE:
            self.btn_primary.setText("再次生成")
        elif s == self.STATE_FAILED:
            self.btn_primary.setText("重试")

        self.btn_secondary.setObjectName("danger")
        if s == self.STATE_RUNNING:
            self.btn_secondary.setText("停止")
            self.btn_secondary.setVisible(True)
            self.btn_secondary.setEnabled(True)
        elif s == self.STATE_STOPPING:
            self.btn_secondary.setText("正在停止…")
            self.btn_secondary.setVisible(True)
            self.btn_secondary.setEnabled(False)
        else:
            self.btn_secondary.setVisible(False)

        self._restyle(self.btn_secondary)
        self._restyle(self.btn_primary)
        text, color = {
            self.STATE_EMPTY: ("等待开始", "muted"),
            self.STATE_READY: (f"等待开始 · {self.tree.count()} 个文件", "muted"),
            self.STATE_RUNNING: ("运行中", "accent"),
            self.STATE_STOPPING: ("正在停止", "accent"),
            self.STATE_STOPPED: ("已停止", "danger"),
            self.STATE_DONE: ("已完成", "success"),
            self.STATE_FAILED: ("出错", "danger"),
        }[s]
        self._log_state(text, color)

    # ---------------------------------------------------------------- 交互
    def _on_primary(self):
        if self.state in (self.STATE_RUNNING, self.STATE_STOPPING):
            return
        if not self.tree.count():
            return
        self._confirm_and_start()

    def _on_secondary(self):
        if self.state == self.STATE_RUNNING:
            dlg = ConfirmAsk(self, "停止生成？",
                             "会丢弃本次未写完的结果，已处理的页不会保留。",
                             "停止生成", "继续生成")
            if dlg.exec() == QDialog.Accepted and self.worker:
                self.worker.cancelled = True
                self.state = self.STATE_STOPPING
                self._apply_state()

    def _build_jobs(self):
        """生成任务列表；同名输出自动追加 -2、-3，返回 (jobs, renamed, existing)。"""
        jobs, renamed, existing = [], [], []
        used = set()
        for row in range(self.tree.count()):
            src = self.tree.path_at(row)
            pages_text = self.tree.topLevelItem(row).text(1)
            pages = int(pages_text) if pages_text.isdigit() else 0
            dst = self.out_path_for(src)
            base, ext = os.path.splitext(dst)
            n = 1
            while dst.lower() in used:
                n += 1
                dst = f"{base}-{n}{ext}"
            if n > 1:
                renamed.append(dst)
            used.add(dst.lower())
            if os.path.exists(dst):
                existing.append(dst)
            jobs.append({"row": row, "src": src, "dst": dst, "pages": pages})
        return jobs, renamed, existing

    def _confirm_and_start(self):
        o = self._opts()
        jobs, renamed, existing = self._build_jobs()
        total = sum(j["pages"] for j in jobs)
        summary = [
            ("输出", o["out_dir"] or "源文件所在目录（原名-双层.pdf）"),
            ("识别", f"{'复用现成文字' if o['native_mode'] == 'reuse' else '整页 OCR'} · "
                     f"{o['dpi']} dpi · 图片识别：{'开' if o['image_ocr'] else '关'}"),
            ("质量", f"JPEG {o['quality']} · 书签：{'开' if o['bookmarks'] else '关'} · "
                     f"体积限制：{'≤ %g MB' % o['max_mb'] if o['max_mb'] else '关'}"),
            ("性能", f"{o['threads'] or '自动'} 线程 · 缓存：{'开' if o['cache'] else '关'}"),
        ]
        warnings = []
        if renamed:
            warnings.append("注意：有同名输出文件，已自动改名（原名-双层-2.pdf 等），详见日志。")
        if existing:
            warnings.append(f"注意：{len(existing)} 个输出文件已存在，将被覆盖"
                            "（若正被阅读器打开会自动改存带时间戳的名字）。")
        dlg = ConfirmStart(self, len(jobs), total, summary, warnings)
        if dlg.exec() == QDialog.Accepted:
            self._start(o, jobs, renamed)

    # ---------------------------------------------------------------- 运行
    def _start(self, o, jobs, renamed):
        if o["out_dir"]:
            try:
                os.makedirs(o["out_dir"], exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "输出文件夹", f"无法创建/写入：{o['out_dir']}\n{e}")
                return
        self.cfg = self._cfg_now()
        save_cfg(self.cfg)
        self.log.clear()
        self.outputs = []
        self.last_out = None
        self.result_bar.setVisible(False)
        for row in range(self.tree.count()):
            self.tree.set_status(row, "wait")
        for dst in renamed:
            self.log.appendPlainText(f"同名输出已改名 → {dst}")
        self.state = self.STATE_RUNNING
        self._apply_state()

        self.worker = Worker(o, jobs, self)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.overall.connect(self._on_overall)
        self.worker.row_state.connect(self._on_row_state)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_overall(self, pct, text):
        # 无底栏：整体进度文字（含页码与预计剩余时间）显示在日志标题栏状态点
        self._log_state(text, "accent")

    def _on_row_state(self, row, kind, progress):
        self.tree.set_status(row, kind, progress)

    def _on_file_done(self, row, out, size_mb):
        self.outputs.append((row, out, size_mb))
        self.last_out = out

    def _on_finished(self, done, failed, cancelled, elapsed):
        if cancelled:
            self.state = self.STATE_STOPPED
        elif done:
            self.state = self.STATE_DONE      # 部分成功也算完成，摘要里标出失败数
        else:
            self.state = self.STATE_FAILED
        self._apply_state()

        n_total = self.tree.count()
        if self.state == self.STATE_DONE:
            total_mb = sum(s for _, _, s in self.outputs)
            out_dir = os.path.dirname(self.last_out) if self.last_out else ""
            if failed:
                text = (f"完成 {done}/{n_total} 个文件 · {failed} 个失败 · "
                        f"共 {human_size(total_mb * 1e6)} · 用时 {human_seconds(elapsed)}"
                        + (f" · 输出到 {out_dir}" if out_dir else ""))
                kind, lab_id = "warn", "resultWarn"
            else:
                text = (f"完成 {done}/{n_total} 个文件 · 共 {human_size(total_mb * 1e6)} · "
                        f"用时 {human_seconds(elapsed)}"
                        + (f" · 输出到 {out_dir}" if out_dir else ""))
                kind, lab_id = "ok", "resultOk"
        elif self.state == self.STATE_STOPPED:
            text = "已停止 · 本次未输出结果"
            kind, lab_id = "warn", "resultWarn"
        else:
            text = "生成失败 · 详见上方日志"
            kind, lab_id = "err", "resultErr"

        self.result_bar.setProperty("kind", kind)
        self._restyle(self.result_bar)
        self.lb_result.setObjectName(lab_id)
        self._restyle(self.lb_result)
        self.lb_result.setText(text)
        self.result_bar.setVisible(True)
