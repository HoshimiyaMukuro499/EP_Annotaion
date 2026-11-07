# -*- coding: utf-8 -*-
"""
WB / 凝胶图像交互标注工具

功能：
  1. 启动时在脚本所在文件夹中选择任意图片（也可用 --src 指定）；
     默认直接使用原图；需要时可加 --rectify 自动提取凝胶区域（透视校正），
     加 --flip 水平左右翻转；
  2. 从左到右点击泳道中心，自动编号；任意泳道都可以按 m 设为 / 取消 Marker；
  3. 点击条带上、下边缘，计算条带中心到加样参考线的距离与条带厚度；
     Marker 泳道可连续测量任意多条带，按 Enter / n 结束本泳道；
  4. 按 k 可为 Marker 泳道输入各条带的相对分子质量（kDa），
     在图片最左/最右侧自动生成 kDa 标尺（仅用于靠近边缘的 Marker 泳道）；
  5. 按 t 标注指示剂前沿（dye front）：在整幅图上画一条线，
     并显示它到加样参考线的距离；
  6. 按 c 框选裁剪，之后只显示裁剪范围内的图像；
  7. 输出标注图 PNG + 长表 CSV（一条带一行，Marker 多条带不会互相覆盖）。

用法：
    python wb_mark_interactive.py                  # 弹窗选择文件夹里的图片
    python wb_mark_interactive.py --src 图.tif      # 直接指定图片
    python wb_mark_interactive.py --rectify        # 自动提取凝胶区域（透视校正）
    python wb_mark_interactive.py --rectify --flip # 提取后再水平翻转
    python wb_mark_interactive.py --manual-corners # 手动点四角（隐含 --rectify）
    python wb_mark_interactive.py --demo           # 无交互，用预设示例看输出效果

    # 给已有测量结果补加 kDa 标尺（不用重新点泳道/条带）：
    python wb_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv \
        --marker-kda "180,130,100,70,55,40,35"

    # 打开已有结果继续手动补充（例如按 t 补指示剂前沿）：
    python wb_mark_interactive.py --from-csv 4-8_Merge_lane_measurements.csv --edit

交互按键：
    左键单击   参考线步骤：设定加样参考线；
               泳道步骤：添加泳道中心；
               条带步骤：点当前泳道条带的上/下边缘；点其他泳道可切换泳道
    Enter / n  参考线步骤：用图像上边缘 y=0；
               泳道步骤：结束添加，进入条带测量；
               条带步骤：完成当前泳道，进入下一条（最后一条不会自动保存）
    m          把当前（或最后添加的）泳道设为 / 取消 Marker
    k          为当前 Marker 泳道输入各条带的相对分子质量（kDa）
    s          跳过当前泳道（无可见条带）
    b          上一条泳道
    z          撤销当前泳道最后添加的一条带
    d          清空当前泳道的所有条带
    f          重新设定加样参考线（已有测量结果会自动重算距离）
    t          标注指示剂前沿（dye front），点击其所在水平位置
    c          框选裁剪：拖出矩形后 Enter，只显示框选范围内的图像
    q          保存并退出
    h / ?      显示 / 隐藏按键说明
    Esc        关闭说明 / 取消未完成的上边缘 / 退出重设参考线
    滚轮        以鼠标位置为中心缩放；方向键平移；r 复位视图

输出（保存在脚本所在文件夹，前缀默认取图片文件名）：
    <前缀>_gel.png                  实际用于标注的图（未翻转；供 --from-csv 还原）
    <前缀>_gel_flipped.png          实际用于标注的图（已翻转）
    <前缀>_lane_annotated.png       最终标注图
    <前缀>_lane_measurements.csv    测量长表：每条带一行

CSV 列：
    lane_index, label, is_marker, band_index, band_count,
    x_center_px, x_left_px, x_right_px,
    y_top_px, y_bottom_px, y_center_px,
    thickness_px, thickness_value,
    distance_px, distance_value, marker_kda,
    dye_front_px, dye_front_value,
    img_x0_px, img_y0_px, img_w_px, img_h_px, unit, note
    （img_* 记录应用内裁剪区域，--from-csv/--edit 时据此精确复位）

    同一泳道有多条带时，band_index 按从上到下的顺序编号；
    thickness_value / distance_value 的单位由 unit 列给出（通常为 mm）；
    marker_kda 为该条带对应的分子量（kDa），仅 Marker 泳道填写。
"""

import argparse
import csv
import os
import sys
import textwrap
import time

import cv2
import numpy as np

import matplotlib

