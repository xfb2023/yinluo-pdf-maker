# -*- coding: utf-8 -*-
"""dl.py —— 彩色双层PDF生成器（纯本地，不联网，不上传）

第1层 = 整页彩色位图（源页栅格化，100% 保留原始版面效果）
第2层 = 不可见文字（render_mode=3），逐字定位在图片对应位置

策略：
  · 源页本就有文字层（Word 生成）→ 直接复用字形坐标，**不做 OCR，零乱码**
  · 纯扫描页 → OCR；先按检测框角度测偏斜，>0.5° 才旋转并重新识别
"""
import os, sys, math, json, re
import numpy as np
import cv2
import pymupdf

# 控制台里交给 Windows 自己处理宽字符；只有输出被重定向（管道/文件）时才强制 UTF-8
try:
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_FONT_CACHE = {}
CACHE_VER = "v11"   # v11：检测器 det_limit_side_len 736→1440（修复高 dpi 漏行）；改算法/语义必须升版本


class Cancelled(Exception):
    """调用方通过 should_stop 请求中止；由上层决定如何提示。"""


# ----------------------------------------------------------------------------
# 字体（只用于不可见文字层，不影响显示效果）
# ----------------------------------------------------------------------------
def get_font():
    """文字层字体。优先系统宋体——子集后 BaseFont 就是 SimSun，
    与 Word 导出的文件一致，不会出现 OCR 专用字体名。"""
    if "f" in _FONT_CACHE:
        return _FONT_CACHE["f"]
    for path in (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simhei.ttf",
                 r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    f = pymupdf.Font(fontbuffer=fh.read())
                if f.text_length("水土保持", 12) > 10:
                    _FONT_CACHE["f"] = (path, f)
                    return _FONT_CACHE["f"]
            except Exception:
                pass
    for name in ("china-s", "china-t", "cjk", "japan"):
        try:
            f = pymupdf.Font(fontname=name)
            if f.text_length("水土保持", 12) > 10:
                _FONT_CACHE["f"] = (name, f)
                return _FONT_CACHE["f"]
        except Exception:
            pass
    raise RuntimeError("找不到可用中文字体")


# ----------------------------------------------------------------------------
# 页面分类：是"文字页"还是"扫描页"
# ----------------------------------------------------------------------------
def image_coverage(page):
    area = page.rect.width * page.rect.height
    tot = 0.0
    for im in page.get_image_info():
        r = pymupdf.Rect(im["bbox"]) & page.rect
        if not r.is_empty:
            tot += abs(r)
    return min(tot / area, 1.0)


def content_images(page, min_area=0.04, min_width=0.25):
    """页面上的"实质图像"（贴进去的扫描件、证书、发票等）。
    排除页眉页脚的小图标、水印、骑缝章那类重复小图。"""
    W, H = page.rect.width, page.rect.height
    area = W * H
    out = []
    for im in page.get_image_info():
        r = pymupdf.Rect(im["bbox"]) & page.rect
        if r.is_empty:
            continue
        if r.width >= W * min_width and abs(r) >= area * min_area:
            out.append(r)
    return out


def is_native_page(page):
    """是否"完全不需要 OCR"：没有实质图像、且本身有文字。
    有实质图像就一定要 OCR——不管这一页有多少原生文字。"""
    if content_images(page):
        return False
    return bool(page.get_text("text").strip())


def suggest_dpi(page, lo=150, hi=220, factor=1.15):
    """按页内扫描件的有效 dpi 决定栅格化分辨率，避免无意义的上采样。"""
    best = 0.0
    for im in page.get_image_info():
        r = pymupdf.Rect(im["bbox"])
        if r.width < page.rect.width * 0.25 or r.width <= 0:
            continue
        best = max(best, im["width"] / (r.width / 72.0))
    if best <= 0:
        return 150
    return int(min(max(best * factor, lo), hi))


# ----------------------------------------------------------------------------
# 扫描页：黑边裁切
# ----------------------------------------------------------------------------
def measure_border(gray, thresh=45, run=0.93):
    h, w = gray.shape
    top = 0
    while top < h // 4 and (gray[top] < thresh).mean() > run:
        top += 1
    bot = h - 1
    while bot > h * 3 // 4 and (gray[bot] < thresh).mean() > run:
        bot -= 1
    left = 0
    while left < w // 4 and (gray[:, left] < thresh).mean() > run:
        left += 1
    right = w - 1
    while right > w * 3 // 4 and (gray[:, right] < thresh).mean() > run:
        right -= 1
    return left, top, right + 1, bot + 1


def crop_border(rgb):
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    x0, y0, x1, y1 = measure_border(gray)
    if (x1 - x0) > w * 0.5 and (y1 - y0) > h * 0.5 and ((w - (x1 - x0)) > 4 or (h - (y1 - y0)) > 4):
        return rgb[y0:y1, x0:x1], [x0, y0, x1, y1]
    return rgb, None


def rotate(img, deg):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


# ----------------------------------------------------------------------------
# OCR
# ----------------------------------------------------------------------------
_OCR = {}


def available_providers():
    """当前 onnxruntime 能用的执行后端（装的是 CPU 版时只有 CPUExecutionProvider）。"""
    try:
        import onnxruntime as _ort
        return list(_ort.get_available_providers())
    except Exception:
        return []


def gpu_ready():
    """是否真的能用 GPU 推理（需要 onnxruntime-gpu + CUDA 运行库）。"""
    return "CUDAExecutionProvider" in available_providers()


def get_ocr(intra_threads=0, gpu=False):
    """按（线程数, 是否 GPU）缓存引擎实例。intra_threads<=0 表示由运行库自行决定。"""
    key = (int(intra_threads or 0), bool(gpu))
    if key in _OCR:
        return _OCR[key]
    from rapidocr_onnxruntime import RapidOCR
    kw = {"det_limit_side_len": 1440}   # 默认 736 在 300dpi 页面上会漏检拼接缝处的行
    if int(intra_threads or 0) > 0:
        kw["intra_op_num_threads"] = int(intra_threads)
        kw["inter_op_num_threads"] = 1
    if gpu and gpu_ready():
        kw.update(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
    try:
        eng = RapidOCR(**kw)
    except Exception:
        if not kw:
            raise
        # GPU 初始化失败（缺 CUDA 运行库等）→ 退回 CPU，不让整本任务失败
        kw = {k: v for k, v in kw.items() if not k.endswith("_use_cuda")}
        eng = RapidOCR(**kw)
    _OCR[key] = eng
    return eng


def ocr_boxes(rgb, intra_threads=0, gpu=False):
    """[(x0,y0,x1,y1,text,score,angle)] 像素坐标；angle 为检测框上边倾角(度)"""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    res, _ = get_ocr(intra_threads, gpu)(bgr)
    out = []
    if not res:
        return out
    for item in res:
        box, text = item[0], (item[1] or "").strip()
        if not text:
            continue
        pts = [(float(p[0]), float(p[1])) for p in box]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ang = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])) if len(pts) >= 2 else 0.0
        if ang > 45:
            ang -= 90
        elif ang < -45:
            ang += 90
        out.append([min(xs), min(ys), max(xs), max(ys), text, float(item[2]), ang, pts])
    return out


