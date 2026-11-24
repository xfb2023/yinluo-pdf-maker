# -*- coding: utf-8 -*-
"""设计令牌与 QSS。浅色为默认主风格，深色整套重调。

间距体系基于 8px 网格（8 / 12 / 16 / 24），圆角统一：
卡片 12px，控件 8px，徽章/进度 4~9px。
"""

TOKENS = {
    "light": {
        "bg": "#F4F5F7", "surface": "#FFFFFF", "surfaceAlt": "#F6F7F9",
        "border": "#E3E6EA", "borderStrong": "#D2D7DD",
        "text": "#1B1F24", "muted": "#667085", "faint": "#98A2B3",
        "accent": "#16A34A", "accentHi": "#15803D", "accentSoft": "#E9F7EE",
        "onAccent": "#FFFFFF",
        "success": "#15803D", "successSoft": "#E7F6EC",
        "danger": "#DC2626", "dangerSoft": "#FDECEC",
        "warning": "#B45309", "warningSoft": "#FDF3E3",
        "log": "#FAFBFC", "sel": "#E9F7EE", "focus": "#8FD3A8",
    },
    "dark": {
        "bg": "#101214", "surface": "#191C20", "surfaceAlt": "#21252B",
        "border": "#2C3138", "borderStrong": "#3A4149",
        "text": "#E8EAED", "muted": "#9AA3AF", "faint": "#6B7280",
        "accent": "#34C77B", "accentHi": "#5BD695", "accentSoft": "#1D3527",
        "onAccent": "#0B1220",
        "success": "#4CC38A", "successSoft": "#1E3A2C",
        "danger": "#F06A5F", "dangerSoft": "#3E2420",
        "warning": "#E5A34D", "warningSoft": "#3A2E1B",
        "log": "#14171B", "sel": "#1F3A2A", "focus": "#3E7D58",
    },
}