# --demo 不需要 GUI；其它情况用当前默认 GUI 后端（Windows 下通常是 QtAgg）
if "--demo" in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS", "DejaVu Sans"
]
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.abspath(__file__))
IMAGE_EXTS = (".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ----------------------------------------------------------------------------
# 读图 / 选图
# ----------------------------------------------------------------------------
def list_images(folder):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [n for n in names if n.lower().endswith(IMAGE_EXTS)]


def choose_image():
    """弹出文件选择框，默认定位到脚本所在文件夹。返回路径或 None。"""
    images = list_images(BASE)
    if images:
        print("脚本文件夹中的图片：")
        for n in images:
            print("  " + n)
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        print("无法打开文件选择框（%s）。请用 --src 指定图片。" % exc)
        return None

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    root.update()
    path = filedialog.askopenfilename(
        parent=root,
        title="选择要标注的图片",
        initialdir=BASE,
        filetypes=[
            ("图像文件", "*.tif *.tiff *.png *.jpg *.jpeg *.bmp"),
            ("TIFF", "*.tif *.tiff"),
            ("PNG / JPG", "*.png *.jpg *.jpeg"),
            ("所有文件", "*.*"),
        ],
    )
    root.destroy()
    return path or None


def read_image(path):
    # 用 imdecode + fromfile，避免 Windows 下中文路径导致 cv2.imread 失败
    try:
        data = np.fromfile(path, dtype=np.uint8)
        raw = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        raw = None
    if raw is None:
        sys.exit("无法读取图像: %s" % path)
    if raw.dtype != np.uint8:
        raw = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if raw.ndim == 2:
        gray = raw
        color = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    else:
        color = raw[:, :, :3].copy()
        gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    return gray, color


# ----------------------------------------------------------------------------
# 找凝胶四角 / 透视校正 / 翻转
# ----------------------------------------------------------------------------
def _runs(idx, minlen):
    """把一维索引数组切成连续段，保留长度 >= minlen 的段。"""
    if len(idx) == 0:
        return []
    out = []
    s = p = idx[0]
    for v in idx[1:]:
        if v == p + 1:
            p = v
        else:
            if p - s + 1 >= minlen:
                out.append((s, p))
            s = p = v
    if p - s + 1 >= minlen:
        out.append((s, p))
    return out


def _fallback_corners(H, W):
    """这张图的经验四角（仅在自动检测失败时使用）。"""
    return np.float32([
        [0.222 * W, 0.381 * H],
        [0.750 * W, 0.394 * H],
        [0.746 * W, 0.790 * H],
        [0.200 * W, 0.785 * H],
    ])


def detect_corners(gray):
    """用亮区边缘拟合四条边，求交点；返回 (4x2 float32, 是否自动检测成功)。"""
    H, W = gray.shape
    bw = gray > 150

    xs = np.arange(int(0.25 * W), int(0.75 * W))
    top, bot = [], []
    for x in xs:
        rr = _runs(np.where(bw[:, x])[0], 30)
        if not rr:
            continue
        top.append((x, rr[0][0]))
        bot.append((x, rr[-1][1]))

    ys = np.arange(int(0.45 * H), int(0.75 * H))
    left, right = [], []
    for y in ys:
        rr = _runs(np.where(bw[y, :])[0], 30)
        if not rr:
            continue
        left.append((y, rr[0][0]))
        right.append((y, rr[-1][1]))

    if min(len(top), len(bot), len(left), len(right)) < 10:
        return _fallback_corners(H, W), False

    mt, bt = np.polyfit(np.array(top)[:, 0], np.array(top)[:, 1], 1)
    mb, bb = np.polyfit(np.array(bot)[:, 0], np.array(bot)[:, 1], 1)
    ml, bl = np.polyfit(np.array(left)[:, 0], np.array(left)[:, 1], 1)
    mr, br = np.polyfit(np.array(right)[:, 0], np.array(right)[:, 1], 1)

    def inter(m1, b1, m2, b2):
        # y = m1 x + b1 ; x = m2 y + b2
        x = (m2 * b1 + b2) / (1.0 - m2 * m1)
        y = m1 * x + b1
        return (x, y)

    TL = inter(mt, bt, ml, bl)
    TR = inter(mt, bt, mr, br)
    BR = inter(mb, bb, mr, br)
    BL = inter(mb, bb, ml, bl)
    pts = np.float32([TL, TR, BR, BL])

    ok = (TL[0] < TR[0] and BL[0] < BR[0] and
          TL[1] < BL[1] and TR[1] < BR[1])
    if (not ok) or cv2.contourArea(pts) < 0.08 * W * H:
        return _fallback_corners(H, W), False
    return pts, True


def pick_corners(gray):
    """手动点四角：左上 -> 右上 -> 右下 -> 左下。"""
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(gray, cmap="gray")
    ax.set_title("依次点击凝胶四角：左上 → 右上 → 右下 → 左下", fontsize=11)
    ax.set_axis_off()
    fig.canvas.draw()
    pts = plt.ginput(4, timeout=0, show_clicks=True)
    plt.close(fig)
    if len(pts) != 4:
        sys.exit("需要点击 4 个角。")
    return np.float32(pts)


def clean_edges(im, width=2, thresh=200):
    """去掉最外圈的黑色细边。"""
    out = im.copy()
    for sl in [np.s_[0:width, :], np.s_[-width:, :],
               np.s_[:, 0:width], np.s_[:, -width:]]:
        reg = out[sl]
        mask = reg < thresh
        if mask.any():
            reg[mask] = 245
    return out


def clean_corners(im):
    """把四角的黑色/阴影填成白底（左上角靠近 Marker 条带，范围小一些）。"""
    out = im.copy()
    H, W = im.shape[:2]
    specs = [
        (0, 50, 0, 50, 170),          # 左上
        (0, 75, W - 75, W, 180),      # 右上
        (H - 60, H, 0, 60, 180),      # 左下
        (H - 60, H, W - 60, W, 180),  # 右下
    ]
    for y0, y1, x0, x1, thresh in specs:
        reg = out[y0:y1, x0:x1]
        mask = reg < thresh
        if mask.any():
            reg[mask] = 245
    return out


def clean_border(im, thresh=150):
    """从四角泛洪，把与边框相连的暗色背景填白；不碰内部条带。"""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
    dark = (g < thresh).astype(np.uint8)
    h, w = dark.shape
    ff = dark.copy()
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if ff[sy, sx]:
            mask = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(ff, mask, (sx, sy), 2)
    out = im.copy()
    out[ff == 2] = 245
    return out


def rectify(gray, color, src, out_w=1200, flip=True):
    """透视校正成矩形并（默认）水平翻转。返回 (gray, color, H, 原始平均高度px)。"""
    TL, TR, BR, BL = src
    wt = np.linalg.norm(TR - TL)
    wb = np.linalg.norm(BR - BL)
    hl = np.linalg.norm(BL - TL)
    hr = np.linalg.norm(BR - TR)
    H = int(round(out_w * (hl + hr) / (wt + wb)))
    H = max(300, min(H, 2000))

    dst = np.float32([[0, 0], [out_w, 0], [out_w, H], [0, H]])
    M = cv2.getPerspectiveTransform(src, dst)

    g = cv2.warpPerspective(gray, M, (out_w, H),
                            flags=cv2.INTER_CUBIC, borderValue=255)
    c = cv2.warpPerspective(color, M, (out_w, H),
                            flags=cv2.INTER_CUBIC,
                            borderValue=(255, 255, 255))
    if flip:
        g = cv2.flip(g, 1)
        c = cv2.flip(c, 1)
    g = clean_edges(g, 6, 210)
    c = clean_edges(c, 6, 210)
    g = clean_corners(g)
    c = clean_corners(c)
    g = clean_border(g, 150)
    c = clean_border(c, 150)
    return g, c, H, (hl + hr) / 2.0


def compute_mm_per_px(avg_h_orig, out_h, orig_h, capture_h_mm=120.0):
    """按仪器元数据“拍摄面积 12x15 cm”估算纵向 mm/px。"""
    mm_per_px_orig = capture_h_mm / float(orig_h)
    return avg_h_orig * mm_per_px_orig / float(out_h)


# ----------------------------------------------------------------------------
# 数据模型
# ----------------------------------------------------------------------------
class GelModel:
    """泳道、Marker 标记与条带测量结果。

    bands: lane_index -> [band, ...]（按添加顺序；绘制/导出时按 y 从上到下排序）
    band:  top/bottom/center（px）, thick_px/val, dist_px/val
    """

    def __init__(self, width, scale, unit):
        self.W = float(width)
        self.scale = float(scale)   # 每个像素对应的物理量（mm 或 px）
        self.unit = unit            # "mm" 或 "px"
        self.ref_y = 0.0
        self.dye_front = None       # 指示剂前沿（dye front）的 y 像素坐标
        # 应用内裁剪的矩形 (x0, y0, x1, y1)，相对保存的凝胶图
        # （<前缀>_gel_flipped.png 或 <前缀>_gel.png）；None 表示整图
        self.crop_rect = None
        self.lanes = []             # [{'x': float, 'marker': bool}, ...]
        self.bands = {}             # lane_index -> [band, ...]
        self.skipped = set()        # 明确标记为“无条带”的泳道
        self.marker_kda = {}        # lane_index -> [kDa, ...]，与条带从上到下对应

    def labels(self):
        n_marker = sum(1 for l in self.lanes if l["marker"])
        out = []
        s = m = 0
        for l in self.lanes:
            if l["marker"]:
                m += 1
                out.append("M" if n_marker == 1 else "M%d" % m)
            else:
                s += 1
                out.append(str(s))
        return out

    def bounds(self, i):
        xs = [l["x"] for l in self.lanes]
        n = len(xs)
        if n == 1:
            return max(0.0, xs[0] - 50.0), min(self.W, xs[0] + 50.0)
        if i == 0:
            if self.lanes[0]["marker"]:
                left = 0.0
            else:
                left = max(0.0, xs[0] - (xs[1] - xs[0]) / 2.0)
        else:
            left = (xs[i - 1] + xs[i]) / 2.0
        if i == n - 1:
            if self.lanes[-1]["marker"]:
                right = self.W
            else:
                right = min(self.W, xs[-1] + (xs[-1] - xs[-2]) / 2.0)
        else:
            right = (xs[i] + xs[i + 1]) / 2.0
        return left, right

    # -- 条带 -------------------------------------------------------------
    def add_band(self, i, top, bottom):
        top, bottom = sorted((float(top), float(bottom)))
        center = (top + bottom) / 2.0
        self.bands.setdefault(i, []).append({
            "top": top,
            "bottom": bottom,
            "center": center,
            "thick_px": bottom - top,
            "thick_val": (bottom - top) * self.scale,
            "dist_px": center - self.ref_y,
            "dist_val": (center - self.ref_y) * self.scale,
        })
        self.skipped.discard(i)
        # 条带数量变了，原先的分子量对应关系失效
        self.marker_kda.pop(i, None)
        return self.bands[i][-1]

    def pop_band(self, i):
        if self.bands.get(i):
            b = self.bands[i].pop()
            if not self.bands[i]:
                del self.bands[i]
            self.marker_kda.pop(i, None)
            return b
        return None

    def clear_bands(self, i):
        self.bands.pop(i, None)
        self.skipped.discard(i)
        self.marker_kda.pop(i, None)

    def set_marker_kda(self, i, values):
        """values 按条带从上到下；数量必须与已测条带数一致。"""
        vals = [float(v) for v in values]
        if not vals or len(vals) != len(self.bands.get(i, [])):
            return False
        if any(v <= 0 for v in vals):
            return False
        self.marker_kda[i] = vals
        return True

    def set_ref(self, y):
        """重设参考线，并重算所有已测条带的距离。"""
        self.ref_y = float(y)
        for bs in self.bands.values():
            for b in bs:
                b["dist_px"] = b["center"] - self.ref_y
                b["dist_val"] = b["dist_px"] * self.scale


def parse_kda(text):
    """解析分子量输入：逗号/空格/分号分隔，返回 float 列表。"""
    if not text:
        return []
    t = (text.replace("，", ",").replace("；", ",").replace(";", ",")
         .replace("\t", ",").replace(" ", ","))
    vals = []
    for p in t.split(","):
        p = p.strip()
        if p:
            vals.append(float(p))
    return vals


def apply_kda_values(model, text, quiet=False, only_missing=False):
    """把一组 kDa 值应用到条带数恰好相同的所有 Marker 泳道。"""
    vals = parse_kda(text)
    if not vals:
        return 0
    applied = 0
    for i, l in enumerate(model.lanes):
        if only_missing and i in model.marker_kda:
            continue
        if l["marker"] and model.set_marker_kda(i, vals):
            applied += 1
    if not quiet:
        if applied:
            print("已为 %d 个 Marker 泳道设置分子量：%s kDa"
                  % (applied, ", ".join("%g" % v for v in vals)))
        else:
            counts = ["%s:%d 条" % (model.labels()[i],
                                    len(model.bands.get(i, [])))
                      for i, l in enumerate(model.lanes)
                      if l["marker"]
                      and not (only_missing and i in model.marker_kda)]
            if counts:
                print("警告：没有 Marker 泳道的条带数与输入的 %d 个分子量一致"
                      "（%s）。" % (len(vals), "，".join(counts)))
    return applied


# ----------------------------------------------------------------------------
# 绘制
# ----------------------------------------------------------------------------
def draw_gel(ax, rgb_bgr, model, final=False, cur=-1, hover=-1,
             pending_top=None):
    H, W = rgb_bgr.shape[:2]
    scale, unit = model.scale, model.unit
    ax.imshow(cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB),
              origin="upper", interpolation="nearest")

    labels = model.labels()
    n_lane = len(model.lanes)

    # 当前泳道 / 悬停泳道高亮
    if not final and 0 <= cur < n_lane:
        left, right = model.bounds(cur)
        ax.add_patch(Rectangle((left, 0), right - left, H,
                               facecolor="#FFD54F", edgecolor="none",
                               alpha=0.14, zorder=1.4))
    if not final and 0 <= hover < n_lane and hover != cur:
        left, right = model.bounds(hover)
        ax.add_patch(Rectangle((left, 0), right - left, H,
                               facecolor="#64B5F6", edgecolor="none",
                               alpha=0.10, zorder=1.3))

    # 加样参考线（只画在凝胶范围内）
    ax.plot([0, W], [model.ref_y, model.ref_y], color="#1f77b4",
            ls=(0, (6, 3)), lw=0.9, zorder=3)
    if not final:
        ax.text(4, model.ref_y + 4, "加样参考线", color="#1f77b4",
                fontsize=7, ha="left", va="bottom", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", fc="white",
                          ec="none", alpha=0.75))

    # 指示剂前沿（dye front）：横贯整幅图的一条线
    dye = getattr(model, "dye_front", None)
    if dye is not None:
        dye = float(dye)
        ax.plot([0, W], [dye, dye], color="#00796B", ls=(0, (2, 2)),
                lw=1.3 if final else 1.6, zorder=6)
        d_val = (dye - model.ref_y) * model.scale
        ax.text(W - 6, dye - 2,
                "dye front  %.1f %s" % (d_val, model.unit),
                color="#00695C", fontsize=6.5 if final else 8,
                ha="right", va="bottom", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", fc="white",
                          ec="none", alpha=0.8))

    # 泳道分隔线与编号
    for i, l in enumerate(model.lanes):
        left, right = model.bounds(i)
        ax.axvline(left, color="0.5", ls=":", lw=0.7, zorder=2)
        if i == n_lane - 1:
            ax.axvline(right, color="0.5", ls=":", lw=0.7, zorder=2)
        ax.text(l["x"], 8 if final else 14, labels[i],
                color="red", fontsize=8 if final else 12,
                ha="center", va="top", zorder=6,
                bbox=dict(boxstyle="round,pad=0.12", fc="white",
                          ec="none", alpha=0.75))

    # 测量结果
    for i, l in enumerate(model.lanes):
        bs = sorted(model.bands.get(i, []), key=lambda b: b["center"])
        left, right = model.bounds(i)
        cx = l["x"]

        if not bs:
            if (not l["marker"]) and (final or i in model.skipped):
                ax.text(cx, H * 0.55, "n.d.", color="0.45",
                        fontsize=7 if final else 10,
                        ha="center", va="center", zorder=5)
            continue

        multi = len(bs) > 1
        for k, b in enumerate(bs):
            ax.add_patch(Rectangle(
                (left, b["top"]), right - left, b["bottom"] - b["top"],
                fill=False, edgecolor="red", lw=0.8, zorder=4))
            ax.plot([left, right], [b["center"], b["center"]],
                    color="red", lw=0.7, zorder=4)

            if not multi:
                ax.annotate(
                    "", xy=(cx, b["center"]), xytext=(cx, model.ref_y),
                    arrowprops=dict(arrowstyle="<->", color="red", lw=0.8,
                                    shrinkA=0, shrinkB=0), zorder=4)

            txt = ("%.1f" % b["dist_val"]) if final \
                else ("%.1f %s" % (b["dist_val"], unit))

            if l["marker"] or multi:
                # Marker / 多条带：数字放在泳道内靠近分隔线的一侧，
                # 避免条带之间互相压字
                if left < W * 0.5:
                    tx, ha = right - 4, "right"
                else:
                    tx, ha = left + 4, "left"
                if multi:
                    txt = "%d: %s" % (k + 1, txt)
                ax.text(tx, b["center"], txt,
                        color="red", fontsize=5.5 if final else 8,
                        ha=ha, va="center", zorder=7,
                        bbox=dict(boxstyle="round,pad=0.08", fc="white",
                                  ec="none", alpha=0.82))
            else:
                # 普通泳道：数字标在条带下方
                ax.text(cx, b["bottom"] + (10 if not final else 6), txt,
                        color="red", fontsize=7 if final else 10,
                        ha="center", va="top", zorder=6,
                        bbox=dict(boxstyle="round,pad=0.12", fc="white",
                                  ec="none", alpha=0.75))

    # 正在标记的条带上边缘
    if pending_top is not None:
        ax.plot([0, W], [pending_top, pending_top], color="orange",
                lw=1.0, zorder=5)

    # Marker 分子量标尺（画在靠近边缘的一侧）
    M = 0.10 * W
    kda_items = []
    for i, l in enumerate(model.lanes):
        bs = sorted(model.bands.get(i, []), key=lambda b: b["center"])
        vals = model.marker_kda.get(i)
        if not (l["marker"] and vals and len(vals) == len(bs) and bs):
            continue
        if l["x"] <= 0.15 * W:
            side = "left"
        elif l["x"] >= 0.85 * W:
            side = "right"
        else:
            continue
        for k, b in enumerate(bs):
            kda_items.append((side, b["center"], vals[k]))

    fs_kda = 6.5 if final else 8
    for side, y, v in kda_items:
        if side == "left":
            ax.plot([-0.45 * M, 0], [y, y], color="0.2", lw=0.6, zorder=6)
            ax.text(-0.52 * M, y, "%g" % v, ha="right", va="center",
                    fontsize=fs_kda, color="black", zorder=6)
        else:
            ax.plot([W, W + 0.45 * M], [y, y], color="0.2", lw=0.6,
                    zorder=6)
            ax.text(W + 0.52 * M, y, "%g" % v, ha="left", va="center",
                    fontsize=fs_kda, color="black", zorder=6)
    if kda_items:
        sides = {s for s, _, _ in kda_items}
        if "left" in sides:
            ax.text(-0.52 * M, 10, "kDa", ha="right", va="top",
                    fontsize=fs_kda, fontweight="bold", color="black",
                    zorder=6)
        if "right" in sides:
            ax.text(W + 0.52 * M, 10, "kDa", ha="left", va="top",
                    fontsize=fs_kda, fontweight="bold", color="black",
                    zorder=6)

    # 比例尺
    bar_val = 5.0 if unit == "mm" else 100.0
    bar_px = bar_val / scale
    x1 = W - 18
    x0 = x1 - bar_px
    y = H - 16
    if 10 < bar_px < W * 0.35:
        ax.plot([x0, x1], [y, y], color="black",
                lw=1.5 if final else 2.0,
                solid_capstyle="butt", zorder=6)
        ax.text((x0 + x1) / 2.0, y - 4,
                ("%g %s" % (bar_val, unit)),
                ha="center", va="bottom",
                fontsize=6 if final else 8, color="black", zorder=6,
                bbox=dict(boxstyle="round,pad=0.1", fc="white",
                          ec="none", alpha=0.8))

    if final:
        left_m = M if any(s == "left" for s, _, _ in kda_items) else 0.0
        right_m = M if any(s == "right" for s, _, _ in kda_items) else 0.0
        ax.set_xlim(-left_m, W + right_m)
    else:
        ax.set_xlim(-M, W + M)
    ax.set_ylim(H, 0)
    ax.set_axis_off()
    if final:
        ax.set_title("数字：条带中心到加样参考线的距离 / %s"
                     "（Marker 泳道为“序号: 距离”）" % unit,
                     fontsize=7.5, pad=4)