# ----------------------------------------------------------------------------
# 文字层构建（逐字绝对定位）
# ----------------------------------------------------------------------------
def write_invisible(page, items):
    """items: [(x, y_baseline, ch)] —— 已逐字定好位置"""
    _, font = get_font()
    tw = pymupdf.TextWriter(page.rect)
    for x, y, ch, fs in items:
        try:
            tw.append((x, y), ch, font=font, fontsize=fs)
        except Exception:
            pass
    try:
        tw.write_text(page, render_mode=3)
    except TypeError:
        tw.write_text(page, color=(1, 1, 1))


def native_items(page):
    items = []
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                fs = max(sp.get("size", 10), 1.0)
                for ch in sp.get("chars", []):
                    c = ch.get("c", "")
                    if not c or c.strip() == "":
                        continue
                    ox, oy = ch.get("origin", (0.0, 0.0))
                    items.append((ox, oy, c, fs))
    return items


def is_vertical(box, ratio=2.5, min_chars=2):
    """竖排框：高远大于宽，且不止一个字。
    典型场景：一页里既有横排标题，又贴了一张旋转 90° 的扫描件。"""
    w = box[2] - box[0]
    h = box[3] - box[1]
    return h > ratio * max(w, 1) and len(box[4]) >= min_chars


def vertical_direction(bgr, vboxes, ocr=None, sample=3):
    """判断竖排文字读向。做法：把竖框分别顺时针/逆时针转 90° 去识别，
    取平均得分高的那个方向。
    顺时针可读 → 页面上是自下而上；否则自上而下。"""
    eng = ocr or get_ocr()
    picks = sorted(vboxes, key=lambda b: -(b[3] - b[1]))[:sample]
    cw, ccw = [], []
    for b in picks:
        x0, y0, x1, y1 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(bgr.shape[1], x1), min(bgr.shape[0], y1)
        if x1 - x0 < 6 or y1 - y0 < 12:
            continue
        c = bgr[y0:y1, x0:x1]
        for rot, store in ((cv2.ROTATE_90_CLOCKWISE, cw), (cv2.ROTATE_90_COUNTERCLOCKWISE, ccw)):
            try:
                r, _ = eng.text_rec([cv2.rotate(c, rot)])
                store.append(float(r[0][1]) if r else 0.0)
            except Exception:
                store.append(0.0)
    if not cw or not ccw:
        return False
    return (sum(cw) / len(cw)) >= (sum(ccw) / len(ccw))


def vertical_items(vboxes, sx, sy, bottom_up):
    """竖排文字：返回 (页面坐标起点x, 起点y, 文本, 字号)，由 write_vertical 旋转写入。
    写成"整体旋转的一行文本"，这样 get_text 能整串取出（可搜索、可复制）。"""
    _, font = get_font()
    ang = 90 if bottom_up else -90
    lines = []
    for b in vboxes:
        x0, y0, x1, y1, t, s, a, q = b
        X0, Y0, X1, Y1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
        w_pt, h_pt = X1 - X0, Y1 - Y0
        if w_pt <= 0.5 or h_pt <= 0.5 or not t.strip():
            continue
        unit = font.text_length(t, fontsize=1.0) or 1.0
        fs = max(min(w_pt * 0.95, h_pt / unit), 3.0)
        xc = (X0 + X1) / 2.0
        if bottom_up:                      # 自下而上：基线从框底起，字头朝左
            lines.append((xc + 0.39 * fs, Y1, t, fs))
        else:                              # 自上而下：基线从框顶起，字头朝右
            lines.append((xc - 0.39 * fs, Y0, t, fs))
    return lines, ang


