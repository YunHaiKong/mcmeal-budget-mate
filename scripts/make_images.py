#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦饭搭子 · 配图生成脚本
==========================

本项目的所有配图都由这个脚本**程序化生成**，不依赖任何设计稿或在线素材，
只要装了 Pillow 就能一键复现：

    python scripts/make_images.py

之所以不用 AI 生图：图表和流程图里的中文文字必须精确可读，程序化渲染才能保证
文字不糊、数字不错、版式对齐。生成结果落在 images/ 目录下。

许可：本文件是麦当劳程序员节创意开发大赛参赛作品的一部分。
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# 视觉规范
# --------------------------------------------------------------------------
RED = (214, 35, 0)
RED_DARK = (166, 26, 0)
YELLOW = (255, 192, 67)
YELLOW_SOFT = (255, 236, 179)
CREAM = (255, 250, 240)
DARK = (31, 35, 40)
GRAY = (107, 114, 128)
GRAY_LIGHT = (229, 231, 235)
WHITE = (255, 255, 255)
GREEN = (14, 138, 95)
BLUE = (37, 99, 235)
PURPLE = (124, 58, 237)

FONT_CANDIDATES = {
    "regular": ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
                "/System/Library/Fonts/PingFang.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"],
    "bold": ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyhbd.ttf",
             "/System/Library/Fonts/PingFang.ttc",
             "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"],
    "mono": ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/msyh.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
}

_cache: dict = {}


def _font_path(kind: str) -> str:
    for p in FONT_CANDIDATES[kind]:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("找不到可用字体，请安装微软雅黑或思源黑体")


def font(size: int, kind: str = "regular") -> ImageFont.FreeTypeFont:
    key = (size, kind)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(_font_path(kind), size)
    return _cache[key]