# ----------------------------------------------------------------------------
# 保存结果
# ----------------------------------------------------------------------------
def save_outputs(rgb_bgr, model, out_prefix):
    H, W = rgb_bgr.shape[:2]
    png = os.path.join(BASE, out_prefix + "_lane_annotated.png")
    csv_path = os.path.join(BASE, out_prefix + "_lane_measurements.csv")

    # 最终标注图（单独的干净画布）
    fig, ax = plt.subplots(figsize=(6.4, 6.4 * H / W), dpi=300)
    draw_gel(ax, rgb_bgr, model, final=True)
    try:
        fig.savefig(png, dpi=300, facecolor="white",
                    bbox_inches="tight", pad_inches=0.02)
    except PermissionError:
        png = os.path.join(BASE, out_prefix + "_lane_annotated_alt.png")
        fig.savefig(png, dpi=300, facecolor="white",
                    bbox_inches="tight", pad_inches=0.02)
        print("提示：原 PNG 被占用（可能在看图软件中打开），已改写到 %s" % png)
    plt.close(fig)

    labels = model.labels()
    data_rows = []
    n_band = 0

    # 当前标注图在原始凝胶图中的位置（应用内裁剪后会非零），
    # 写入 CSV 以便下次 --from-csv / --edit 时精确复位。
    rect = getattr(model, "crop_rect", None)
    img_x0 = float(rect[0]) if rect else 0.0
    img_y0 = float(rect[1]) if rect else 0.0
    img_cols = ["%.1f" % img_x0, "%.1f" % img_y0, "%d" % W, "%d" % H]

    if model.dye_front is not None:
        dye_px_str = "%.1f" % model.dye_front
        dye_val_str = "%.2f" % ((model.dye_front - model.ref_y) * model.scale)
    else:
        dye_px_str = dye_val_str = ""
    for i, l in enumerate(model.lanes):
        left, right = model.bounds(i)
        bs = sorted(model.bands.get(i, []), key=lambda b: b["center"])
        base = [i + 1, labels[i], int(l["marker"]), 0, len(bs),
                "%.1f" % l["x"], "%.1f" % left, "%.1f" % right]
        kda_vals = model.marker_kda.get(i)
        if kda_vals and len(kda_vals) != len(bs):
            kda_vals = None
        if bs:
            for k, b in enumerate(bs):
                kda_str = "%g" % kda_vals[k] if kda_vals else ""
                data_rows.append(base[:3] + [k + 1, len(bs)] + base[5:] + [
                    "%.1f" % b["top"], "%.1f" % b["bottom"],
                    "%.1f" % b["center"],
                    "%.1f" % b["thick_px"], "%.2f" % b["thick_val"],
                    "%.1f" % b["dist_px"], "%.2f" % b["dist_val"],
                    kda_str, dye_px_str, dye_val_str] + img_cols + [
                    model.unit, "ok",
                ])
                n_band += 1
        else:
            note = ("skipped" if i in model.skipped else
                    ("marker_no_band" if l["marker"] else "not_measured"))
            data_rows.append(base[:3] + [0, 0] + base[5:] + [
                "", "", "", "", "", "", "", "", dye_px_str, dye_val_str,
            ] + img_cols + [
                model.unit, note,
            ])

    header = [
        "lane_index", "label", "is_marker", "band_index", "band_count",
        "x_center_px", "x_left_px", "x_right_px",
        "y_top_px", "y_bottom_px", "y_center_px",
        "thickness_px", "thickness_value",
        "distance_px", "distance_value", "marker_kda",
        "dye_front_px", "dye_front_value",
        "img_x0_px", "img_y0_px", "img_w_px", "img_h_px",
        "unit", "note",
    ]
    for path in (csv_path,
                 os.path.join(BASE, out_prefix + "_lane_measurements_alt.csv")):
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(data_rows)
            if path != csv_path:
                print("提示：原 CSV 被占用（可能在 Excel 中打开），已改写到 %s"
                      % path)
            csv_path = path
            break
        except PermissionError:
            continue
    else:
        print("错误：CSV 无法写入（文件被占用）。")

    print("\n已保存：")
    print("  " + png)
    print("  " + csv_path)
    print("\n测量结果（%d 条带，单位 %s）：" % (n_band, model.unit))
    print("  %-5s %-6s %6s %10s %10s %8s" %
          ("lane", "type", "#band", "dist", "thick", "kDa"))
    for i, l in enumerate(model.lanes):
        bs = sorted(model.bands.get(i, []), key=lambda b: b["center"])
        typ = "Marker" if l["marker"] else "sample"
        kda_vals = model.marker_kda.get(i)
        if kda_vals and len(kda_vals) != len(bs):
            kda_vals = None
        if not bs:
            print("  %-5s %-6s %6s %10s %10s %8s" %
                  (labels[i], typ, 0, "-", "-", "-"))
            continue
        for k, b in enumerate(bs):
            print("  %-5s %-6s %6d %8.2f  %8.2f %8s" %
                  (labels[i], typ, k + 1, b["dist_val"], b["thick_val"],
                   ("%g" % kda_vals[k]) if kda_vals else "-"))
    if model.dye_front is not None:
        print("\n指示剂前沿（dye front）：y=%.1f px，距加样参考线 %.2f %s"
              % (model.dye_front,
                 (model.dye_front - model.ref_y) * model.scale, model.unit))