def write_vertical(page, lines, ang):
    """逐行旋转写入。morph 的旋转中心必须与该行写入点重合，否则整行会被丢弃。"""
    if not lines:
        return
    _, font = get_font()
    for px, py, t, fs in lines:
        tw = pymupdf.TextWriter(page.rect)
        try:
            tw.append((px, py), t, font=font, fontsize=fs)
            tw.write_text(page, morph=(pymupdf.Point(px, py), pymupdf.Matrix(ang)),
                          render_mode=3)
        except TypeError:
            try:
                tw.write_text(page, morph=(pymupdf.Point(px, py), pymupdf.Matrix(ang)),
                              color=(1, 1, 1))
            except Exception:
                pass
        except Exception:
            pass


def ocr_items(boxes, sx, sy):
    """把检测框文字映射到页面坐标。
    注意：检测框坐标是"像素"，必须换算成"磅"再当字号用，否则字框会被放大好几倍。"""
    _, font = get_font()
    items = []
    for b in boxes:
        quad = b[7] if len(b) > 7 else None
        if quad and len(quad) == 4:
            tl, tr, br, bl = quad
        else:
            x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
            tl, tr, br, bl = (x0, y0), (x1, y0), (x1, y1), (x0, y1)
        # 像素 -> 磅
        P = lambda pt: (pt[0] * sx, pt[1] * sy)
        (ax, ay), (bx, by) = P(tl), P(tr)
        (cx, cy), (dx, dy) = P(br), P(bl)
        w = math.hypot(bx - ax, by - ay)
        h = math.hypot(dx - ax, dy - ay)
        if w < 0.5 or h < 0.5:
            continue
        t = b[4]
        fs = max(h * 0.85, 3.0)
        base = font.text_length(t, fontsize=fs) or 1.0
        k = min(max(w / base, 0.5), 2.0)
        ux, uy = (bx - ax) / w, (by - ay) / w
        # 基线起点：左下角向内收 20% 字高
        startx = dx + (ax - dx) * 0.20
        starty = dy + (ay - dy) * 0.20
        cum = 0.0
        for ch in t:
            adv = font.text_length(ch, fontsize=fs)
            if ch.strip():
                items.append((startx + ux * cum * k, starty + uy * cum * k, ch, fs))
            cum += adv
    return items


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def boxes_angle_stats(boxes):
    angs = [b[6] for b in boxes if (b[2] - b[0]) >= 12 and (b[3] - b[1]) >= 4]
    if not angs:
        return 0.0
    return float(np.median(angs))


_CJK = re.compile(r'[\u4e00-\u9fff]')
_VALID = re.compile(r'[\u4e00-\u9fff0-9A-Za-z]')
# 这些字符在正规公文里几乎不出现，却是发票密码区/防伪底纹垃圾的主要成分
_BAD = set("*><|^~=\\`+$°")


def clean_boxes(boxes, min_score=0.50, max_bad=0.12):
    """剔除低置信度与"符号垃圾"。
    注意：不能按"有没有中文"来判断——项目代码、统一社会信用代码、
    发票号这类串本来就没有中文（如 2509-430103-04-01-699222-0001），
    必须保留。只按"垃圾符号占比"过滤。"""
    out = []
    for b in boxes:
        t = b[4].strip()
        s = b[5]
        if not t or s < min_score:
            continue
        n = len(t)
        valid = len(_VALID.findall(t)) / n
        if valid < 0.40:                            # 基本全是标点/符号
            continue
        bad = sum(1 for ch in t if ch in _BAD)
        if bad / n > max_bad:                       # 密码区那类乱码
            continue
        if len(_CJK.findall(t)) == 0 and bad > 0 and valid < 0.75:
            continue                                # 无中文 + 带怪符号 + 有效率低
        out.append(b)
    return out


def sort_boxes(boxes):
    """按"行"排序，保证文字层提取出来是自然阅读顺序"""
    if not boxes:
        return boxes
    hs = [b[3] - b[1] for b in boxes]
    tol = max(float(np.median(hs)) * 0.6, 4.0)
    ordered = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    lines, cur, cy = [], [], None
    for b in ordered:
        c = (b[1] + b[3]) / 2
        if cy is None or abs(c - cy) <= tol:
            cur.append(b)
            cy = float(np.mean([(x[1] + x[3]) / 2 for x in cur]))
        else:
            lines.append(cur)
            cur, cy = [b], c
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        out.extend(sorted(ln, key=lambda b: b[0]))
    return out