def text(d: ImageDraw.ImageDraw, xy, s: str, f, fill=DARK, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def tw(d: ImageDraw.ImageDraw, s: str, f) -> float:
    return d.textlength(s, font=f)


def rrect(d: ImageDraw.ImageDraw, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def pill(d: ImageDraw.ImageDraw, x, y, s: str, f, fg=DARK, bg=YELLOW_SOFT, padx=16, pady=8):
    """画一个胶囊标签，返回右边界 x。"""
    w = tw(d, s, f) + padx * 2
    h = f.size + pady * 2
    rrect(d, (x, y, x + w, y + h), h // 2, fill=bg)
    text(d, (x + padx, y + h / 2), s, f, fg, anchor="lm")
    return x + w


def vgradient(size, top, bottom):
    img = Image.new("RGB", size, top)
    d = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def arrow_down(d, cx, y0, y1, color=GRAY_LIGHT, w=4):
    d.line([(cx, y0), (cx, y1 - 12)], fill=color, width=w)
    d.polygon([(cx - 9, y1 - 14), (cx + 9, y1 - 14), (cx, y1)], fill=color)


# --------------------------------------------------------------------------
# 图 1：banner.png
# --------------------------------------------------------------------------
def make_banner(out: str):
    W, H = 1280, 420
    img = vgradient((W, H), CREAM, (255, 243, 224))
    d = ImageDraw.Draw(img)

    # 右上角装饰圆
    d.ellipse((W - 300, -180, W + 120, 240), fill=(255, 232, 196))
    d.ellipse((W - 120, 250, W + 160, 530), fill=(255, 222, 175))

    # 左侧文字区
    x = 72
    text(d, (x, 66), "麦当劳程序员节创意开发大赛 · 参赛作品", font(20, "regular"), GRAY)
    text(d, (x, 106), "麦麦饭搭子", font(72, "bold"), DARK)
    w = tw(d, "麦麦饭搭子", font(72, "bold"))
    text(d, (x + w + 14, 118), "· 午餐省钱官", font(38, "bold"), RED)

    text(d, (x, 214), "一句话说出人数、预算、忌口", font(26), DARK)
    text(d, (x, 252), "→ 算出实付最低的那一餐", font(26), DARK)

    px = x
    for label in ["满减券", "第二份半价", "买一送一", "免费单品", "折扣券"]:
        px = pill(d, px, 306, label, font(19), DARK, YELLOW_SOFT) + 10

    # 右下角"小票"卡片
    cx0, cy0, cx1, cy1 = W - 372, 84, W - 72, H - 60
    rrect(d, (cx0 + 6, cy0 + 8, cx1 + 6, cy1 + 8), 18, fill=(228, 214, 190))
    rrect(d, (cx0, cy0, cx1, cy1), 18, fill=WHITE)
    d.line([(cx0 + 28, cy0 + 66), (cx1 - 28, cy0 + 66)], fill=GRAY_LIGHT, width=2)
    text(d, (cx0 + 28, cy0 + 30), "本次午餐", font(21, "bold"), GRAY)

    rows = [("原价", "¥36.50", GRAY), ("优惠", "-¥7.00", RED), ("实付", "¥29.50", RED)]
    yy = cy0 + 92
    for k, v, col in rows:
        big = (k == "实付")
        text(d, (cx0 + 28, yy), k, font(23 if big else 21, "bold" if big else "regular"),
             DARK if big else GRAY)
        text(d, (cx1 - 28, yy), v, font(34 if big else 24, "bold"), col, anchor="ra")
        yy += 62 if big else 50
    text(d, (cx0 + 28, cy1 - 46), "省 19.2% ｜ 人均 513 kcal", font(19), GREEN)

    img.save(out)
    return out


# --------------------------------------------------------------------------
# 图 2：architecture.png  调用流程
# --------------------------------------------------------------------------
def make_architecture(out: str):
    W, H = 1180, 1010
    img = Image.new("RGB", (W, H), (252, 252, 253))
    d = ImageDraw.Draw(img)

    text(d, (56, 46), "「麦麦饭搭子」如何调用麦当劳 MCP", font(34, "bold"), DARK)
    text(d, (56, 96), "11 个 Tool，一条链路：从一句自然语言到实付最低的一餐", font(20), GRAY)

    steps = [
        ("①", "确认时间", "now-time-info", "判断当前供餐时段，决定菜单范围与券的有效性", BLUE),
        ("②", "定位门店", "query-nearby-stores / delivery-query-stores", "拿到 storeCode（外送场景先查收货地址）", BLUE),
        ("③", "拉菜单与营养", "query-meals · query-meal-detail · list-nutrition-foods", "候选餐品池 + 套餐组成 + 每项热量", GREEN),
        ("④", "收集优惠", "available-coupons · auto-bind-coupons · query-my-coupons · query-store-coupons · campaign-calendar", "四路券合并去重，再把当月活动折算成额外优惠", YELLOW),
        ("⑤", "本地求解", "scripts/optimize.py", "在约束下搜索实付最低的组合（快速解 + 精确解）", PURPLE),
        ("⑥", "官方计价复核", "calculate-price", "用麦当劳真实计价覆盖本地估算（含配送费、包装费）", GREEN),
        ("⑦", "呈现方案", "—", "原价 → 优惠 → 实付 → 省了多少，附热量", GRAY),
        ("⑧", "一键下单", "create-order", "仅在用户明确同意后执行，返回到店取餐码或支付链接", RED),
    ]

    y = 152
    box_x0, box_x1 = 118, W - 56
    for num, title, tools, desc, col in steps:
        h = 78 if len(tools) < 62 else 96
        rrect(d, (box_x0, y, box_x1, y + h), 14, fill=WHITE, outline=GRAY_LIGHT, width=2)
        rrect(d, (box_x0, y, box_x0 + 8, y + h), 4, fill=col)

        d.ellipse((44, y + h / 2 - 24, 92, y + h / 2 + 24), fill=col)
        text(d, (68, y + h / 2), num, font(22, "bold"), WHITE, anchor="mm")

        text(d, (box_x0 + 28, y + 18), title, font(23, "bold"), DARK)
        text(d, (box_x0 + 28, y + 50), tools, font(17, "regular"), col)
        text(d, (box_x0 + 28, y + 72), desc, font(17), GRAY)

        if num != "⑧":
            arrow_down(d, 68, y + h, y + h + 20)
        y += h + 20

    img.save(out)
    return out


# --------------------------------------------------------------------------
# 图 3：optimizer.png  两层求解
# --------------------------------------------------------------------------
def make_optimizer(out: str):
    W, H = 1150, 620
    img = Image.new("RGB", (W, H), (252, 252, 253))
    d = ImageDraw.Draw(img)

    text(d, (56, 44), "求解器为什么是两层结构", font(34, "bold"), DARK)
    text(d, (56, 94), "先要快要准，再要能证明它是最优的", font(20), GRAY)

    # 左：输入
    rrect(d, (56, 158, 250, 470), 16, fill=WHITE, outline=GRAY_LIGHT, width=2)
    text(d, (80, 182), "输入", font(22, "bold"), DARK)
    for i, s in enumerate(["菜单（30~60 项）", "优惠券（≤8 张）", "人数 / 预算", "热量上下限", "忌口 / 必备品类"]):
        text(d, (80, 226 + i * 42), "· " + s, font(17), GRAY)

    # 中：两层
    rrect(d, (300, 138, 800, 292), 16, fill=(245, 243, 255), outline=PURPLE, width=2)
    text(d, (326, 160), "第 1 层｜快速解", font(24, "bold"), PURPLE)
    text(d, (326, 198), "贪心构造保底篮子", font(18), DARK)
    text(d, (326, 226), "+ 有界背包 DP 求「最少加购顶过门槛」", font(18), DARK)
    text(d, (326, 258), "秒级出结果 → 用作剪枝的种子", font(17), GRAY)

    arrow_down(d, 550, 292, 336, PURPLE, 4)

    rrect(d, (300, 336, 800, 490), 16, fill=(240, 249, 245), outline=GREEN, width=2)
    text(d, (326, 358), "第 2 层｜精确解", font(24, "bold"), GREEN)
    text(d, (326, 396), "带下界剪枝的深度优先搜索", font(18), DARK)
    text(d, (326, 428), "剪枝：实付下界 = 当前小计 − 全局最大可能优惠", font(17, "bold"), GREEN)
    text(d, (326, 456), "下界 ≥ 当前最优 → 整枝剪掉；节点超预算则退回快速解", font(17), GRAY)

    # 右：输出
    rrect(d, (850, 158, W - 56, 470), 16, fill=WHITE, outline=GRAY_LIGHT, width=2)
    text(d, (874, 182), "输出", font(22, "bold"), DARK)
    text(d, (874, 228), "实付最低的", font(18), GRAY)
    text(d, (874, 254), "餐品组合", font(28, "bold"), RED)
    text(d, (874, 306), "麦香鸡套餐 ×1", font(17), DARK)
    text(d, (874, 332), "派（菠萝） ×1", font(17), DARK)
    text(d, (874, 372), "实付 ¥29.50", font(24, "bold"), RED)
    text(d, (874, 408), "省 19.2%", font(18, "bold"), GREEN)
    text(d, (874, 436), "1026 kcal", font(17), GRAY)

    # 底部说明
    rrect(d, (56, 512, W - 56, 578), 12, fill=(255, 249, 232), outline=YELLOW, width=2)
    text(d, (80, 545), "正确性由 tests/test_optimize.py 的随机对拍保证：随机生成小规模菜单与券，"
                      "用独立实现的暴力枚举作标准答案逐例比对。", font(17), DARK, anchor="lm")

    img.save(out)
    return out


# --------------------------------------------------------------------------
# 图 4：demo-result.png  真实运行结果
# --------------------------------------------------------------------------
def make_demo(out: str):
    """真实运行结果卡片。注意：中文必须用含 CJK 字形的字体渲染，
    因此这里用坐标对齐而不是等宽字符对齐。"""
    W, H = 980, 790
    img = Image.new("RGB", (W, H), (252, 252, 253))
    d = ImageDraw.Draw(img)

    text(d, (48, 40), "真实跑一次的完整输出", font(32, "bold"), DARK)
    text(d, (48, 88), "门店：麦当劳上海吴江路餐厅 · 数据取自麦当劳 MCP 的实时返回", font(18), GRAY)

    x0, y0, x1, y1 = 48, 136, W - 48, H - 48
    rrect(d, (x0, y0, x1, y1), 16, fill=(28, 30, 34))
    d.ellipse((x0 + 22, y0 + 20, x0 + 38, y0 + 36), fill=(255, 95, 86))
    d.ellipse((x0 + 48, y0 + 20, x0 + 64, y0 + 36), fill=(255, 189, 46))
    d.ellipse((x0 + 74, y0 + 20, x0 + 90, y0 + 36), fill=(39, 201, 63))
    text(d, (x0 + 108, y0 + 28), "optimize.py", font(15, "mono"), (120, 126, 136))

    # 标题
    text(d, (x0 + 34, y0 + 74), "麦麦饭搭子 · 午餐省钱官", font(26, "bold"), WHITE)
    text(d, (x1 - 34, y0 + 80), "最优方案", font(20, "bold"), YELLOW, anchor="ra")

    def divider(y, col=(58, 62, 70)):
        d.line([(x0 + 34, y), (x1 - 34, y)], fill=col, width=2)

    divider(y0 + 122)

    # 约束行（同一行内横向排布）
    fy = y0 + 142
    cx = x0 + 34
    for s in ["人数 2 人", "预算 ¥50.00", "人均 ≥500 kcal", "忌 含牛肉"]:
        text(d, (cx, fy), s, font(17), (140, 146, 156))
        cx += tw(d, s, font(17)) + 34

    # 餐品行
    divider(y0 + 184)
    iy = y0 + 206
    for name, price, cal in [("麦香鸡套餐", "¥28.00", "805 kcal"), ("派（菠萝）", "¥8.50", "221 kcal")]:
        text(d, (x0 + 34, iy), name, font(22, "bold"), WHITE)
        text(d, (x0 + 34, iy + 30), "×1", font(17), (120, 126, 136))
        text(d, (x1 - 150, iy + 2), price, font(24, "bold"), WHITE, anchor="ra")
        text(d, (x1 - 34, iy + 8), cal, font(17), (140, 146, 156), anchor="ra")
        iy += 68

    divider(iy - 12)

    rows = [
        ("小计", "¥36.50", (170, 176, 184), "regular", 22),
        ("优惠券", "-¥7.00  （满 30 减 7）", YELLOW, "regular", 22),
        ("实付", "¥29.50", (94, 226, 154), "bold", 36),
        ("总热量", "1026 kcal · 人均 513 kcal", (170, 176, 184), "regular", 20),
        ("求解方式", "精确最优", (94, 226, 154), "regular", 20),
    ]
    ry = iy + 14
    for label, value, col, w, sz in rows:
        big = (label == "实付")
        text(d, (x0 + 34, ry), label, font(20 if big else 18), (120, 126, 136))
        text(d, (x1 - 34, ry - (6 if big else 0)), value, font(sz, w), col, anchor="ra")
        ry += 54 if big else 40

    img.save(out)
    return out


# --------------------------------------------------------------------------
# 图 5：compare.png  三种点法对比
# --------------------------------------------------------------------------
def make_compare(out: str):
    W, H = 1040, 600
    img = Image.new("RGB", (W, H), (252, 252, 253))
    d = ImageDraw.Draw(img)

    text(d, (52, 40), "同一顿饭，三种点法", font(32, "bold"), DARK)
    text(d, (52, 88), "约束：2 人 · 预算 50 元 · 人均至少 500 kcal · 忌牛肉 · 要有主食和饮品", font(18), GRAY)

    base_y = 470
    maxv = 56.0
    scale = 250 / maxv

    bars = [
        ("直觉点法", "一人一套麦香鸡套餐", 56.00, 1610, RED, "超预算 ¥6.00，且热量偏高"),
        ("只挑最便宜", "麦香鸡 + 纯悦", 24.50, 369, GRAY, "便宜，但人均仅 185 kcal"),
        ("麦麦饭搭子", "麦香鸡套餐 + 派 + 满30减7", 29.50, 1026, GREEN, "预算内 · 热量达标 · 省 19.2%"),
    ]

    bw = 180
    gap = 90
    x = 120
    for name, desc, val, cal, col, note in bars:
        h = val * scale
        # 柱子
        rrect(d, (x, base_y - h, x + bw, base_y), 10, fill=col)
        # 数值
        text(d, (x + bw / 2, base_y - h - 34), "¥%.2f" % val, font(28, "bold"), col, anchor="ma")
        # 名称
        text(d, (x + bw / 2, base_y + 18), name, font(22, "bold"), DARK, anchor="ma")
        text(d, (x + bw / 2, base_y + 52), desc, font(16), GRAY, anchor="ma")
        text(d, (x + bw / 2, base_y + 78), "%d kcal" % cal, font(17, "bold"), GRAY, anchor="ma")
        text(d, (x + bw / 2, base_y + 104), note, font(15), col, anchor="ma")
        x += bw + gap

    d.line([(80, base_y), (W - 52, base_y)], fill=GRAY_LIGHT, width=3)

    # 预算虚线
    by = base_y - 50 * scale
    for xx in range(80, W - 52, 16):
        d.line([(xx, by), (xx + 8, by)], fill=(214, 35, 0), width=2)
    text(d, (W - 56, by - 8), "预算 50 元", font(17, "bold"), RED, anchor="rs")

    img.save(out)
    return out


# --------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.join(here, "..", "images")
    os.makedirs(outdir, exist_ok=True)

    jobs = [
        ("banner.png", make_banner),
        ("architecture.png", make_architecture),
        ("optimizer.png", make_optimizer),
        ("demo-result.png", make_demo),
        ("compare.png", make_compare),
    ]
    for name, fn in jobs:
        p = fn(os.path.join(outdir, name))
        print("生成", os.path.relpath(p, os.path.join(here, "..")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
