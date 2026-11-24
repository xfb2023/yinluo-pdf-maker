# -*- coding: utf-8 -*-
"""bookmarks.py —— 从正文"目录"页解析出章节并生成 PDF 书签（大纲）。

用法：
    python bookmarks.py <源.pdf> [输出.pdf]
不指定输出时写回新文件 "<源>-带书签.pdf"。
"""
import sys, os, re
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

# 目录行：标题 + 前导点 + 页码
LINE_RE = re.compile(r"^(?P<title>.+?)[\s\.·…⋯]*?(?P<page>\d{1,4})\s*$")


def find_toc_page(doc, max_scan=12):
    """找"目录"页：标题含"目录"，且行内多含点线引导符"""
    for i in range(min(max_scan, doc.page_count)):
        txt = doc[i].get_text("text")
        if "目录" not in txt:
            continue
        if txt.count("…") + txt.count(".") >= 10:
            return i
    return None


def parse_toc(doc, idx):
    """返回 [(level, title, page)]，层级按左缩进自动判定"""
    page = doc[idx]
    rows = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            txt = "".join(s["text"] for s in ln.get("spans", [])).strip()
            if not txt or "目录" in txt:
                continue
            m = LINE_RE.match(txt)
            if not m:
                continue
            title = m.group("title").strip(" .·…⋯\t")
            # 去掉标题里残留的引导点
            title = re.sub(r"[\.·…⋯]{3,}.*$", "", title).strip()
            pg = int(m.group("page"))
            if not title or not (1 <= pg <= doc.page_count):
                continue
            rows.append((ln["bbox"][0], title, pg))

    if not rows:
        return []

    # 按缩进聚类出层级
    xs = sorted({round(r[0], 1) for r in rows})
    levels = {}
    for x in xs:
        levels[x] = min(len(levels) + 1, 3)
    return [(levels[round(x, 1)], t, p) for x, t, p in rows]


def build(doc):
    idx = find_toc_page(doc)
    if idx is None:
        return []
    return parse_toc(doc, idx)


# ---------------------------------------------------------------------------
# 纯扫描件的兜底：目录页本身是图片，源文件里没有文字可解析。
# 做法是把开头几页按 300dpi 重新识别，配对"标题 + 页码列"，
# 再用标题在正文文字层里定位，得到准确页码。
# ---------------------------------------------------------------------------
_CJK = re.compile(r'[\u4e00-\u9fff0-9A-Za-z]')


def _norm(s):
    return "".join(_CJK.findall(s or ""))


def _level_of(t):
    t = t.strip()
    if re.match(r'^（[一二三四五六七八九十]+）', t):
        return 1
    if re.match(r'^（\d+）', t):
        return 3
    if re.match(r'^\d+\.\d+', t):
        return 3
    if re.match(r'^\d+\.(?![0-9])', t):
        return 2
    return 0


def _clean(t):
    t = re.sub(r'[.．·…⋯\s]+$', '', t.strip())
    t = re.sub(r'[.．·…⋯]{2,}', '', t)
    return re.sub(r'[,，、;；:：]+$', '', t.strip()).strip()


def _family(t):
    if re.match(r'^（\d+）', t):
        return "pd"
    if re.match(r'^（[一二三四五六七八九十]+）', t):
        return "pc"
    if re.match(r'^\d+\.\d+', t):
        return "mm"
    if re.match(r'^\d+\.', t):
        return "m"
    return ""


def _parse_toc_page(page, ocr, dpi=300):
    import numpy as np
    import cv2
    import dl
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()
    boxes = dl.ocr_boxes(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    boxes.sort(key=lambda b: (b[1] + b[3]) / 2)
    cut = pix.width * 0.72          # 右侧为页码列
    rows, cur = [], []
    for b in boxes:
        cy = (b[1] + b[3]) / 2
        if not cur or abs(cy - (cur[-1][1] + cur[-1][3]) / 2) < dpi * 0.18:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    if cur:
        rows.append(cur)

    out = []
    for row in rows:
        titles = [b for b in row if b[0] < cut]
        nums = [b for b in row if b[0] >= cut]
        t = "".join(b[4] for b in sorted(titles, key=lambda b: b[0])).strip()
        if not t:
            continue
        lv = _level_of(t)
        if lv == 0:
            continue
        out.append({"level": lv, "title": _clean(t)})
    return out


def build_from_scan(doc, max_pages=4, ocr=None):
    """目录页是扫描图时，从图片里还原大纲"""
    import dl
    if ocr is None:
        ocr = dl.get_ocr()
    texts = [_norm(p.get_text("text")) for p in doc]
    entries = []
    for i in range(min(max_pages, doc.page_count)):
        try:
            part = _parse_toc_page(doc[i], ocr)
        except Exception:
            part = []
        if len(part) >= 4:          # 像目录页才收
            entries.extend(part)
    if len(entries) < 4:
        return []

    toc, used = [], 0
    for e in entries:
        key = _norm(e["title"])[:12]
        if len(key) < 3:
            continue
        found = None
        for cand in (key, _norm(e["title"])[:8], _norm(e["title"])[:5]):
            if len(cand) < 3:
                continue
            for j in range(used, len(texts)):
                if cand in texts[j]:
                    found = j + 1
                    break
            if found:
                break
        if found:
            toc.append([e["level"], e["title"], found])

    prev = 0                    # 首条层级必须压到 1，否则 set_toc 会拒绝整个大纲
    for i, row in enumerate(toc):
        lv = row[0]
        if i > 0 and _family(row[1]) and _family(row[1]) == _family(toc[i - 1][1]):
            lv = min(lv, toc[i - 1][0])
        if lv > prev + 1:
            lv = prev + 1
        row[0] = lv
        prev = lv
    return toc if len(toc) >= 4 else []


def apply_toc(src, dst=None):
    doc = pymupdf.open(src)
    toc = build(doc)
    if not toc:
        print("未找到目录页，跳过书签")
        doc.close()
        return None
    out = dst or (os.path.splitext(src)[0] + "-带书签.pdf")
    doc.set_toc(toc)
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    return out, toc


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    r = apply_toc(src, dst)
    if r:
        out, toc = r
        for lvl, title, page in toc:
            print(f"{'  ' * (lvl - 1)}{title}  ....  {page}")
        print("已写入:", out)