def detect_flip(rgb, boxes, ocr=None):
    """判断整页是否上下颠倒（180°）。
    用 OCR 自带的文本方向分类器逐行投票，按"字数×置信度"加权。
    返回 True 表示需要旋转 180°。"""
    if len(boxes) < 3:
        return False
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    crops, weights = [], []
    h, w = bgr.shape[:2]
    for b in boxes:
        x0, y0, x1, y1 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 - x0 < 10 or y1 - y0 < 8:
            continue
        sub = bgr[y0:y1, x0:x1]
        if sub.size == 0:
            continue
        crops.append(sub)
        weights.append(max(len(b[4]), 1) * max(float(b[5]), 0.1))
    if len(crops) < 3:
        return False
    eng = ocr or get_ocr()
    try:
        _, cls_res, _ = eng.text_cls(crops)
    except Exception:
        return False
    w180 = 0.0
    for (label, score), wt in zip(cls_res, weights):
        if "180" in str(label) and float(score) > 0.9:
            w180 += wt
    total = sum(weights)
    return total > 0 and (w180 / total) > 0.6


def native_spans(page):
    """按 span 汇总原生文字：[(x, y, text, size, bbox)]"""
    out = []
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                chars = [c for c in sp.get("chars", []) if c.get("c", "").strip()]
                if not chars:
                    continue
                text = "".join(c["c"] for c in chars)
                r = pymupdf.Rect(chars[0]["bbox"])
                for c in chars[1:]:
                    r |= pymupdf.Rect(c["bbox"])
                out.append((chars[0]["origin"][0], chars[0]["origin"][1], text,
                            float(sp.get("size", 10)), r))
    return out


def mask_spans(rgb, spans, W, H, max_ring=0.03, pad=4.0):
    """把"孤立在空白处"的原生文字（页码等）从位图抹白。
    判据：看文字框外围一圈是否干净，而不是框内墨量（框内本来就是字）。"""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    masked = []
    for x, y, text, size, r in spans:
        ix0 = int((r.x0 - 1.5) * w / W); ix1 = int((r.x1 + 1.5) * w / W)
        iy0 = int((r.y0 - 1.5) * h / H); iy1 = int((r.y1 + 1.5) * h / H)
        ox0 = int((r.x0 - pad) * w / W); ox1 = int((r.x1 + pad) * w / W)
        oy0 = int((r.y0 - pad) * h / H); oy1 = int((r.y1 + pad) * h / H)
        ix0, iy0 = max(0, ix0), max(0, iy0)
        ix1, iy1 = min(w, ix1), min(h, iy1)
        ox0, oy0 = max(0, ox0), max(0, oy0)
        ox1, oy1 = min(w, ox1), min(h, oy1)
        if ix1 <= ix0 or iy1 <= iy0 or ox1 <= ox0 or oy1 <= oy0:
            continue
        outer = g[oy0:oy1, ox0:ox1]
        ring = np.ones_like(outer, dtype=bool)
        ring[(iy0 - oy0):(iy1 - oy0), (ix0 - ox0):(ix1 - ox0)] = False
        if ring.sum() == 0:
            continue
        if float(((outer < 200) & ring).sum()) / float(ring.sum()) > max_ring:
            continue                       # 旁边还有内容，抹了会伤到图
        rgb[oy0:oy1, ox0:ox1] = 255
        masked.append((x, y, text, size))
    return rgb, masked


def draw_visible(page, spans):
    """把原生文字按原位重新画成可见文字（字体与原版不同，但位置字号一致）"""
    if not spans:
        return
    _, font = get_font()
    tw = pymupdf.TextWriter(page.rect)
    for x, y, text, size in spans:
        try:
            tw.append((x, y), text, font=font, fontsize=size)
        except Exception:
            pass
    try:
        tw.write_text(page, color=(0, 0, 0))
    except Exception:
        pass


def page_transform(page_wh, px_wh, crop, rot_deg):
    """把"原始页面坐标"映射到"裁边+纠偏+拉伸到整页"之后的页面坐标。
    必须与图像上做的 cv2 操作保持完全一致，否则文字层会错位。"""
    W, H = page_wh
    pw, ph = px_wh
    x0, y0, x1, y1 = crop if crop else (0, 0, pw, ph)
    cw, chh = max(x1 - x0, 1), max(y1 - y0, 1)
    th = math.radians(rot_deg)
    cos, sin = math.cos(th), math.sin(th)
    cx, cy = cw / 2.0, chh / 2.0
    sx, sy = W / cw, H / chh

    def f(x, y):
        px = x * pw / W - x0
        py = y * ph / H - y0
        dx, dy = px - cx, py - cy
        return (cos * dx + sin * dy + cx) * sx, (-sin * dx + cos * dy + cy) * sy
    return f


def span_rects(page):
    """页面上原生文字块的外接矩形（用于去重，避免 OCR 重复识别）"""
    rects = []
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                if sp.get("chars"):
                    r = pymupdf.Rect(sp["chars"][0]["bbox"])
                    for c in sp["chars"][1:]:
                        r |= pymupdf.Rect(c["bbox"])
                    rects.append(r)
    return rects