def qss(theme: str) -> str:
    t = TOKENS[theme]
    return f"""
    * {{ outline: 0; }}
    QWidget {{
        background: {t['bg']}; color: {t['text']};
        font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px;
    }}
    QDialog, QMainWindow {{ background: {t['bg']}; }}

    /* ---------- 文字层级 ---------- */
    QLabel {{ background: transparent; }}
    QLabel#h1 {{ font-size: 20px; font-weight: 600; }}
    QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
    QLabel#sub {{ color: {t['muted']}; font-size: 12px; }}
    QLabel#section {{
        font-size: 12px; font-weight: 600; color: {t['muted']};
        letter-spacing: 1px;
    }}
    QLabel#hint, QLabel#stat {{ color: {t['muted']}; font-size: 12px; }}
    QLabel#warn {{ color: {t['warning']}; font-size: 12px; }}

    /* ---------- 卡片 ---------- */
    QFrame#card {{
        background: {t['surface']};
        border: 1px solid {t['border']}; border-radius: 12px;
    }}
    QFrame#summary {{
        background: {t['surfaceAlt']};
        border: 1px solid {t['border']}; border-radius: 10px;
    }}
    QFrame#drop {{
        background: {t['surfaceAlt']};
        border: 2px dashed {t['borderStrong']}; border-radius: 12px;
    }}
    QFrame#hrule {{ background: {t['border']}; max-height: 1px; border: 0; }}

    /* 结果条 */
    QFrame#result {{ border-radius: 10px; border: 1px solid transparent; }}
    QFrame#result[kind="ok"] {{ background: {t['successSoft']}; border-color: {t['success']}; }}
    QFrame#result[kind="err"] {{ background: {t['dangerSoft']}; border-color: {t['danger']}; }}
    QFrame#result[kind="warn"] {{ background: {t['warningSoft']}; border-color: {t['warning']}; }}
    QLabel#resultOk {{ color: {t['success']}; font-weight: 600; }}
    QLabel#resultErr {{ color: {t['danger']}; font-weight: 600; }}
    QLabel#resultWarn {{ color: {t['warning']}; font-weight: 600; }}

    /* ---------- 文件表 ---------- */
    QTreeWidget {{
        background: {t['surface']};
        border: 1px solid {t['border']}; border-radius: 10px;
        selection-background-color: {t['sel']}; selection-color: {t['text']};
    }}
    QTreeWidget::item {{ padding: 7px 4px; border: 0; }}
    QTreeWidget::item:hover {{ background: {t['surfaceAlt']}; }}
    QTreeWidget::item:selected {{ background: {t['sel']}; }}
    QHeaderView::section {{
        background: {t['surface']}; color: {t['muted']}; font-size: 12px;
        border: 0; border-bottom: 1px solid {t['border']}; padding: 7px 6px;
    }}

    /* 状态徽章 */
    QLabel#badge {{ padding: 3px 10px; border-radius: 10px; font-size: 11px; }}
    QLabel#badge[kind="wait"] {{ background: {t['surfaceAlt']}; color: {t['muted']}; }}
    QLabel#badge[kind="run"]  {{ background: {t['accentSoft']}; color: {t['accent']}; }}
    QLabel#badge[kind="ok"]   {{ background: {t['successSoft']}; color: {t['success']}; }}
    QLabel#badge[kind="err"]  {{ background: {t['dangerSoft']}; color: {t['danger']}; }}
    QLabel#badge[kind="stop"] {{ background: {t['warningSoft']}; color: {t['warning']}; }}

    /* ---------- 输入控件 ---------- */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {t['surface']};
        border: 1px solid {t['border']}; border-radius: 8px;
        padding: 4px 10px; min-height: 16px;
        selection-background-color: {t['accent']};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: {t['borderStrong']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {t['accent']};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {t['faint']}; background: {t['surfaceAlt']};
    }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {t['surface']}; border: 1px solid {t['border']};
        selection-background-color: {t['sel']}; selection-color: {t['text']};
        padding: 4px;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 18px; border: 0; }}

    QCheckBox {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1px solid {t['borderStrong']}; background: {t['surface']};
    }}
    QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
    QCheckBox:disabled {{ color: {t['faint']}; }}

    /* ---------- 按钮 ---------- */
    QPushButton {{
        background: {t['surface']};
        border: 1px solid {t['border']}; border-radius: 8px;
        padding: 7px 16px; min-height: 18px;
    }}
    QPushButton:hover {{ border-color: {t['accent']}; color: {t['accent']}; }}
    QPushButton:pressed {{ background: {t['surfaceAlt']}; }}
    QPushButton:disabled {{
        color: {t['faint']}; background: {t['surfaceAlt']}; border-color: {t['border']};
    }}
    QPushButton#primary {{
        background: {t['accent']}; border: 1px solid {t['accent']};
        color: {t['onAccent']}; font-weight: 600; font-size: 14px;
        border-radius: 10px; padding: 10px 26px;
    }}
    QPushButton#primary:hover {{ background: {t['accentHi']}; border-color: {t['accentHi']}; color: {t['onAccent']}; }}
    QPushButton#primary:disabled {{
        background: {t['border']}; border-color: {t['border']}; color: {t['faint']};
    }}
    QPushButton#danger {{ color: {t['danger']}; }}
    QPushButton#danger:hover {{ border-color: {t['danger']}; color: {t['danger']}; }}
    QPushButton#link {{
        background: transparent; border: 0; color: {t['accent']};
        padding: 4px 6px; min-height: 16px;
    }}
    QPushButton#link:hover {{ color: {t['accentHi']}; text-decoration: underline; }}
    QPushButton#quiet {{ background: transparent; border: 0; color: {t['muted']}; padding: 4px 6px; }}
    QPushButton#quiet:hover {{ color: {t['danger']}; }}
    QToolButton#icon {{
        background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px;
    }}
    QToolButton#icon:hover {{ border-color: {t['border']}; background: {t['surfaceAlt']}; }}

    /* 主题分段开关 */
    QFrame#seg {{
        background: {t['surfaceAlt']};
        border: 1px solid {t['border']}; border-radius: 15px;
    }}
    QPushButton#segBtn {{
        background: transparent; border: 0; border-radius: 12px;
        color: {t['muted']}; padding: 4px 12px; min-height: 16px; font-size: 12px;
    }}
    QPushButton#segBtn:hover {{ color: {t['text']}; }}
    QPushButton#segBtn:checked {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; font-weight: 600;
    }}

    /* 折叠区标题 */
    QToolButton#fold {{
        background: transparent; border: 0; color: {t['muted']};
        font-size: 12px; font-weight: 600; padding: 4px 2px;
    }}
    QToolButton#fold:hover {{ color: {t['text']}; }}

    /* ---------- 进度 ---------- */
    QProgressBar {{
        background: {t['surfaceAlt']}; border: 1px solid {t['border']};
        border-radius: 5px; min-height: 10px; max-height: 10px;
    }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
    QProgressBar#done::chunk {{ background: {t['success']}; }}
    QProgressBar#stopped::chunk {{ background: {t['danger']}; }}
    QProgressBar#mini {{
        min-height: 5px; max-height: 5px; border: 0; border-radius: 2px;
        background: {t['border']};
    }}
    QProgressBar#mini::chunk {{ background: {t['accent']}; border-radius: 2px; }}

    /* ---------- 日志 ---------- */
    QPlainTextEdit {{
        background: {t['log']}; border: 1px solid {t['border']}; border-radius: 10px;
        padding: 8px; font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px;
    }}

    /* ---------- 滚动 ---------- */
    QScrollArea {{ border: 0; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['borderStrong']}; border-radius: 5px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t['borderStrong']}; border-radius: 5px; min-width: 28px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QToolTip {{
        background: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border']}; padding: 6px 8px;
    }}
    """