def _gel_bbox(img_gray):
    """找出标注图中凝胶图像所占的区域（四周白边 / 标题 / kDa 标尺不算）。"""
    nonwhite = (img_gray < 240).astype(np.float32)
    rows = nonwhite.mean(axis=1)
    cols = nonwhite.mean(axis=0)
    ry = np.where(rows > 0.5)[0]
    rx = np.where(cols > 0.5)[0]
    if len(rx) < 10 or len(ry) < 10:
        return None
    return int(rx[0]), int(rx[-1]), int(ry[0]), int(ry[-1])


def guess_crop_rect(gel_bgr, ann_bgr, min_w=0.0, min_h=0.0):
    """从旧版标注图反推当时用 c 裁剪出的矩形（相对凝胶图坐标）。

    旧版 CSV 没记录裁剪区域，但 *_lane_annotated.png 本身就是
    “裁剪后的图 + 标注”。抹掉红色标注后与凝胶图做多尺度匹配即可。
    返回 (x0, y0, x1, y1) 或 None。
    """
    g = cv2.cvtColor(gel_bgr, cv2.COLOR_BGR2GRAY)
    bb = _gel_bbox(cv2.cvtColor(ann_bgr, cv2.COLOR_BGR2GRAY))
    if bb is None:
        return None
    gx0, gx1, gy0, gy1 = bb
    sub = ann_bgr[gy0:gy1 + 1, gx0:gx1 + 1]
    if sub.size == 0:
        return None
    sg = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b, gg, r = cv2.split(sub.astype(np.int16))
    # 红/蓝标注线与白底文字框会干扰匹配，做掩膜
    bad = ((((r - gg) > 60) & (r > 120)) | (sg > 245)).astype(np.uint8)
    bad = cv2.dilate(bad, np.ones((5, 5), np.uint8))
    keep = ((1 - bad) * 255).astype(np.uint8)
    if (keep > 0).mean() < 0.4:
        return None

    def hp(img):
        return img - cv2.GaussianBlur(img, (0, 0), 12)

    gel_hp = hp(g.astype(np.float32))
    aspect = (gy1 - gy0 + 1) / float(gx1 - gx0 + 1)
    W_gel, H_gel = g.shape[1], g.shape[0]
    w_lo = max(24, int(np.ceil(min_w)),
               int(np.ceil(min_h / max(aspect, 1e-6))))
    w_hi = min(W_gel, int(H_gel / max(aspect, 1e-6)))
    if w_hi <= w_lo + 4:
        return None

    best = (-1.0, None)
    for step in (8, 2):
        if best[1] is None:
            lo, hi = w_lo, w_hi
        else:
            w0 = best[1][2]
            lo = max(w_lo, w0 - 4 * step)
            hi = min(w_hi, w0 + 4 * step)
        for w in range(lo, hi + 1, step):
            h = int(round(w * aspect))
            if h < 8 or h > H_gel or w > W_gel:
                continue
            tpl = hp(cv2.resize(sg, (w, h), interpolation=cv2.INTER_AREA))
            m = cv2.resize(keep, (w, h), interpolation=cv2.INTER_NEAREST)
            if (m > 0).mean() < 0.4:
                continue
            res = cv2.matchTemplate(gel_hp, tpl, cv2.TM_CCORR_NORMED,
                                    mask=m)
            _, mx, _, ml = cv2.minMaxLoc(res)
            if mx > best[0]:
                best = (mx, (ml[0], ml[1], w, h))
    score, rect = best
    if rect is None or score < 0.12:
        return None
    x0, y0, w, h = rect
    x0 = max(0, min(x0, W_gel - w))
    y0 = max(0, min(y0, H_gel - h))
    print("从标注图恢复裁剪区域：x=%d..%d, y=%d..%d（匹配度 %.2f）"
          % (x0, x0 + w, y0, y0 + h, score))
    return x0, y0, x0 + w, y0 + h


def load_from_csv(csv_path, crop_override=None):
    """从已有的 *_lane_measurements.csv 还原模型和凝胶图，便于补加 kDa 标尺。"""
    csv_path = os.path.abspath(csv_path)
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("CSV 为空: %s" % csv_path)

    base = os.path.basename(csv_path)
    suffix = "_lane_measurements.csv"
    prefix = (base[:-len(suffix)] if base.endswith(suffix)
              else os.path.splitext(base)[0])

    candidates = []
    for folder in (os.path.dirname(csv_path), BASE):
        candidates.append(os.path.join(folder, prefix + "_gel_flipped.png"))
        candidates.append(os.path.join(folder, prefix + "_gel.png"))
    img_path = next((p for p in candidates if os.path.isfile(p)), None)
    if img_path is None:
        sys.exit("找不到与 CSV 对应的凝胶图（%s_gel_flipped.png）。"
                 "请把 CSV 和凝胶图放在同一文件夹，或重新运行测量。"
                 % prefix)
    color = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8),
                         cv2.IMREAD_COLOR)
    if color is None:
        sys.exit("无法读取凝胶图: %s" % img_path)
    H, W = color.shape[:2]

    grouped = {}
    for r in rows:
        try:
            li = int(r["lane_index"])
        except (KeyError, TypeError, ValueError):
            continue
        grouped.setdefault(li, []).append(r)
    if not grouped:
        sys.exit("CSV 中没有有效的 lane_index。")

    scale, unit = 1.0, "mm"
    refs, scales = [], []
    for r in rows:
        try:
            dpx = float(r["distance_px"])
            dval = float(r["distance_value"])
        except (KeyError, TypeError, ValueError):
            continue
        if dpx:
            refs.append(float(r["y_center_px"]) - dpx)
            scales.append(abs(dval / dpx))
            unit = (r.get("unit") or "mm").strip() or "mm"
    if not refs:
        sys.exit("CSV 中没有可用的 distance_px/distance_value 列。")
    ref_y = float(np.median(refs))
    scale = float(np.median(scales))

    # ---- 应用内裁剪区域：新版 CSV 有记录，旧版从标注图反推 ----
    def _f(row, key):
        try:
            return float((row.get(key) or "").strip())
        except (TypeError, ValueError):
            return None

    crop = None
    if crop_override:
        crop = tuple(int(v) for v in crop_override)
        print("使用手动指定的裁剪区域：x=%d..%d, y=%d..%d"
              % (crop[0], crop[2], crop[1], crop[3]))
    else:
        cx0 = _f(rows[0], "img_x0_px")
        cy0 = _f(rows[0], "img_y0_px")
        cw = _f(rows[0], "img_w_px")
        ch = _f(rows[0], "img_h_px")
        if None not in (cx0, cy0, cw, ch) and cw > 0 and ch > 0:
            # 记录的矩形必须落在当前凝胶图范围内，否则说明这张图
            # 本身已经是裁剪后的图（此时无需再裁）
            if (cx0 + cw <= W and cy0 + ch <= H
                    and (cx0, cy0, cw, ch) != (0.0, 0.0, float(W), float(H))):
                crop = (int(round(cx0)), int(round(cy0)),
                        int(round(cx0 + cw)), int(round(cy0 + ch)))
        else:
            max_x = max_y = 0.0
            for r in rows:
                for key, target in (("x_right_px", "x"),
                                    ("y_bottom_px", "y")):
                    v = _f(r, key)
                    if v is None:
                        continue
                    if target == "x":
                        max_x = max(max_x, v)
                    else:
                        max_y = max(max_y, v)
            ann_path = next((p for p in (
                os.path.join(os.path.dirname(csv_path),
                             prefix + "_lane_annotated.png"),
                os.path.join(BASE, prefix + "_lane_annotated.png"),
                os.path.join(os.path.dirname(csv_path),
                             prefix + "_lane_annotated_alt.png"),
                os.path.join(BASE, prefix + "_lane_annotated_alt.png"),
            ) if os.path.isfile(p)), None)
            ann = None
            if ann_path:
                ann = cv2.imdecode(np.fromfile(ann_path, dtype=np.uint8),
                                   cv2.IMREAD_COLOR)
            need = max_x < 0.98 * W
            if ann is not None and not need:
                bb = _gel_bbox(cv2.cvtColor(ann, cv2.COLOR_BGR2GRAY))
                if bb is not None:
                    a_asp = (bb[3] - bb[2] + 1) / float(bb[1] - bb[0] + 1)
                    if abs(a_asp - H / float(W)) > 0.04 * (H / float(W)):
                        need = True
            if need and ann is not None:
                print("检测到旧版结果可能使用过应用内裁剪，"
                      "正在根据标注图恢复裁剪区域…")
                crop = guess_crop_rect(color, ann,
                                       min_w=max_x, min_h=max_y)
                if crop is None:
                    print("警告：无法自动恢复裁剪区域。若标注错位，"
                          "请加 --crop-rect x0,y0,x1,y1 手动指定。")
            elif need:
                print("警告：缺少标注图，无法判断旧结果是否裁剪过。"
                      "若标注错位，请加 --crop-rect x0,y0,x1,y1 手动指定。")

    if crop:
        x0, y0, x1, y1 = crop
        x0 = max(0, min(x0, W - 2))
        y0 = max(0, min(y0, H - 2))
        x1 = max(x0 + 2, min(x1, W))
        y1 = max(y0 + 2, min(y1, H))
        color = np.ascontiguousarray(color[y0:y1, x0:x1])
        H, W = color.shape[:2]
        crop = (x0, y0, x1, y1)
        print("使用裁剪区域：%dx%d（x=%d..%d, y=%d..%d）"
              % (W, H, x0, x1, y0, y1))

    model = GelModel(W, scale, unit)
    model.crop_rect = crop
    for li in sorted(grouped):
        rs = grouped[li]
        first = rs[0]
        model.lanes.append({
            "x": float(first["x_center_px"]),
            "marker": str(first.get("is_marker", "0")).strip()
                      in ("1", "True", "true"),
        })
        i = len(model.lanes) - 1
        notes = set((r.get("note") or "").strip() for r in rs)
        if "skipped" in notes:
            model.skipped.add(i)

        band_rows = [r for r in rs if (r.get("y_top_px") or "").strip()]
        for r in band_rows:
            try:
                top = float(r["y_top_px"])
                bottom = float(r["y_bottom_px"])
            except (KeyError, TypeError, ValueError):
                continue
            model.add_band(i, top, bottom)

        if "marker_kda" in rs[0]:
            kda = []
            for r in sorted(band_rows,
                            key=lambda r: float(r["y_center_px"])):
                v = (r.get("marker_kda") or "").strip()
                if v:
                    kda.append(float(v))
            if kda and len(kda) == len(model.bands.get(i, [])):
                model.marker_kda[i] = kda

    model.set_ref(ref_y)

    # 指示剂前沿（旧版 CSV 没有这两列，读不到就保持 None）
    dye_px = None
    for r in rows:
        v = (r.get("dye_front_px") or "").strip()
        if v:
            try:
                dye_px = float(v)
                break
            except ValueError:
                pass
    if dye_px is None:
        for r in rows:
            v = (r.get("dye_front_value") or "").strip()
            if v:
                try:
                    dye_px = ref_y + float(v) / scale
                    break
                except ValueError:
                    pass
    if dye_px is not None:
        model.dye_front = dye_px

    if sorted(grouped) != list(range(1, len(grouped) + 1)):
        print("警告：CSV 的 lane_index 不连续，已按顺序重建泳道。")
    print("已从 %s 还原 %d 条泳道、%d 条带（单位 %s）"
          % (base, len(model.lanes),
             sum(len(v) for v in model.bands.values()), unit))
    return model, color, prefix