def _reencode(jpg, scale, quality):
    """从原始 JPEG 重新编码（不叠加压缩），按比例缩小像素"""
    arr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return jpg
    if scale < 0.995:
        h, w = arr.shape[:2]
        arr = cv2.resize(arr, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", arr, [int(cv2.IMWRITE_JPEG_QUALITY), int(round(quality))])
    return buf.tobytes() if ok else jpg


def fit_size(records, max_mb, log=print):
    """把整本体积压到 max_mb 以内：先降 JPEG 质量，不够再降分辨率。
    只动图像层，文字层坐标是页面坐标，不受影响。"""
    if not max_mb or max_mb <= 0 or not records:
        return records
    limit = int(max_mb * 1e6 * 0.97)
    total = sum(len(r["jpg"]) for r in records)
    if total <= limit:
        log(f"  体积 {total/1e6:.1f}MB ≤ 上限 {max_mb:g}MB，保持原分辨率")
        return records

    n = len(records)
    step = max(1, n // 5)
    sample = records[::step][:6]
    drop, scale = 0.0, 1.0
    for _ in range(14):
        est = 0.0
        for r in sample:
            nb = _reencode(r["src_jpg"], scale, max(60, r["q"] - drop))
            est += total * (len(nb) / max(len(r["src_jpg"]), 1)) / len(sample)
        if est <= limit:
            break
        if drop < 24:
            drop += 5
        elif scale > 0.60:
            scale *= 0.90
        else:
            break

    for r in records:
        r["jpg"] = _reencode(r["src_jpg"], scale, max(60, r["q"] - drop))
    got = sum(len(r["jpg"]) for r in records)

    # 抽样有偏差时再修正两轮
    rounds = 0
    while got > limit and rounds < 3:
        f = (limit / got) ** 0.5
        scale = max(0.55, scale * f)
        drop = min(30, drop + 3)
        for r in records:
            r["jpg"] = _reencode(r["src_jpg"], scale, max(58, r["q"] - drop))
        got = sum(len(r["jpg"]) for r in records)
        rounds += 1

    px = records[0]["px"]
    log(f"  体积控制：{total/1e6:.1f}MB → 上限 {max_mb:g}MB，"
        f"质量 -{int(drop)}，分辨率 ×{scale:.2f}"
        f"（约 {int(px[0]*scale)}×{int(px[1]*scale)}），实际 {got/1e6:.1f}MB")
    if got > limit:
        log(f"  !! 已压到极限仍超上限（{got/1e6:.1f}MB），建议拆分成多个文件")
    return records


def covered_ratio(box, rects):
    """一个 OCR 行框被原生文字框覆盖的面积占比（取最大的那一个）"""
    area = box.width * box.height
    if area <= 0:
        return 0.0
    best = 0.0
    for r in rects:
        inter = abs(box & r)
        if inter <= 0:
            continue
        v = inter / area
        if v > best:
            best = v
    return best


def sample_ink_ratio(rgb, boxes, sx, sy, limit=40, dark=200):
    """自检：抽若干 OCR 行，看框内是否真的有墨迹（防止文字层落在空白处）"""
    h, w = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    step = max(1, len(boxes) // limit)
    ok = tot = 0
    for b in boxes[::step]:
        x0, y0, x1, y1 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        tot += 1
        if float((g[y0:y1, x0:x1] < dark).mean()) > 0.01:
            ok += 1
    return (ok / tot) if tot else 1.0


def scrub_traces(path):
    """抹掉 PDF 写入引擎留下的痕迹。全部等长替换，不改变字节偏移，
    因此交叉引用表不受影响。
      1) 文件头的 "% Written by MuPDF x.y.z" 注释
      2) /ID 的第二个标识改成与第一个相同（看起来像一次保存产生）"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        orig = data

        i = data.find(b"% Written by ")
        if 0 <= i < 2048:
            j = data.find(b"\n", i)
            if j > i:
                n = j - i
                data = data[:i] + b"%" + b" " * (n - 1) + data[j:]

        m = re.search(rb"/ID\s*\[\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\]", data)
        if m:
            a, b = m.group(1), m.group(2)
            rep = b"/ID[<" + a + b"><" + a + b">]"
            if len(rep) == m.end() - m.start():
                data = data[:m.start()] + rep + data[m.end():]

        # 引擎会在 Catalog 里塞一个内联 /Info<</Producer(MuPDF x.y.z)>>，
        # 与 trailer 里的正式 Info 并存；这里把括号内容清空
        data = re.sub(rb"\(MuPDF[^)]*\)",
                      lambda mm: b"(" + b" " * (len(mm.group(0)) - 2) + b")", data)

        if data != orig:
            with open(path, "wb") as fh:
                fh.write(data)
    except Exception:
        pass


def convert(src, dst, dpi_text=200, dpi_img=160, q_text=88, q_img=82,
            log=print, pages=None, max_skew=0.5, use_cache=True, bookmarks=True,
            cache_dir=None, max_mb=0.0, native_mode="reuse", image_ocr=True,
            threads=0, gpu=False, on_page=None, should_stop=None):
    """native_mode="reuse" 时，纯文字页直接复用原字形坐标、不做 OCR；
    「有文字层 + 有插图」的页：image_ocr=True 时只对插图区域裁图 OCR、
    原生文字层完整复用，image_ocr=False 时只取该页原生文字；
    整页扫描件不受此开关影响，永远照常整页 OCR。
    threads>0 限制 OCR 线程数（让前台不卡）；gpu=True 且环境支持时用 CUDA。"""
    import hashlib, time
    srcdoc = pymupdf.open(src)
    idxs = range(srcdoc.page_count) if pages is None else pages

    cdir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(dst)), "_cache")
    if use_cache:
        os.makedirs(cdir, exist_ok=True)

    stats = []
    records = []
    for i in idxs:
        if should_stop is not None and should_stop():
            raise Cancelled()
        p = srcdoc[i]
        W, H = p.rect.width, p.rect.height

        # 先把这一页渲染出来，用"渲染后的像素"做指纹：
        # 内容只要变一个像素，指纹就变，绝不会误用旧缓存；
        # 反过来，另存一次但页面没变，仍然能命中。
        ntxt = p.get_text("text").strip()
        cimgs = content_images(p)
        dpi = dpi_text if not cimgs else suggest_dpi(p)
        pix = p.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()

        # 这一页要不要跑 OCR：
        #   · 纯文字页（无嵌入图像、本来就有文字层）→ native_mode="reuse" 时直接复用原字形
        #   · 有文字层 + 有插图的页 → image_ocr=False 时不做 OCR（只保留原生文字层）
        #   · 整页扫描件不受 image_ocr 影响，永远照常 OCR；
        #     判定用「像样的文字层」（≥10 字），扫描件页角的页码等零星文字不算
        has_text = len(ntxt) >= 10
        skip_ocr = (native_mode != "ocr" and not cimgs and bool(ntxt)) \
                   or (bool(cimgs) and has_text and not image_ocr)

        if use_cache:
            # 指纹 = 渲染像素 + 算法版本 + JPEG 质量（质量影响缓存里的压缩图，必须参与）
            q_page = q_img if cimgs else q_text
            ph = hashlib.md5(pix.samples + f"{CACHE_VER}|q{q_page}".encode()).hexdigest()[:20]
            cj = os.path.join(cdir, f"{ph}.jpg")
            cm = os.path.join(cdir, f"{ph}.json")
            hit = (not skip_ocr) and os.path.exists(cj) and os.path.exists(cm)
        else:
            cj = cm = None
            hit = False

        # 这两组变量在"命中缓存"和"重新计算"两条路径上都要有值
        redraw = []
        vlines, vang = [], 0

        if hit:
            with open(cj, "rb") as fh:
                img_bytes = fh.read()
            with open(cm, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            items = [tuple(x) for x in meta["items"]]
            vlines = [tuple(x) for x in meta.get("vlines", [])]
            vang = meta.get("vang", 0)
            redraw = [tuple(x) for x in meta.get("redraw", [])]
            kind, dpi, info = meta["kind"], meta["dpi"], meta["info"]
            cw, ch = meta["px"]
        else:
            info = {"border": None, "skew": 0.0, "rot": 0.0, "flip": 0, "passes": 1,
                    "native_chars": 0, "covered": 0}
            # 每一页都走同一条路：原生文字照收，OCR 只补原生文字没覆盖的区域
            ntv = native_items(p)
            info["native_chars"] = len(ntv)
            base_rects = span_rects(p)
            rgb, crop = crop_border(rgb)
            info["border"] = crop
            # 文字页+插图（复用模式下）：只对插图区域裁图 OCR，
            # 原生文字层完整复用；翻转/纠偏不适用（版式页不会倒置），直接跳过
            mixed = bool(cimgs) and has_text and native_mode != "ocr"
            if skip_ocr:
                # 不跑 OCR：这一页的文字层完全来自原文件的字形坐标
                boxes = []
                info["skip_ocr"] = 1
            elif mixed:
                boxes = []
                cx0, cy0 = (crop[0], crop[1]) if crop else (0, 0)
                ph_img, pw_img = rgb.shape[:2]
                pad = max(int(pix.width / W * 4), 4)     # 约 4pt 的像素，防贴边漏字
                for r in cimgs:
                    # 插图的 PDF 点坐标 → 裁边后的渲染像素坐标
                    ix0 = max(int(r.x0 * pix.width / W) - cx0 - pad, 0)
                    iy0 = max(int(r.y0 * pix.height / H) - cy0 - pad, 0)
                    ix1 = min(int(math.ceil(r.x1 * pix.width / W)) - cx0 + pad, pw_img)
                    iy1 = min(int(math.ceil(r.y1 * pix.height / H)) - cy0 + pad, ph_img)
                    if ix1 - ix0 < 8 or iy1 - iy0 < 8:
                        continue
                    for b in ocr_boxes(rgb[iy0:iy1, ix0:ix1], threads, gpu):
                        b[0] += ix0; b[2] += ix0
                        b[1] += iy0; b[3] += iy0
                        if len(b) > 7:                    # 四边形顶点一并平移
                            b[7] = [(qx + ix0, qy + iy0) for qx, qy in b[7]]
                        boxes.append(b)
                info["region_ocr"] = len(cimgs)
            else:
                boxes = ocr_boxes(rgb, threads, gpu)

            # ① 整页上下颠倒 → 先转正，再重识别
            if not mixed and detect_flip(rgb, boxes):
                # 页码等原生文字不能跟着翻转：先从位图抹掉，转正后按原位重画
                if ntv:
                    rgb, redraw = mask_spans(rgb, native_spans(p), W, H)
                    if redraw:
                        ntv = []          # 已可见重绘，不再进不可见层
                rgb = cv2.rotate(rgb, cv2.ROTATE_180)
                boxes = ocr_boxes(rgb, threads, gpu)
                info["flip"] = 180
                info["passes"] += 1
                crop = None          # 已转正，裁切偏移作废

            # ② 倾斜校正（转正之后的角度才是真实倾斜）
            ang = boxes_angle_stats(boxes)
            info["skew"] = round(ang, 2)
            if not mixed and abs(ang) >= max_skew:
                rgb = rotate(rgb, -ang)
                boxes = ocr_boxes(rgb, threads, gpu)
                info["rot"] = round(-ang, 2)
                info["passes"] += 1
            raw_n = len(boxes)
            boxes = clean_boxes(boxes)
            info["dropped"] = raw_n - len(boxes)

            ch0, cw0 = rgb.shape[:2]
            sx, sy = W / cw0, H / ch0
            tf = page_transform((W, H), (pix.width, pix.height), crop, -info["rot"])

            # 原生文字已经覆盖的区域（按同样的几何变换映射到当前页坐标）
            native_zone = []
            for r in base_rects:
                a, b = tf(r.x0, r.y0), tf(r.x1, r.y1)
                native_zone.append(pymupdf.Rect(min(a[0], b[0]) - 1.5, min(a[1], b[1]) - 1.5,
                                                max(a[0], b[0]) + 1.5, max(a[1], b[1]) + 1.5))

            # 只保留"原生文字没有覆盖"的 OCR 行（按重叠面积判定，不看中心点）
            kept, covered = [], 0
            for b in boxes:
                br = pymupdf.Rect(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy)
                if native_zone and covered_ratio(br, native_zone) >= 0.5:
                    covered += 1
                    continue
                kept.append(b)
            info["covered"] = covered

            vert = sort_boxes([b for b in kept if is_vertical(b)])
            norm = sort_boxes([b for b in kept if not is_vertical(b)])
            items = ocr_items(norm, sx, sy)
            if vert:
                bottom_up = vertical_direction(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), vert)
                vlines, vang = vertical_items(vert, sx, sy, bottom_up)
                info["vertical"] = len(vert)

            ntv_new = [(tf(x, y)[0], tf(x, y)[1], c, fs) for x, y, c, fs in ntv]
            items = ntv_new + items
            if skip_ocr:
                kind = "native"
            else:
                kind = f"text+ocr({len(kept)})" if ntv_new else f"ocr({len(kept)})"

            # —— 自检（I4/I5）：抽样看补进来的文字是否真的压在墨迹上
            if len(kept) >= 3:
                info["ink"] = round(sample_ink_ratio(rgb, kept, sx, sy), 3)

            q = q_img if cimgs else q_text
            ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                                   [int(cv2.IMWRITE_JPEG_QUALITY), int(q)])
            img_bytes = buf.tobytes()
            ch, cw = rgb.shape[:2]

            if use_cache and not skip_ocr:
                with open(cj, "wb") as fh:
                    fh.write(img_bytes)
                with open(cm, "w", encoding="utf-8") as fh:
                    json.dump({"kind": kind, "dpi": dpi, "info": info, "px": [cw, ch],
                               "vlines": [list(x) for x in vlines], "vang": vang,
                               "redraw": [list(x) for x in redraw],
                               "items": [list(x) for x in items]}, fh, ensure_ascii=False)

        if should_stop is not None and should_stop():
            raise Cancelled()
        records.append({"W": W, "H": H, "jpg": img_bytes, "src_jpg": img_bytes,
                        "q": int(q_text if kind == "native" else q_img),
                        "items": items, "redraw": redraw, "info": info,
                        "vlines": vlines, "vang": vang,
                        "kind": kind, "dpi": dpi, "px": [cw, ch], "page": i + 1})
        stats.append({"page": i + 1, "kind": kind, "dpi": dpi, "px": [cw, ch],
                      "img_bytes": len(img_bytes), "chars": len(items), **info})
        log(f"  p{i+1:>2} {kind:<10} dpi={dpi} px={cw}x{ch} "
            f"img={len(img_bytes)/1024:6.1f}KB chars={len(items):5d} "
            f"skew={info['skew']:>5} rot={info['rot']:>5} "
            f"{'FLIP ' + str(info.get('flip', 0)) if info.get('flip') else ''}"
            f" pass={info['passes']} drop={info.get('dropped', 0):>3}"
            f"{'  [skip-ocr]' if skip_ocr else ''}"
            f"{'  [cache]' if hit else ''}")
        if on_page is not None:
            try:
                on_page(i + 1, len(srcdoc), stats[-1])
            except Exception:
                pass

    records = fit_size(records, max_mb, log)

    toc = []
    if bookmarks:
        try:
            toc = srcdoc.get_toc() or []          # 源文件已有大纲就原样沿用
            if toc:
                log(f"  沿用原书签 {len(toc)} 条")
            else:
                from bookmarks import build as _build_toc
                toc = _build_toc(srcdoc)          # 否则从"目录"页解析
        except Exception as e:
            log(f"  !! 书签处理失败: {e}")

    tmp = dst + ".part"

    def _write():
        doc = pymupdf.open()
        for r in records:
            pg = doc.new_page(width=r["W"], height=r["H"])
            pg.insert_image(pymupdf.Rect(0, 0, r["W"], r["H"]),
                            stream=r["jpg"], keep_proportion=False)
            draw_visible(pg, r["redraw"])
            write_invisible(pg, r["items"])
            write_vertical(pg, r.get("vlines"), r.get("vang", 0))
        # 元数据沿用源文件，避免留下"由某脚本生成"的痕迹
        sm = {k: v for k, v in (srcdoc.metadata or {}).items() if v}
        md = {k: sm[k] for k in ("author", "title", "subject", "keywords",
                                 "creator", "producer", "creationDate", "modDate")
              if sm.get(k)}
        try:
            doc.set_metadata(md if md else {"producer": "", "creator": ""})
        except Exception:
            pass
        try:
            xmp = srcdoc.get_xml_metadata()
            if xmp:
                doc.set_xml_metadata(xmp)
        except Exception:
            pass
        if toc:
            doc.set_toc(toc)
        try:
            doc.subset_fonts()          # 只嵌入用到的字形，中文全字库 1.6MB → 几十 KB
        except Exception:
            pass
        doc.save(tmp, deflate=True, garbage=4, clean=True)
        doc.close()
        scrub_traces(tmp)
        return os.path.getsize(tmp)

    size = _write()
    if toc:
        log(f"  书签 {len(toc)} 条")

    # 源文件没有大纲、也没有可解析的目录文字（目录页是扫描图）时，
    # 从输出成品里把目录页重新高清识别，再按标题定位
    if bookmarks and not toc:
        try:
            from bookmarks import build_from_scan
            _d = pymupdf.open(tmp)
            t2 = build_from_scan(_d)
            _d.close()
            if t2:
                _tmp2 = tmp + ".toc"
                _d = pymupdf.open(tmp)
                try:
                    _d.set_toc(t2)
                    _d.save(_tmp2, garbage=4, deflate=True)
                finally:
                    _d.close()      # 失败也必须关，否则句柄泄漏导致成品无法落盘
                if os.path.exists(_tmp2):
                    os.replace(_tmp2, tmp)
                    size = os.path.getsize(tmp)
                    log(f"  由扫描目录页生成书签 {len(t2)} 条")
        except Exception as e:
            log(f"  !! 扫描目录识别失败: {e}")

    # 按“最终文件大小”闭环：图像预算漏算了字体等固定开销时再收紧
    for _ in range(3):
        if not max_mb or max_mb <= 0 or size <= max_mb * 1e6:
            break
        img = sum(len(r["jpg"]) for r in records)
        overhead = max(size - img, 0)
        budget_mb = max(max_mb * 1e6 - overhead, 0.15e6) / 1e6
        log(f"  实际 {size/1e6:.1f}MB 仍超上限（非图像开销 {overhead/1024:.0f}KB），"
            f"按 {budget_mb:.2f}MB 再收紧")
        before = img
        records = fit_size(records, budget_mb, log)
        size = _write()
        if sum(len(r["jpg"]) for r in records) >= before - 1024:
            break                     # 已经压到极限，再迭代也没用

    log(f"  最终文件 {size/1e6:.1f}MB")
    srcdoc.close()
    scrub_traces(tmp)          # 兜底再抹一次（书签/压缩可能重新写过文件）

    final = dst
    for attempt in range(6):
        try:
            os.replace(tmp, final)
            break
        except PermissionError:
            if attempt == 5:
                final = os.path.splitext(dst)[0] + time.strftime("-%H%M%S") + ".pdf"
                os.replace(tmp, final)
                log(f"!! 目标文件被占用，已改存为: {final}")
            else:
                time.sleep(2)
    convert.last_path = final
    return stats


def _median_angle(boxes):
    angs = []
    for x0, y0, x1, y1, t, s, ang in boxes:
        if (x1 - x0) < 12 or (y1 - y0) < 4:
            continue
        angs.append(ang)
    if not angs:
        return 0.0, angs
    return float(np.median(angs)), angs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--dpi-text", type=int, default=200)
    ap.add_argument("--dpi-img", type=int, default=160)
    ap.add_argument("--q-text", type=int, default=88)
    ap.add_argument("--q-img", type=int, default=82)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--last", type=int, default=0)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-bookmarks", action="store_true")
    ap.add_argument("--max-mb", type=float, default=0.0,
                    help="体积上限（MB），0=不限制（默认）")
    a = ap.parse_args()
    pages = None
    if a.first or a.last:
        pages = list(range(a.first - 1, a.last))
    st = convert(a.src, a.dst, dpi_text=a.dpi_text, dpi_img=a.dpi_img,
                 q_text=a.q_text, q_img=a.q_img, pages=pages,
                 use_cache=not a.no_cache, bookmarks=not a.no_bookmarks,
                 max_mb=a.max_mb)
    lp = getattr(convert, "last_path", a.dst)
    print(json.dumps({"pages": len(st), "file": lp, "bytes": os.path.getsize(lp)}, ensure_ascii=False))
