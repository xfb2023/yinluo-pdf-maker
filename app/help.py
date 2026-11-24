# -*- coding: utf-8 -*-
"""使用说明弹窗。内容内嵌，打包后也能看。"""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QTextBrowser, QVBoxLayout

from .widgets import make_btn

HELP_HTML = """
<h2>隐络双层PDF制作器 使用说明</h2>

<h3>这是什么</h3>
<p>把普通 PDF 转成「双层 PDF」：第一层是整页彩色图像（版式、红章、手签、图纸原样保留），
第二层是与图像逐字对齐的<b>不可见文字</b>，可以框选、复制、检索。
全部在本机运算，不联网、不上传任何文件。</p>

<h3>怎么用</h3>
<ol>
<li>把 PDF 拖进窗口（可一次多个），或点「选择 PDF 文件…」。</li>
<li>按需调整参数（通常保持默认即可）。</li>
<li>点「生成双层PDF」→ 确认参数 → 开始。完成后在结果条里打开输出文件夹。</li>
</ol>
<p>输出文件默认与源文件同目录，名字为「原名-双层.pdf」。
若同名文件正被阅读器打开，会自动改存为带时间戳的名字。</p>

<h3>参数说明</h3>
<ul>
<li><b>文字页 OCR</b>：复用现成文字（快，推荐）＝ 纯文字页直接用原文字、不跑识别，零乱码；
整页 OCR（慢）＝ 纯文字页也整页识别一遍。</li>
<li><b>识别文字页中插图上的文字</b>：开启后文字页中的插图会被裁出单独做 OCR，原生文字层完整保留；
整页扫描件始终会识别，不受此开关影响。关掉后插图不做识别，图中的字搜不到。</li>
<li><b>分辨率</b>：文字页渲染分辨率。150 偏小，200 均衡（默认），300 最清晰。</li>
<li><b>JPEG 质量</b>：图像层压缩质量，70~95，默认 90。</li>
<li><b>书签</b>：源文件自带大纲的原样沿用；没有的从「目录」页解析生成。</li>
<li><b>限制单文件体积</b>：默认关闭、不压缩。启用后超限时自动先降 JPEG 质量、再降分辨率，
日志会报告实际用量。</li>
</ul>
<p><b>高级设置</b>（一般用不到）：</p>
<ul>
<li><b>线程数</b>：默认 3，处理时整机不卡；调到「自动」＝用满所有 CPU 核心，最快。</li>
<li><b>使用缓存</b>：按页缓存识别结果（页面内容变一个像素就会重识别，不会误用旧结果），
改一页只重跑一页。缓存位置可自定义。</li>
</ul>

<h3>检查输出是否合格</h3>
<ul>
<li>Ctrl+F 能搜到正文里的词 → 有文字层</li>
<li>鼠标能框选、复制页面文字 → 文字层位置正确</li>
<li>左侧书签栏能看到章节 → 书签生成成功</li>
<li>放大看红章、签名、图纸 → 图像层保真</li>
</ul>

<h3>常见问题</h3>
<p><b>文件太大，想压到 30MB 以内？</b><br>
勾选「限制单文件体积」并填 30。若提示已压到极限，说明页数太多，
建议按章节拆成多个文件分别转换。</p>
<p><b>整页横躺 90° 的扫描件能自动转正吗？</b><br>
不会。整页旋转 90° 会改变页面长宽方向，请先用阅读器把页面转正另存再转换。
（页内横竖混排的证书、执照可以自动处理。）</p>
<p><b>扫描页识别有错字？</b><br>
OCR 不可能 100% 准确，印刷体通常在 98% 左右。文字层只用于检索和复制，
页面显示始终是原图。人名、金额、日期建议抽查。</p>
<p><b>提示「目标文件被占用」？</b><br>
输出文件正被 PDF 阅读器打开。关闭后重跑，或直接用自动改存的文件。</p>

<h3>兼容性</h3>
<p>输出文件兼容 Adobe Acrobat、福昕、WPS、Chrome 及国网电子商务平台；
文件属性（Producer / Creator / 标题 / 作者 / 时间）与源文件保持一致。</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.setModal(True)
        self.resize(640, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        text = QTextBrowser()
        text.setHtml(HELP_HTML)
        text.setOpenExternalLinks(False)
        lay.addWidget(text, 1)
        bar = QHBoxLayout()
        bar.addStretch(1)
        close = make_btn("关闭", primary=True)
        close.setMinimumSize(120, 36)
        close.clicked.connect(self.accept)
        bar.addWidget(close)
        lay.addLayout(bar)