# ----------------------------------------------------------------------------
# 交互界面
# ----------------------------------------------------------------------------
HELP_TEXT = """操作说明
────────────────────────────
左键：设定参考线 / 添加泳道中心 / 点条带上、下边缘
      在条带步骤点击其他泳道，可直接切换到该泳道
Enter / n：完成当前泳道，进入下一条
           最后一条泳道不会再自动保存，确认后按 q
m：把当前泳道设为 / 取消 Marker
k：输入当前 Marker 泳道各条带的分子量（kDa）
   保存（q）时也会自动询问尚未填写的边缘 Marker
s：跳过当前泳道（无条带）
b：上一条泳道
z：撤销当前泳道最后一条带
d：清空当前泳道所有条带
f：重新设定加样参考线（自动重算距离）
t：标注指示剂前沿（dye front）：点击其水平位置
c：框选裁剪，之后只显示框选范围内的图像
q：保存并退出
r：复位视图；滚轮缩放；方向键平移
h / ?：关闭本说明
────────────────────────────
Marker 泳道可连续测多条带，按 Enter / n 结束本泳道"""


class MarkerUI:
    def __init__(self, rgb_bgr, model, out_prefix, src_path,
                 kda_arg=None, dye_front_px=None, dye_front_mm=None,
                 resume=False):
        self.rgb = rgb_bgr
        self.model = model
        self.out_prefix = out_prefix
        self.src_path = src_path
        self.kda_arg = kda_arg
        self.H, self.W = rgb_bgr.shape[:2]

        self.state = "ref"
        self.cur = 0
        self.hover = -1
        self.pending_top = None
        self.saved = False
        self.help_visible = False
        self._dialog_closed_at = 0.0
        self._ref_return = None
        # 应用内裁剪
        self.crop_start = None      # 拖拽起点 (x, y)
        self.crop_rect = None       # [x0, y0, x1, y1]
        self._state_before_crop = None
        # 当前图像左上角在原始凝胶图中的位置（用于记录裁剪区域）
        rect = getattr(model, "crop_rect", None)
        self._img_x0 = float(rect[0]) if rect else 0.0
        self._img_y0 = float(rect[1]) if rect else 0.0
        # 指示剂前沿（dye front）
        self._state_before_dye = None
        self._dye_front_mm = None   # --dye-front-mm 待参考线确定后换算
        if dye_front_px is not None:
            self.model.dye_front = float(dye_front_px)
        if dye_front_mm is not None:
            self._dye_front_mm = float(dye_front_mm)
        self._view_margin = 0.10 * self.W
        self.view = [-self._view_margin, self.W + self._view_margin,
                     float(self.H), 0.0]

        if resume and model.lanes:
            # 载入已有标注后继续手动编辑：直接停在测量条带步骤，
            # 用户按 t 即可补充指示剂前沿。
            self.state = "bands"
            self.cur = len(model.lanes) - 1
            self.msg = ("已载入已有标注（%d 条泳道、%d 条带）。"
                        "按 t 再点击指示剂前沿即可补标；可继续点击补测条带；"
                        "按 b 回看前一条泳道，确认后按 q 保存退出。"
                        % (len(model.lanes),
                           sum(len(v) for v in model.bands.values())))
        else:
            self.msg = ("第 1 步：点击凝胶上侧“加样参考线”的位置；"
                        "直接按 Enter 使用图像上边缘 y=0。按 h 查看全部按键。")

        self.fig, self.ax = plt.subplots(
            figsize=(12, 12 * self.H / self.W))
        self.fig.subplots_adjust(left=0.01, right=0.99,
                                 top=0.935, bottom=0.09)
        try:
            self.fig.canvas.manager.set_window_title(
                "WB 标注 - %s" % os.path.basename(src_path))
        except Exception:
            pass

        # 断开 matplotlib 自带的快捷键，否则 s 会弹出“保存图片”对话框，
        # k/l 会切换坐标轴对数刻度，f 全屏、p/o 平移缩放等。
        try:
            mgr = self.fig.canvas.manager
            for cid in (getattr(mgr, "key_press_handler_id", None),
                        getattr(mgr, "button_press_handler_id", None),
                        getattr(mgr, "scroll_handler_id", None)):
                if cid is not None:
                    self.fig.canvas.mpl_disconnect(cid)
        except Exception:
            pass

        # 顶部步骤指示
        self.step_texts = []
        for i, name in enumerate(("① 加样参考线", "② 划分泳道", "③ 测量条带",
                                  "④ Marker 分子量")):
            t = self.fig.text(0.015 + i * 0.112, 0.965, name,
                              fontsize=9, color="0.55", va="center")
            self.step_texts.append(t)

        self.file_text = self.fig.text(
            0.99, 0.965, os.path.basename(src_path), fontsize=8,
            color="0.45", ha="right", va="center")

        # 底部状态栏
        self.msg_text = self.fig.text(
            0.5, 0.012, "", fontsize=9, ha="center", va="bottom",
            color="#222222", linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.4", fc="#F7F7F7",
                      ec="#aaaaaa", alpha=0.95))

        self.hint_text = self.fig.text(
            0.48, 0.965, "h 帮助 · c 裁剪 · 滚轮缩放 · 方向键平移",
            fontsize=7.5, color="0.55", ha="left", va="center")

        # 帮助浮层
        self.help_text = self.fig.text(
            0.5, 0.5, HELP_TEXT, fontsize=9, ha="center", va="center",
            linespacing=1.6, visible=False, zorder=200,
            bbox=dict(boxstyle="round,pad=0.7", fc="white",
                      ec="#555555", alpha=0.97))

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("button_release_event", self.on_release)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.fig.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.fig.canvas.mpl_connect("close_event", self.on_close)

        self._update_hud()
        self.redraw()
        plt.show()

    # -- 辅助 -------------------------------------------------------------
    def _lane_at(self, x):
        for i in range(len(self.model.lanes)):
            left, right = self.model.bounds(i)
            if left <= x <= right:
                return i
        return -1

    def _cur_label(self):
        if not self.model.lanes:
            return "-"
        return self.model.labels()[self.cur]

    def _update_hud(self):
        idx = {"ref": 0, "lanes": 1, "bands": 2}.get(self.state,
                                                      len(self.step_texts))
        for i, t in enumerate(self.step_texts):
            if self.state == "done" or i < idx:
                t.set_color("#2E7D32")
                t.set_fontweight("normal")
            elif i == idx:
                t.set_color("#C00000")
                t.set_fontweight("bold")
            else:
                t.set_color("0.55")
                t.set_fontweight("normal")

        # 第 4 步：当前正在测边缘 Marker 条带时点亮，提示按 k 输入分子量
        if self.state != "done" and len(self.step_texts) > 3:
            t4 = self.step_texts[3]
            lane = (self.model.lanes[self.cur]
                    if self.cur < len(self.model.lanes) else None)
            if (self.state == "bands" and lane is not None
                    and lane["marker"] and self.model.bands.get(self.cur)):
                if self.cur in self.model.marker_kda:
                    t4.set_color("#2E7D32")
                    t4.set_fontweight("normal")
                else:
                    t4.set_color("#C00000")
                    t4.set_fontweight("bold")
            else:
                t4.set_color("0.55")
                t4.set_fontweight("normal")
        self.msg_text.set_text(textwrap.fill(self.msg, 62))
        self.hint_text.set_visible(not self.help_visible)
        self.help_text.set_visible(self.help_visible)

    def _msg(self, text):
        self.msg = text
        self._update_hud()

    def band_prompt(self):
        if self.cur >= len(self.model.lanes):
            return ""
        label = self._cur_label()
        lane = self.model.lanes[self.cur]
        n = len(self.model.bands.get(self.cur, []))
        total = len(self.model.lanes)
        tag = "（Marker）" if lane["marker"] else ""
        if lane["marker"]:
            extra = "可连续测多条带，Enter/n 结束本泳道"
        else:
            extra = "点其他泳道可切换；Enter/n 结束本泳道"
        if self.cur == total - 1:
            extra += "；已是最后一条，q 保存退出"
        if n:
            k_hint = "按 k 输入分子量（kDa）；" if lane["marker"] else ""
            return ("第 3 步：泳道 %s%s 已测 %d 条；继续点条带上边缘；%s%s"
                    % (label, tag, n, k_hint, extra))
        return ("第 3 步：泳道 %s%s（第 %d/%d 条）——点击最粗条带的上边缘；"
                "s 跳过；%s" % (label, tag, self.cur + 1, total, extra))

    def next_band_msg(self):
        self._msg(self.band_prompt())

    # -- 状态切换 ---------------------------------------------------------
    def set_reference(self, y):
        self.model.set_ref(float(np.clip(y, 0, self.H - 1)))
        # 命令行给的 dye front 距离要等参考线确定后才能换算成像素
        if self._dye_front_mm is not None and self.model.dye_front is None:
            self.model.dye_front = float(np.clip(
                self.model.ref_y + self._dye_front_mm / self.model.scale,
                0, self.H - 1))
            print("已按 %.2f %s 标注指示剂前沿: y=%.1f px"
                  % (self._dye_front_mm, self.model.unit,
                     self.model.dye_front))
            self._dye_front_mm = None
        if self._ref_return:
            self.state = self._ref_return
            self._ref_return = None
        else:
            self.state = "bands" if self.model.lanes else "lanes"
        if self.state == "bands":
            self.next_band_msg()
        else:
            self._msg("第 2 步：从左到右点击每条泳道的中心；"
                      "Enter 进入条带测量；u 撤销；m 设为 Marker。")

    def advance_lane(self, skip=False):
        i = self.cur
        if 0 <= i < len(self.model.lanes):
            if not self.model.bands.get(i) and not self.model.lanes[i]["marker"]:
                self.model.skipped.add(i)
        if self.cur + 1 >= len(self.model.lanes):
            # 最后一条泳道：不自动结束，交给用户按 q 明确保存
            self.pending_top = None
            self._msg("已是最后一条泳道（%s）。还可继续点击补测条带；"
                      "按 b 返回上一条；确认无误后按 q 保存退出。"
                      % self._cur_label())
            return
        self.cur += 1
        self.next_band_msg()

    # -- 应用内裁剪 -------------------------------------------------------
    def start_crop(self):
        self._state_before_crop = self.state
        self.state = "crop"
        self.pending_top = None
        self.hover = -1
        self.crop_start = None
        self.crop_rect = None
        extra = ""
        if self.model.lanes:
            extra = "（应用后会清除已点击的泳道和条带）"
        self._msg("裁剪：按住左键拖动，框选要保留的凝胶区域；"
                  "Enter 应用%s；Esc 取消。" % extra)
        self._update_hud()
        self.redraw()

    def cancel_crop(self):
        self.state = self._state_before_crop or "ref"
        self._state_before_crop = None
        self.crop_start = None
        self.crop_rect = None
        self._msg("已取消裁剪。")
        self._update_hud()
        self.redraw()

    def apply_crop(self):
        rect = self.crop_rect
        if not rect:
            self._msg("请先按住左键拖出一个矩形，再按 Enter。")
            return
        x0, y0, x1, y1 = rect
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        x0 = int(max(0, min(round(x0), self.W - 2)))
        x1 = int(max(1, min(round(x1), self.W)))
        y0 = int(max(0, min(round(y0), self.H - 2)))
        y1 = int(max(1, min(round(y1), self.H)))
        w, h = x1 - x0, y1 - y0
        if w < 20 or h < 20:
            self._msg("裁剪区域太小（至少 20×20 像素），请重新框选。")
            return

        self.rgb = np.ascontiguousarray(self.rgb[y0:y1, x0:x1])
        self._img_x0 += x0
        self._img_y0 += y0
        self.H, self.W = self.rgb.shape[:2]
        self.model.W = float(self.W)
        self.model.crop_rect = (self._img_x0, self._img_y0,
                                self._img_x0 + self.W, self._img_y0 + self.H)
        self.model.lanes = []
        self.model.bands = {}
        self.model.skipped = set()
        self.model.marker_kda = {}
        self.model.ref_y = 0.0
        if self.model.dye_front is not None:
            dy = self.model.dye_front - y0
            self.model.dye_front = dy if 0 <= dy <= h else None
        self.cur = 0
        self.hover = -1
        self._ref_return = None
        self._view_margin = 0.10 * self.W
        self.view = [-self._view_margin, self.W + self._view_margin,
                     float(self.H), 0.0]
        self.state = "ref"
        self._state_before_crop = None
        self.crop_start = None
        self.crop_rect = None
        self._msg("已裁剪：只显示框选范围（%d×%d 像素）。"
                  "请重新点击加样参考线。" % (self.W, self.H))
        self._update_hud()
        self.redraw()

    def finish(self, close=False):
        if self.state == "done":
            if close:
                plt.close(self.fig)
            return
        self.state = "done"
        self.pending_top = None
        self.hover = -1
        if self.kda_arg:
            apply_kda_values(self.model, self.kda_arg, only_missing=True)
            self.kda_arg = None
        if not self.saved:
            # 第 4 步：保存前询问尚未填写的边缘 Marker 分子量
            self.prompt_missing_kda()
        self.save_outputs()
        self._msg("标注完成，已保存 PNG 和 CSV。按 Enter 或 q 关闭窗口。")
        self.redraw()
        if close:
            plt.close(self.fig)

    def save_outputs(self):
        if self.saved:
            return
        self.saved = True
        save_outputs(self.rgb, self.model, self.out_prefix)

    def _ask_dialog(self, title, prompt, initial):
        try:
            import tkinter as tk
            from tkinter import simpledialog
        except Exception:
            self._msg("无法打开输入框；可在命令行用 --marker-kda 指定。")
            return None
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        root.update()
        try:
            val = simpledialog.askstring(title, prompt,
                                         initialvalue=initial, parent=root)
        except Exception:
            val = None
        root.destroy()
        # 记录关闭时刻：输入框确认用的 Enter 可能被主窗口再次收到
        self._dialog_closed_at = time.time()
        return val

    def edit_kda(self, note=""):
        """为当前 Marker 泳道输入各条带的分子量。"""
        if not self.model.lanes:
            return
        if not self.model.lanes[self.cur]["marker"]:
            self._msg("当前泳道不是 Marker；先按 m 设为 Marker，再按 k。")
            return
        bs = self.model.bands.get(self.cur, [])
        if not bs:
            self._msg("当前 Marker 泳道还没有条带；先测至少一条带。")
            return
        n = len(bs)
        initial = ""
        if self.cur in self.model.marker_kda:
            initial = ", ".join("%g" % v for v in self.model.marker_kda[self.cur])
        text = self._ask_dialog(
            "Marker 相对分子质量",
            "%s按从上到下的顺序输入 %d 个分子量（kDa），用逗号或空格分隔。\n"
            "当前泳道 %s，共 %d 条带；留空或取消则跳过。"
            % (note, n, self._cur_label(), n),
            initial)
        if text is None or not text.strip():
            return
        try:
            vals = parse_kda(text)
        except ValueError:
            self._msg("格式不对：请输入用逗号分隔的数字，例如 180,130,100。")
            return
        if len(vals) != n:
            self._msg("输入了 %d 个值，但当前泳道有 %d 条带；请按条带数输入。"
                      % (len(vals), n))
            return
        if not self.model.set_marker_kda(self.cur, vals):
            self._msg("分子量必须为正数，且数量要与条带数一致。")
            return
        self._msg("已为泳道 %s 的 %d 条带设置分子量：%s kDa；"
                  "标注图会在最%s侧生成 kDa 标尺。"
                  % (self._cur_label(), n,
                     ", ".join("%g" % v for v in vals),
                     "左" if self.model.lanes[self.cur]["x"] < self.W / 2
                     else "右"))

    def _pending_kda_lanes(self):
        """靠近图像左右边缘、有条带但还没填分子量的 Marker 泳道。"""
        pending = []
        for i, l in enumerate(self.model.lanes):
            if not (l["marker"] and self.model.bands.get(i)):
                continue
            if i in self.model.marker_kda:
                continue
            if l["x"] <= 0.15 * self.W or l["x"] >= 0.85 * self.W:
                pending.append(i)
        return pending

    def prompt_missing_kda(self):
        """保存前依次询问尚未填写的边缘 Marker 分子量。"""
        pending = self._pending_kda_lanes()
        total = len(pending)
        for n, i in enumerate(pending, 1):
            self.cur = i
            self._update_hud()
            self.edit_kda(note="【第 %d/%d 个 Marker 泳道】" % (n, total))
        if self.model.lanes:
            self.cur = min(self.cur, len(self.model.lanes) - 1)

    # -- 鼠标 -------------------------------------------------------------
    def on_click(self, event):
        if event.button != 1 or event.inaxes is None or event.xdata is None:
            return
        x, y = float(event.xdata), float(event.ydata)

        if self.help_visible:
            self.help_visible = False
            self._update_hud()
            self.redraw()
            return

        if self.state == "crop":
            self.crop_start = (x, y)
            self.crop_rect = [x, y, x, y]
            self.redraw()
            return

        if self.state == "dye":
            self.model.dye_front = y
            self.state = self._state_before_dye or "bands"
            self._state_before_dye = None
            d_val = (y - self.model.ref_y) * self.model.scale
            self._msg("已标注指示剂前沿：y=%.0f px，距加样参考线 %.2f %s。"
                      "按 t 可重新设置，Delete 移除。"
                      % (y, d_val, self.model.unit))
            self._update_hud()
            self.redraw()
            return

        if self.state == "ref":
            self.set_reference(y)

        elif self.state == "lanes":
            if self.model.lanes and x <= self.model.lanes[-1]["x"] + 5:
                self._msg("请按从左到右的顺序点击（当前点应在上一泳道右侧）。")
                self.redraw()
                return
            self.model.lanes.append({"x": x, "marker": False})
            self._msg("已添加 %d 条泳道；继续点击或按 Enter 进入条带测量；"
                      "u 撤销；m 把最后一条设为 Marker。"
                      % len(self.model.lanes))

        elif self.state == "bands":
            lane = self._lane_at(x)
            if lane < 0:
                self._msg("请点在泳道范围内。")
                self.redraw()
                return

            if self.pending_top is not None and lane != self.cur:
                # 先切换泳道，未完成的上边缘作废
                self.pending_top = None
                self.cur = lane
                self._msg("已切换到泳道 %s（上一条未完成的条带已取消）。"
                          % self._cur_label())
                self.redraw()
                return

            if lane != self.cur and self.pending_top is None:
                self.cur = lane
                self.next_band_msg()
                self._msg("已选择泳道 %s。点击条带上边缘开始测量；m 设为 Marker。"
                          % self._cur_label())
                self.redraw()
                return

            if self.pending_top is None:
                self.pending_top = y
                self._msg("已记录上边缘 y=%.0f：再点同一条带的下边缘；"
                          "Esc 取消。" % y)
            else:
                top, bottom = sorted((self.pending_top, y))
                if bottom - top < 3:
                    self._msg("条带厚度过小（<3 px），请重新点击上边缘。")
                    self.pending_top = None
                    self.redraw()
                    return
                b = self.model.add_band(self.cur, top, bottom)
                self.pending_top = None
                label = self._cur_label()
                lane_is_marker = self.model.lanes[self.cur]["marker"]
                if lane_is_marker:
                    self._msg("泳道 %s（Marker）已测第 %d 条带（距离 %.2f %s）。"
                              "继续点下一条带，或按 Enter/n 结束本泳道。"
                              % (label, len(self.model.bands[self.cur]),
                                 b["dist_val"], self.model.unit))
                else:
                    nxt = self.cur + 1
                    if nxt >= len(self.model.lanes):
                        # 最后一条泳道：不自动结束，等用户按 q 明确保存
                        self._msg("泳道 %s 已记录（距离 %.2f %s）。"
                                  "已是最后一条泳道；可继续补测条带，"
                                  "按 b 返回上一条，确认后按 q 保存退出。"
                                  % (label, b["dist_val"],
                                     self.model.unit))
                        self.redraw()
                        return
                    self.cur = nxt
                    self.next_band_msg()
                    self._msg("泳道 %s 已记录（距离 %.2f %s）；下一条：泳道 %s。"
                              % (label, b["dist_val"], self.model.unit,
                                 self._cur_label()))

        self.redraw()

    def on_motion(self, event):
        if self.help_visible:
            return
        if self.state == "crop":
            if self.crop_start is None or event.xdata is None:
                return
            x0, y0 = self.crop_start
            self.crop_rect = [x0, y0, float(event.xdata), float(event.ydata)]
            self.redraw()
            return
        if self.state != "bands":
            return
        if event.inaxes is None or event.xdata is None:
            new = -1
        else:
            new = self._lane_at(float(event.xdata))
        if new != self.hover:
            self.hover = new
            self.redraw()

    def on_release(self, event):
        if self.state != "crop" or self.crop_start is None:
            return
        self.crop_start = None
        r = self.crop_rect
        if r:
            w = abs(r[2] - r[0])
            h = abs(r[3] - r[1])
            if w >= 20 and h >= 20:
                self._msg("已框选 %d×%d 像素；Enter 应用（只显示该范围），"
                          "Esc 取消，可重新拖拽。" % (round(w), round(h)))
            else:
                self._msg("框选范围太小；请按住左键重新拖拽。")
        self.redraw()

    def on_scroll(self, event):
        if event.inaxes is None or event.xdata is None:
            return
        scale = 1.2 if event.button == "up" else 1.0 / 1.2
        x, y = float(event.xdata), float(event.ydata)
        x0, x1, y0, y1 = self.view
        new_w = (x1 - x0) * scale
        if new_w < 40 or new_w > self.W * 1.30:
            return
        self.view = [
            x + (x0 - x) * scale,
            x + (x1 - x) * scale,
            y + (y0 - y) * scale,
            y + (y1 - y) * scale,
        ]
        self.redraw()

    def on_close(self, event):
        if not self.saved and self.model.lanes:
            print("窗口已关闭；本次未保存。")

    # -- 键盘 -------------------------------------------------------------
    def on_key(self, event):
        k = (event.key or "").lower()

        # 输入框刚关闭时，确认用的 Enter 可能被主窗口再收到一次，
        # 若此时已完成会被误判为“关闭窗口”，短暂忽略。
        if (k in ("enter", "return")
                and time.time() - self._dialog_closed_at < 0.5):
            return

        # 裁剪模式：只响应确认 / 取消
        if self.state == "crop":
            if k in ("enter", "return"):
                self.apply_crop()
            elif k == "escape":
                self.cancel_crop()
            return

        # 设置指示剂前沿：点击确定位置，Esc 取消，Delete 移除
        if self.state == "dye":
            if k == "escape":
                self.state = self._state_before_dye or "bands"
                self._msg("已取消设置指示剂前沿。")
            elif k in ("delete", "backspace"):
                self.model.dye_front = None
                self.state = self._state_before_dye or "bands"
                self._msg("已移除指示剂前沿标注。")
            elif k in ("enter", "return"):
                self._msg("请点击指示剂前沿所在的水平位置；Esc 取消。")
            self._update_hud()
            self.redraw()
            return

        if k in ("h", "?"):
            self.help_visible = not self.help_visible
            self._update_hud()
            self.redraw()
            return

        if k == "escape":
            if self.help_visible:
                self.help_visible = False
            elif self.pending_top is not None:
                self.pending_top = None
                self._msg("已取消未完成的上边缘。")
            elif self.state == "ref" and self._ref_return:
                self.state = self._ref_return
                self._ref_return = None
                if self.state == "bands":
                    self.next_band_msg()
                else:
                    self._msg("已取消重设参考线。")
            self._update_hud()
            self.redraw()
            return

        if k in ("enter", "return", "n"):
            if self.state == "ref":
                self.set_reference(0.0)
            elif self.state == "lanes":
                if not self.model.lanes:
                    self._msg("至少点击一条泳道。")
                else:
                    self.state = "bands"
                    self.cur = 0
                    self.next_band_msg()
            elif self.state == "bands":
                if self.pending_top is not None:
                    self.pending_top = None
                    self._msg("未完成的上边缘已取消：一条带需要依次点击"
                              "上边缘和下边缘，只点一次不会显示。")
                    self.redraw()
                    return
                self.advance_lane()
            elif self.state == "done":
                plt.close(self.fig)
                return

        elif k == "m":
            if self.state == "lanes" and self.model.lanes:
                self.model.lanes[-1]["marker"] = \
                    not self.model.lanes[-1]["marker"]
                self._msg("最后一条泳道已%s Marker。"
                          % ("设为" if self.model.lanes[-1]["marker"]
                             else "取消"))
            elif self.state == "bands" and self.model.lanes:
                self.model.lanes[self.cur]["marker"] = \
                    not self.model.lanes[self.cur]["marker"]
                self.pending_top = None
                is_m = self.model.lanes[self.cur]["marker"]
                self._msg("泳道 %s 已%s Marker。%s"
                          % (self._cur_label(), "设为" if is_m else "取消",
                             self.band_prompt()))

        elif k == "k":
            if self.state == "bands":
                self.edit_kda()
            elif self.state == "lanes":
                self._msg("先按 Enter 进入条带测量；量完 Marker 泳道的条带后"
                          "按 k 输入分子量（也可在保存时统一填写）。")

        elif k == "u" and self.state == "lanes":
            if self.model.lanes:
                self.model.lanes.pop()
                self._msg("已撤销上一条泳道。")

        elif k == "s" and self.state == "bands":
            self.pending_top = None
            self.advance_lane(skip=True)

        elif k == "b" and self.state == "bands":
            if self.pending_top is not None:
                self.pending_top = None
                self._msg("已取消未完成的上边缘。")
            elif self.cur > 0:
                self.cur -= 1
                self.next_band_msg()
            else:
                self._msg("已经是第一条泳道。")

        elif k == "z" and self.state == "bands":
            b = self.model.pop_band(self.cur)
            if b is None:
                self._msg("当前泳道没有可撤销的条带。")
            else:
                self._msg("已撤销泳道 %s 最后添加的条带。%s"
                          % (self._cur_label(), self.band_prompt()))

        elif k == "d" and self.state == "bands":
            self.model.clear_bands(self.cur)
            self._msg("已清空泳道 %s 的所有条带。%s"
                      % (self._cur_label(), self.band_prompt()))

        elif k == "c" and self.state in ("ref", "lanes", "bands"):
            self.start_crop()

        elif k == "t" and self.state in ("lanes", "bands"):
            self._state_before_dye = self.state
            self.state = "dye"
            self.pending_top = None
            self._msg("点击指示剂前沿（dye front）所在的水平位置；"
                      "Esc 取消；Delete 移除已有标注。")

        elif k == "f" and self.state in ("lanes", "bands"):
            self._ref_return = self.state
            self.state = "ref"
            self.pending_top = None
            self._msg("重新设定参考线：点击新的加样位置（已有距离会自动重算）；"
                      "Enter 使用 y=0；Esc 取消。")

        elif k == "q":
            if self.state == "done" or not self.model.lanes:
                plt.close(self.fig)
                return
            self.finish(close=True)

        elif k == "r":
            m = self._view_margin
            self.view = [-m, self.W + m, float(self.H), 0.0]

        elif k in ("left", "right", "up", "down"):
            dx = (self.view[1] - self.view[0]) * 0.1
            dy = (self.view[2] - self.view[3]) * 0.1
            if k == "left":
                self.view[0] -= dx
                self.view[1] -= dx
            elif k == "right":
                self.view[0] += dx
                self.view[1] += dx
            elif k == "up":
                self.view[2] -= dy
                self.view[3] -= dy
            elif k == "down":
                self.view[2] += dy
                self.view[3] += dy

        self._update_hud()
        self.redraw()

    # -- 绘制 -------------------------------------------------------------
    def redraw(self):
        self.ax.clear()
        draw_gel(self.ax, self.rgb, self.model, final=False,
                 cur=self.cur if self.state == "bands" else -1,
                 hover=self.hover, pending_top=self.pending_top)
        if self.state == "crop" and self.crop_rect:
            x0, y0, x1, y1 = self.crop_rect
            self.ax.add_patch(Rectangle(
                (min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                fill=False, edgecolor="#1E88E5", lw=1.6, ls="--", zorder=30))
        self.ax.set_xlim(self.view[0], self.view[1])
        self.ax.set_ylim(self.view[2], self.view[3])
        self.fig.canvas.draw_idle()


# ----------------------------------------------------------------------------
# 无交互示例
# ----------------------------------------------------------------------------
def run_demo(rgb_bgr, scale, unit, out_prefix):
    H, W = rgb_bgr.shape[:2]
    model = GelModel(W, scale, unit)
    model.ref_y = 0.0

    centers = [50, 150, 250, 350, 450, 550,
               650, 750, 850, 950, 1050, 1150]
    model.lanes = [{"x": float(c), "marker": False} for c in centers]
    model.lanes[0]["marker"] = True
    model.lanes[-1]["marker"] = True

    # 示例条带（按当前自动检测的 FWHM 估计；仅用于看版式）
    bands = {
        1: (191, 209),
        2: (195, 211),
        3: (185, 205),
        4: (184, 212),
        5: (306, 328),
        6: (333, 345),
        7: (335, 353),
        8: (342, 352),
        9: (344, 354),
    }
    for i, (t, b) in bands.items():
        model.add_band(i, t, b)

    # 最后一条样品泳道没有条带
    model.skipped.add(10)
    model.dye_front = 430.0

    save_outputs(rgb_bgr, model, out_prefix + "_demo")


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="WB / 凝胶图像泳道与条带交互标注")
    ap.add_argument("--src", default=None,
                    help="图片路径；省略时弹出文件选择框（默认脚本文件夹）")
    ap.add_argument("--out-prefix", default=None,
                    help="输出文件名前缀（默认为图片文件名）")
    ap.add_argument("--rectify", action="store_true",
                    help="启用自动提取凝胶区域（自动找四角 + 透视校正）；"
                         "默认关闭，直接使用原图")
    ap.add_argument("--manual-corners", action="store_true",
                    help="手动点击凝胶四角（隐含 --rectify）")
    ap.add_argument("--flip", action="store_true",
                    help="水平翻转图像（默认不翻转）")
    ap.add_argument("--demo", action="store_true",
                    help="无交互，用预设示例生成一张标注图")
    ap.add_argument("--mm-per-px", type=float, default=None,
                    help="覆盖自动估算的比例（mm/像素）；未启用 --rectify "
                         "时给出此值才会用 mm 为单位")
    ap.add_argument("--no-crop", action="store_true",
                    help="（兼容旧参数）等同于默认行为：不自动提取凝胶区域")
    ap.add_argument("--no-flip", action="store_true",
                    help="（兼容旧参数）不水平翻转；现在本来就是默认行为")
    ap.add_argument("--marker-kda", default=None,
                    help="Marker 分子量（kDa），按从上到下用逗号分隔，"
                         "如 180,130,100,70,55,40,35")
    ap.add_argument("--from-csv", default=None,
                    help="从已有的 *_lane_measurements.csv 还原并重绘，"
                         "默认不再交互（通常配合 --marker-kda）")
    ap.add_argument("--edit", action="store_true",
                    help="配合 --from-csv：载入已有标注后打开交互窗口，"
                         "可继续手动补充（例如按 t 标指示剂前沿），q 保存")
    ap.add_argument("--dye-front-px", type=float, default=None,
                    help="指示剂前沿（dye front）的 y 像素坐标，"
                         "给已有结果补线时最直接")
    ap.add_argument("--dye-front-mm", type=float, default=None,
                    help="指示剂前沿距加样参考线的距离（mm，向下为正；"
                         "无 mm/px 标定时为 px）；交互模式下在参考线确定后生效")
    ap.add_argument("--crop-rect", default=None,
                    help="配合 --from-csv：手动指定旧结果的裁剪区域 "
                         "x0,y0,x1,y1（相对凝胶图的像素坐标）")
    args = ap.parse_args()

    if args.from_csv:
        crop_override = None
        if args.crop_rect:
            try:
                vals = [float(v) for v in
                        args.crop_rect.replace("，", ",").split(",")]
            except ValueError:
                vals = []
            if len(vals) != 4:
                sys.exit("--crop-rect 格式应为 x0,y0,x1,y1（像素坐标）")
            crop_override = tuple(int(round(v)) for v in vals)
        model, c, prefix = load_from_csv(args.from_csv,
                                         crop_override=crop_override)
        if args.out_prefix:
            prefix = args.out_prefix
        if args.marker_kda:
            apply_kda_values(model, args.marker_kda)
        elif any(model.marker_kda.values()):
            print("沿用 CSV 中已有的 Marker 分子量。")
        if args.dye_front_px is not None:
            model.dye_front = float(args.dye_front_px)
        elif args.dye_front_mm is not None:
            model.dye_front = model.ref_y + args.dye_front_mm / model.scale
        if args.edit:
            # 打开交互窗口，所有已有泳道 / 条带 / 分子量都保留，
            # 用户可直接按 t 手动补画指示剂前沿。
            print("进入编辑模式：按 t 标注指示剂前沿，q 保存退出。")
            MarkerUI(c, model, prefix, args.from_csv, resume=True)
            return
        save_outputs(c, model, prefix)
        return

    if args.edit:
        sys.exit("--edit 需要配合 --from-csv 使用："
                 "例如 --from-csv 4-8_Merge_lane_measurements.csv --edit")

    if args.demo and not args.src:
        args.src = os.path.join(BASE, "4-8_Merge.tif")
    src = args.src
    if not src:
        src = choose_image()
        if not src:
            sys.exit("未选择图片，已退出。")
    src = os.path.abspath(src)
    if not os.path.isfile(src):
        sys.exit("文件不存在: %s" % src)

    print("输入图片: %s" % src)
    prefix = args.out_prefix or os.path.splitext(os.path.basename(src))[0]
    print("输出前缀: %s" % prefix)

    gray, color = read_image(src)

    # 默认直接使用原图；只有显式 --rectify（或 --manual-corners）才提取凝胶
    do_rectify = (args.rectify or args.manual_corners) and not args.no_crop
    do_flip = args.flip and not args.no_flip

    if do_rectify:
        if args.manual_corners:
            src_pts = pick_corners(gray)
            auto = False
        else:
            src_pts, auto = detect_corners(gray)
        print("凝胶四角（TL, TR, BR, BL）:\n", np.round(src_pts, 1))
        print("自动检测:", "成功" if auto else "失败，使用经验四角")

        g, c, H, avg_h = rectify(gray, color, src_pts, flip=do_flip)
        scale = (args.mm_per_px if args.mm_per_px
                 else compute_mm_per_px(avg_h, H, gray.shape[0]))
        unit = "mm"
        print("已自动提取凝胶区域%s" % ("并水平翻转" if do_flip else ""))
    else:
        g, c = gray, color
        if do_flip:
            c = np.ascontiguousarray(c[:, ::-1])
            g = np.ascontiguousarray(g[:, ::-1])
        if args.mm_per_px:
            scale = args.mm_per_px
            unit = "mm"
        else:
            scale = 1.0
            unit = "px"
        print("直接使用原图 %dx%d（未自动提取%s）；单位 %s"
              % (c.shape[1], c.shape[0],
                 "，已水平翻转" if do_flip else "", unit))

    suffix = "_gel_flipped.png" if do_flip else "_gel.png"
    rect_path = os.path.join(BASE, prefix + suffix)
    ok, buf = cv2.imencode(".png", c)
    if not ok:
        sys.exit("保存失败: %s" % rect_path)
    buf.tofile(rect_path)
    print("供后续 --from-csv 还原用的图片: %s" % rect_path)
    print("输出尺寸: %dx%d, 比例: %.5f %s/px"
          % (c.shape[1], c.shape[0], scale, unit))

    if args.demo:
        run_demo(c, scale, unit, prefix)
        return

    model = GelModel(c.shape[1], scale, unit)
    MarkerUI(c, model, prefix, src, kda_arg=args.marker_kda,
             dye_front_px=args.dye_front_px,
             dye_front_mm=args.dye_front_mm)


if __name__ == "__main__":
    main()
