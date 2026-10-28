# -*- coding: utf-8 -*-
"""通用绿幕/纯色底抠图：把角色从纯色背景抠成透明 PNG（带软边 + 去色边）。

用法：
    python matte.py <输入图> <输出图> [--bg-thresh 40] [--bg-dist 55]

背景判定：绿度 d = g - max(r, b) >= bg_thresh，或与角部采样背景色欧氏距离 <= bg_dist
    => 透明；d <= 14 => 不透明；中间线性软边。
输出：角色保留原色 + alpha，边缘用 chamfer 最近不透明像素去色边。
"""
import sys, argparse
from PIL import Image

INF = float("inf")


def matte(src, dst, bg_thresh=40, bg_dist=55):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()
    vals = []
    for (x0, y0, x1, y1) in ((0, 0, 120, 100), (w-120, 0, w, 100),
                             (0, h-100, 120, h), (w-120, h-100, w, h)):
        for x in range(x0, x1, 6):
            for y in range(y0, y1, 6):
                vals.append(px[x, y][:3])
    n = len(vals)
    bg = tuple(sum(c[i] for c in vals)//n for i in range(3))

    alpha = [[0]*w for _ in range(h)]
    rcol = [[0]*w for _ in range(h)]
    gcol = [[0]*w for _ in range(h)]
    bcol = [[0]*w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            d = g - max(r, b)
            d2 = ((r-bg[0])**2 + (g-bg[1])**2 + (b-bg[2])**2) ** 0.5
            if d >= bg_thresh or d2 <= bg_dist:
                a = 0
            elif d <= 14:
                a = 255
            else:
                a = int(255*(bg_thresh-d)/(bg_thresh-14) + 0.5)
            alpha[y][x] = a
            if a > 0:
                rcol[y][x], gcol[y][x], bcol[y][x] = r, g, b

    dist = [[INF]*w for _ in range(h)]
    nr = [[0]*w for _ in range(h)]; ng = [[0]*w for _ in range(h)]; nb = [[0]*w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if alpha[y][x] == 255:
                dist[y][x] = 0.0
                nr[y][x], ng[y][x], nb[y][x] = rcol[y][x], gcol[y][x], bcol[y][x]
    for y in range(h):
        for x in range(w):
            best = dist[y][x]; bc = (nr[y][x], ng[y][x], nb[y][x])
            for (dy, dx, wgt) in ((-1,0,3),(0,-1,3),(-1,-1,4),(-1,1,4)):
                yy, xx = y+dy, x+dx
                if 0 <= yy < h and 0 <= xx < w and dist[yy][xx]+wgt < best:
                    best = dist[yy][xx]+wgt; bc = (nr[yy][xx], ng[yy][xx], nb[yy][xx])
            dist[y][x] = best; nr[y][x], ng[y][x], nb[y][x] = bc
    for y in range(h-1, -1, -1):
        for x in range(w-1, -1, -1):
            best = dist[y][x]; bc = (nr[y][x], ng[y][x], nb[y][x])
            for (dy, dx, wgt) in ((1,0,3),(0,1,3),(1,1,4),(1,-1,4)):
                yy, xx = y+dy, x+dx
                if 0 <= yy < h and 0 <= xx < w and dist[yy][xx]+wgt < best:
                    best = dist[yy][xx]+wgt; bc = (nr[yy][xx], ng[yy][xx], nb[yy][xx])
            dist[y][x] = best; nr[y][x], ng[y][x], nb[y][x] = bc

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            a = alpha[y][x]
            if a > 0:
                op[x, y] = (nr[y][x], ng[y][x], nb[y][x], a)
    out.save(dst)
    print("matted", dst, im.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--bg-thresh", type=int, default=40)
    ap.add_argument("--bg-dist", type=int, default=55)
    args = ap.parse_args()
    matte(args.src, args.dst, args.bg_thresh, args.bg_dist)


if __name__ == "__main__":
    main()
